# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at http://cvs2svn.tigris.org/.
# ====================================================================

"""This module contains the SVNRepositoryMirror class."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.serializer import MarshalSerializer
from cvs2svn_lib.database import IndexedDatabase
from cvs2svn_lib.record_table import UnsignedIntegerPacker
from cvs2svn_lib.record_table import RecordTable
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.svn_commit_item import SVNCommitItem


class _MirrorNode(object):
  """Represent a node within the SVNRepositoryMirror.

  Instances of this class act like a map { component : _MirrorNode },
  where component is the path name component of an item within this
  node (i.e., a file within this directory).

  Instances also have a particular path, even though the same node
  content can have multiple paths within the same repository.  The
  path member indicates via what path the node was accessed.

  For space efficiency, SVNRepositoryMirror does not actually use this
  class to store the data internally, but rather constructs instances
  of this class on demand."""

  def __init__(self, repo, path, key, entries):
    # The SVNRepositoryMirror containing this directory:
    self.repo = repo

    # The path of this node within the repository:
    self.path = path

    # The key of this directory:
    self.key = key

    # The entries within this directory (a map from component name to
    # node):
    self.entries = entries

  def get_subpath(self, *components):
    return path_join(self.path, *components)

  def __getitem__(self, component):
    """Return the _MirrorNode associated with the specified subnode.

    Return None if the specified subnode does not exist."""

    key = self.entries.get(component, None)
    if key is None:
      return None
    else:
      return self.repo._get_node(self.get_subpath(component), key)

  def __contains__(self, component):
    return component in self.entries

  def __iter__(self):
    return self.entries.__iter__()


class _ReadOnlyMirrorNode(_MirrorNode):
  """Represent a read-only node within the SVNRepositoryMirror."""

  pass


class _WritableMirrorNode(_MirrorNode):
  """Represent a writable node within the SVNRepositoryMirror."""

  def __setitem__(self, component, node):
    self.entries[component] = node.key

  def __delitem__(self, component):
    del self.entries[component]

  def delete_component(self, component):
    """Delete the COMPONENT from this directory and notify delagates.

    COMPONENT must exist in this node."""

    del self[component]
    self.repo._invoke_delegates('delete_path', self.get_subpath(component))


class SVNRepositoryMirror:
  """Mirror a Subversion Repository as it is constructed, one
  SVNCommit at a time.  The mirror is skeletal; it does not contain
  file contents.  The creation of a dumpfile or Subversion repository
  is handled by delegates.  See self.add_delegate method for how to
  set delegates.

  The structure of the repository is kept in two databases and one
  hash.  The _svn_revs_root_nodes database maps revisions to root node
  keys, and the _nodes_db database maps node keys to nodes.  A node is
  a hash from directory names to keys.  Both the _svn_revs_root_nodes
  and the _nodes_db are stored on disk and each access is expensive.

  The _nodes_db database only has the keys for old revisions.  The
  revision that is being contructed is kept in memory in the
  _new_nodes map, which is cheap to access.

  You must invoke start_commit() before each SVNCommit and
  end_commit() afterwards.

  *** WARNING *** Path arguments to methods in this class MUST NOT
      have leading or trailing slashes."""

  class SVNRepositoryMirrorParentMissingError(Exception):
    """Exception raised if an attempt is made to add a path to the
    repository mirror but the parent's path doesn't exist in the
    youngest revision of the repository."""

    pass

  class SVNRepositoryMirrorPathExistsError(Exception):
    """Exception raised if an attempt is made to add a path to the
    repository mirror and that path already exists in the youngest
    revision of the repository."""

    pass

  def __init__(self):
    """Set up the SVNRepositoryMirror and prepare it for SVNCommits."""

    self._key_generator = KeyGenerator()

    self._delegates = [ ]

    # A map from SVN revision number to root node number:
    self._svn_revs_root_nodes = RecordTable(
        artifact_manager.get_temp_file(config.SVN_MIRROR_REVISIONS_TABLE),
        DB_OPEN_NEW, UnsignedIntegerPacker())

    # This corresponds to the 'nodes' table in a Subversion fs.  (We
    # don't need a 'representations' or 'strings' table because we
    # only track metadata, not file contents.)
    self._nodes_db = IndexedDatabase(
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_STORE),
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_INDEX_TABLE),
        DB_OPEN_NEW, serializer=MarshalSerializer())

    # Start at revision 0 without a root node.  It will be created
    # by _open_writable_root_node.
    self._youngest = 0

    self._symbolings_reader = SymbolingsReader()

  def start_commit(self, revnum, revprops):
    """Start a new commit."""

    self._youngest = revnum
    self._new_root_node = None
    self._new_nodes = { }

    self._invoke_delegates('start_commit', revnum, revprops)

    if revnum == 1:
      # For the first revision, we have to create the root directory
      # out of thin air:
      self._new_root_node = self._create_node('')

  def end_commit(self):
    """Called at the end of each commit.  This method copies the newly
    created nodes to the on-disk nodes db."""

    if self._new_root_node is None:
      # No changes were made in this revision, so we make the root node
      # of the new revision be the same as the last one.
      self._svn_revs_root_nodes[self._youngest] = \
          self._svn_revs_root_nodes[self._youngest - 1]
    else:
      self._svn_revs_root_nodes[self._youngest] = self._new_root_node.key
      # Copy the new nodes to the _nodes_db
      for key, value in self._new_nodes.items():
        self._nodes_db[key] = value

    del self._new_root_node
    del self._new_nodes

    self._invoke_delegates('end_commit')

  def _create_node(self, path, entries=None):
    if entries is None:
      entries = {}
    else:
      entries = entries.copy()

    node = _WritableMirrorNode(
        self, path, self._key_generator.gen_id(), entries)

    self._new_nodes[node.key] = node.entries
    return node

  def _get_node(self, path, key):
    """Returns the node for PATH and key KEY.

    The node might be read from either self._nodes_db or
    self._new_nodes.  Return an instance of _MirrorNode."""

    contents = self._new_nodes.get(key, None)
    if contents is not None:
      return _WritableMirrorNode(self, path, key, contents)
    else:
      return _ReadOnlyMirrorNode(self, path, key, self._nodes_db[key])

  def _open_readonly_node(self, path, revnum):
    """Open a readonly node for PATH at revision REVNUM.

    Return an instance of _MirrorNode if the path exists, else None."""

    # Get the root key
    if revnum == self._youngest:
      if self._new_root_node is None:
        node_key = self._svn_revs_root_nodes[self._youngest - 1]
      else:
        node_key = self._new_root_node.key
    else:
      node_key = self._svn_revs_root_nodes[revnum]

    node = self._get_node('', node_key)
    for component in path.split('/'):
      node = node[component]
      if node is None:
        return None

    return node

  def _open_writable_root_node(self):
    """Open and return a writable root node.

    The current root node is returned immeditely if it is already
    writable.  If not, create a new one by copying the contents of the
    root node of the previous version."""

    if self._new_root_node is None:
      # Root node still has to be created for this revision:
      old_root_node = self._get_node(
          '', self._svn_revs_root_nodes[self._youngest - 1])
      self._new_root_node = self._create_node('', old_root_node.entries)

    return self._new_root_node

  def _open_writable_node(self, svn_path, create):
    """Open a writable node for the path SVN_PATH.

    Iff CREATE is True, create a directory node at SVN_PATH and any
    missing directories.  Return an instance of _WritableMirrorNode,
    or None if SVN_PATH doesn't exist and CREATE is not set."""

    node = self._open_writable_root_node()

    if svn_path:
      # Walk down the path, one node at a time.
      for component in svn_path.split('/'):
        new_node = node[component]
        if new_node is not None:
          # The component exists.
          if not isinstance(new_node, _WritableMirrorNode):
            # Create a new node, with entries initialized to be the same
            # as those of the old node:
            new_node = self._create_node(new_node.path, new_node.entries)
            node[component] = new_node
        elif create:
          # The component does not exist, so we create it.
          new_node = self._create_node(path_join(node.path, component))
          node[component] = new_node
          self._invoke_delegates('mkdir', new_node.path)
        else:
          # The component does not exist and we are not instructed to
          # create it, so we give up.
          return None

        node = new_node

    return node

  def path_exists(self, path):
    """Return True iff PATH exists in self._youngest of the repository mirror.

    PATH must not start with '/'."""

    return self._open_readonly_node(path, self._youngest) is not None

  def delete_path(self, svn_path, should_prune=False):
    """Delete SVN_PATH from the tree.

    SVN_PATH must currently exist.

    If SHOULD_PRUNE is true, then delete all ancestor directories that
    are made empty when SVN_PATH is deleted.  In other words,
    SHOULD_PRUNE is like the -P option to 'cvs checkout'.

    This function ignores requests to delete the root directory or any
    directory for which any project's is_unremovable() method returns
    True, either directly or by pruning."""

    if svn_path == '':
      return
    for project in Ctx().projects:
      if project.is_unremovable(svn_path):
        return

    (parent_path, entry,) = path_split(svn_path)
    parent_node = self._open_writable_node(parent_path, False)

    parent_node.delete_component(entry)
    # The following recursion makes pruning an O(n^2) operation in the
    # worst case (where n is the depth of SVN_PATH), but the worst case
    # is probably rare, and the constant cost is pretty low.  Another
    # drawback is that we issue a delete for each path and not just
    # a single delete for the topmost directory pruned.
    if should_prune and len(parent_node.entries) == 0:
      self.delete_path(parent_path, True)

  def mkdir(self, path):
    """Create PATH in the repository mirror at the youngest revision."""

    self._open_writable_node(path, True)

  def change_path(self, cvs_rev):
    """Register a change in self._youngest for the CVS_REV's svn_path
    in the repository mirror."""

    # We do not have to update the nodes because our mirror is only
    # concerned with the presence or absence of paths, and a file
    # content change does not cause any path changes.
    self._invoke_delegates('change_path', SVNCommitItem(cvs_rev, False))

  def add_path(self, cvs_rev):
    """Add the CVS_REV's svn_path to the repository mirror."""

    (parent_path, component,) = path_split(cvs_rev.get_svn_path())
    parent_node = self._open_writable_node(parent_path, True)

    assert component not in parent_node

    parent_node[component] = \
        self._create_node(path_join(parent_node.path, component))

    self._invoke_delegates('add_path', SVNCommitItem(cvs_rev, True))

  def skip_path(self, cvs_rev):
    """This does nothing, except for allowing the delegate to handle
    skipped revisions symmetrically."""
    self._invoke_delegates('skip_path', cvs_rev)

  def copy_path(self, src_path, dest_path, src_revnum, create_parent=False):
    """Copy SRC_PATH at subversion revision number SRC_REVNUM to DEST_PATH.

    In the youngest revision of the repository, DEST_PATH's parent
    *must* exist unless create_parent is specified.  DEST_PATH itself
    *must not* exist.

    Return the new node at DEST_PATH.  Note that this node is not
    necessarily writable, though its parent node necessarily is."""

    # Get the node of our src_path
    src_node = self._open_readonly_node(src_path, src_revnum)

    # Get the parent path and the base path of the dest_path
    (dest_parent, dest_basename,) = path_split(dest_path)
    dest_parent_node = self._open_writable_node(dest_parent, create_parent)

    if dest_parent_node is None:
      raise self.SVNRepositoryMirrorParentMissingError(
          "Attempt to add path '%s' to repository mirror, "
          "but its parent directory doesn't exist in the mirror." % dest_path)
    elif dest_basename in dest_parent_node:
      raise self.SVNRepositoryMirrorPathExistsError(
          "Attempt to add path '%s' to repository mirror "
          "when it already exists in the mirror." % dest_path)

    dest_parent_node[dest_basename] = src_node
    self._invoke_delegates('copy_path', src_path, dest_path, src_revnum)

    # This is a cheap copy, so src_node has the same contents as the
    # new destination node.  But we have to get it from its parent
    # node again so that its path is correct.
    return dest_parent_node[dest_basename]

  def fill_symbol(self, svn_symbol_commit):
    """Perform all copies necessary to create as much of the the tag
    or branch SYMBOL as possible given the current revision of the
    repository mirror.  SYMBOL is an instance of TypedSymbol.

    The symbolic name is guaranteed to exist in the Subversion
    repository by the end of this call, even if there are no paths
    under it."""

    symbol = svn_symbol_commit.symbol

    # Get the set of sources for the symbolic name:
    source_set = self._symbolings_reader.get_source_set(
        svn_symbol_commit, self._youngest
        )

    if not source_set:
      raise InternalError(
          'fill_symbol() called for %s with empty source set' % (symbol,)
          )

    dest_node = self._open_writable_node(symbol.get_path(), False)
    self._fill(symbol, dest_node, source_set)

  def _prune_extra_entries(self, dest_path, dest_node, src_entries):
    """Delete any entries in DEST_NODE that are not in SRC_ENTRIES.

    This might require creating a new writable node, so return a
    possibly-modified dest_node."""

    delete_list = [
        component
        for component in dest_node
        if component not in src_entries]
    if delete_list:
      if not isinstance(dest_node, _WritableMirrorNode):
        dest_node = self._open_writable_node(dest_path, False)
      # Sort the delete list so that the output is in a consistent
      # order:
      delete_list.sort()
      for component in delete_list:
        dest_node.delete_component(component)
    return dest_node

  def _fill(self, symbol, dest_node, source_set,
            parent_source=None, prune_ok=False):
    """Fill the tag or branch SYMBOL at the path indicated by SOURCE_SET.

    Use items from SOURCE_SET, and recurse into the child items.

    Fill SYMBOL starting at the path SYMBOL.get_path(SOURCE_SET.path).
    DEST_NODE is the node of this destination path, or None if the
    destination does not yet exist.  All directories above this path
    have already been filled.  SOURCE_SET is a list of FillSource
    classes that are candidates to be copied to the destination.

    PARENT_SOURCE is the source that was best for the parent
    directory.  (Note that the parent directory wasn't necessarily
    copied in this commit, but PARENT_SOURCE was chosen anyway.)  We
    prefer to copy from the same source as was used for the parent,
    since it typically requires less touching-up.  If PARENT_SOURCE is
    None, then this is the top-level directory, and no revision is
    preferable to any other (which probably means that no copies have
    happened yet).

    PRUNE_OK means that a copy has been made in this recursion, and
    it's safe to prune directories that are not in
    SYMBOL_FILL._node_tree.

    PARENT_SOURCE, and PRUNE_OK should only be passed in by recursive
    calls."""

    copy_source = source_set.get_best_source()

    src_path = path_join(copy_source.prefix, source_set.path)
    dest_path = symbol.get_path(source_set.path)

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if dest_node is None:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      do_copy = True
    elif prune_ok and (
          parent_source is None
          or copy_source.prefix != parent_source.prefix
          or copy_source.revnum != parent_source.revnum):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent before we can re-copy from the correct source:
      self.delete_path(dest_path)
      do_copy = True
    else:
      do_copy = False

    if do_copy:
      dest_node = self.copy_path(src_path, dest_path, copy_source.revnum)
      prune_ok = True

    # Get the map {entry : FillSourceSet} for entries within this
    # directory that need filling.
    src_entries = source_set.get_subsource_sets(copy_source)

    if prune_ok:
      dest_node = self._prune_extra_entries(dest_path, dest_node, src_entries)

    # Recurse into the SRC_ENTRIES keys sorted in alphabetical order.
    entries = src_entries.keys()
    entries.sort()
    for entry in entries:
      self._fill(symbol, dest_node[entry], src_entries[entry],
                 copy_source, prune_ok)

  def add_delegate(self, delegate):
    """Adds DELEGATE to self._delegates.

    For every delegate you add, as soon as SVNRepositoryMirror
    performs a repository action method, SVNRepositoryMirror will call
    the delegate's corresponding repository action method.  Multiple
    delegates will be called in the order that they are added.  See
    SVNRepositoryMirrorDelegate for more information."""

    self._delegates.append(delegate)

  def _invoke_delegates(self, method, *args):
    """Iterate through each of our delegates, in the order that they
    were added, and call the delegate's method named METHOD with the
    arguments in ARGS."""

    for delegate in self._delegates:
      getattr(delegate, method)(*args)

  def close(self):
    """Call the delegate finish methods and close databases."""

    self._invoke_delegates('finish')
    self._svn_revs_root_nodes.close()
    self._svn_revs_root_nodes = None
    self._nodes_db.close()
    self._nodes_db = None


class SVNRepositoryMirrorDelegate:
  """Abstract superclass for any delegate to SVNRepositoryMirror.
  Subclasses must implement all of the methods below.

  For each method, a subclass implements, in its own way, the
  Subversion operation implied by the method's name.  For example, for
  the add_path method, the DumpfileDelegate would write out a
  "Node-add:" command to a Subversion dumpfile, the StdoutDelegate
  would merely print that the path is being added to the repository,
  and the RepositoryDelegate would actually cause the path to be added
  to the Subversion repository that it is creating.
  """

  def start_commit(self, revnum, revprops):
    """Perform any actions needed to start an SVN commit with revision
    number REVNUM and revision properties REVPROPS; see subclass
    implementation for details."""

    raise NotImplementedError

  def end_commit(self):
    """This method is called at the end of each SVN commit."""

    raise NotImplementedError

  def mkdir(self, path):
    """PATH is a string; see subclass implementation for details."""

    raise NotImplementedError

  def add_path(self, s_item):
    """S_ITEM is an SVNCommitItem; see subclass implementation for
    details."""

    raise NotImplementedError

  def change_path(self, s_item):
    """S_ITEM is an SVNCommitItem; see subclass implementation for
    details."""

    raise NotImplementedError

  def skip_path(self, cvs_rev):
    """CVS_REV is a CVSRevision; see subclass implementation for
    details."""

    raise NotImplementedError

  def delete_path(self, path):
    """PATH is a string; see subclass implementation for
    details."""

    raise NotImplementedError

  def copy_path(self, src_path, dest_path, src_revnum):
    """SRC_PATH and DEST_PATH are both strings, and SRC_REVNUM is a
    subversion revision number (int); see subclass implementation for
    details."""

    raise NotImplementedError

  def finish(self):
    """Perform any cleanup necessary after all revisions have been
    committed."""

    raise NotImplementedError


