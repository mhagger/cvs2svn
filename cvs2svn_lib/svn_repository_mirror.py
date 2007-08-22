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
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.svn_commit_item import SVNCommitItem


class _MirrorNode(object):
  """Represent a node within the SVNRepositoryMirror.

  Instances of this class act like a map { component : _MirrorNode },
  where component is the path name component of an item within this
  node (i.e., a file within this directory).

  For space efficiency, SVNRepositoryMirror does not actually use this
  class to store the data internally, but rather constructs instances
  of this class on demand."""

  def __init__(self, repo, key, entries):
    # The SVNRepositoryMirror containing this directory:
    self.repo = repo

    # The key of this directory:
    self.key = key

    # The entries within this directory (a map from component name to
    # node):
    self.entries = entries

  def __getitem__(self, component):
    """Return the _MirrorNode associated with the specified subnode.

    Return None if the specified subnode does not exist."""

    key = self.entries.get(component, None)
    if key is None:
      return None
    else:
      return self.repo._get_node(key)

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


class SVNRepositoryMirror:
  """Mirror a Subversion repository and its history.

  Mirror a Subversion repository as it is constructed, one SVNCommit
  at a time.  The mirror is skeletal; it does not contain file
  contents.  The creation of a dumpfile or Subversion repository is
  handled by delegates.  See the add_delegate() method for how to set
  delegates.

  The structure of the repository is kept in two databases and one
  hash.  The _svn_revs_root_nodes database maps revisions to root node
  keys, and the _nodes_db database maps node keys to nodes.  A node is
  a hash from directory names to keys.  Both the _svn_revs_root_nodes
  and the _nodes_db are stored on disk and each access is expensive.

  The _nodes_db database only has the keys for old revisions.  The
  revision that is being constructed is kept in memory in the
  _new_nodes map, which is cheap to access.

  You must invoke start_commit() before each SVNCommit and
  end_commit() afterwards.

  *** WARNING *** Path arguments to methods in this class MUST NOT
      have leading or trailing slashes."""

  class ParentMissingError(Exception):
    """The parent of a path is missing.

    Exception raised if an attempt is made to add a path to the
    repository mirror but the parent's path doesn't exist in the
    youngest revision of the repository."""

    pass

  class PathExistsError(Exception):
    """The path already exists in the repository.

    Exception raised if an attempt is made to add a path to the
    repository mirror and that path already exists in the youngest
    revision of the repository."""

    pass

  def register_artifacts(self, which_pass):
    """Register the artifacts that will be needed for this object."""

    artifact_manager.register_temp_file(
        config.SVN_MIRROR_REVISIONS_TABLE, which_pass
        )
    artifact_manager.register_temp_file(
        config.SVN_MIRROR_NODES_INDEX_TABLE, which_pass
        )
    artifact_manager.register_temp_file(
        config.SVN_MIRROR_NODES_STORE, which_pass
        )

  def open(self):
    """Set up the SVNRepositoryMirror and prepare it for SVNCommits."""

    self._key_generator = KeyGenerator()

    self._delegates = [ ]

    # A map from SVN revision number to root node number:
    self._svn_revs_root_nodes = RecordTable(
        artifact_manager.get_temp_file(config.SVN_MIRROR_REVISIONS_TABLE),
        DB_OPEN_NEW, UnsignedIntegerPacker()
        )

    # This corresponds to the 'nodes' table in a Subversion fs.  (We
    # don't need a 'representations' or 'strings' table because we
    # only track metadata, not file contents.)
    self._nodes_db = IndexedDatabase(
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_STORE),
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_INDEX_TABLE),
        DB_OPEN_NEW, serializer=MarshalSerializer()
        )

    # Start at revision 0 without a root node.  It will be created
    # by _open_writable_root_node.
    self._youngest = 0

  def start_commit(self, revnum, revprops):
    """Start a new commit."""

    self._youngest = revnum
    self._new_root_node = None
    self._new_nodes = { }

    self._invoke_delegates('start_commit', revnum, revprops)

    if revnum == 1:
      # For the first revision, we have to create the root directory
      # out of thin air:
      self._new_root_node = self._create_node_raw()

  def end_commit(self):
    """Called at the end of each commit.

    This method copies the newly created nodes to the on-disk nodes
    db."""

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

  def _create_node_raw(self, entries=None):
    if entries is None:
      entries = {}
    else:
      entries = entries.copy()

    node = _WritableMirrorNode(self, self._key_generator.gen_id(), entries)

    self._new_nodes[node.key] = node.entries
    return node

  def _create_node(self, entries=None):
    if entries is None:
      entries = {}
    else:
      entries = entries.copy()

    node = _WritableMirrorNode(self, self._key_generator.gen_id(), entries)

    self._new_nodes[node.key] = node.entries
    return node


  def _get_node(self, key):
    """Return the node for key KEY.

    The node might be read from either self._nodes_db or
    self._new_nodes.  Return an instance of _MirrorNode."""

    contents = self._new_nodes.get(key, None)
    if contents is not None:
      return _WritableMirrorNode(self, key, contents)
    else:
      return _ReadOnlyMirrorNode(self, key, self._nodes_db[key])

  def _open_readonly_lod_node(self, lod, revnum):
    """Open a readonly node for the root path of LOD at revision REVNUM.

    Return an instance of _MirrorNode if the path exists, else None."""

    # Get the root key
    if revnum == self._youngest:
      if self._new_root_node is None:
        node_key = self._svn_revs_root_nodes[self._youngest - 1]
      else:
        node_key = self._new_root_node.key
    else:
      node_key = self._svn_revs_root_nodes[revnum]

    node = self._get_node(node_key)

    for component in lod.get_path().split('/'):
      node = node[component]
      if node is None:
        return None

    return node

  def _open_readonly_node(self, cvs_path, lod, revnum):
    """Open a readonly node for CVS_PATH from LOD at REVNUM."""

    if cvs_path.parent_directory is None:
      return self._open_readonly_lod_node(lod, revnum)
    else:
      parent_node = self._open_readonly_node(
          cvs_path.parent_directory, lod, revnum
          )
      if parent_node is None:
        return None
      else:
        return parent_node[cvs_path.basename]

  def _open_writable_node_raw(
        self, svn_path, create=False, invoke_delegates=True
        ):
    """Open a writable node for the path SVN_PATH.

    Iff CREATE is True, create a directory node at SVN_PATH and any
    missing directories.  Return an instance of _WritableMirrorNode,
    or None if SVN_PATH doesn't exist and CREATE is not set."""

    # First, get a writable root node:
    if self._new_root_node is None:
      # Root node still has to be created for this revision:
      old_root_node = self._get_node(
          self._svn_revs_root_nodes[self._youngest - 1]
          )
      self._new_root_node = self._create_node_raw(old_root_node.entries)

    node = self._new_root_node
    node_path = ''

    if svn_path:
      # Walk down the path, one node at a time.
      for component in svn_path.split('/'):
        new_node = node[component]
        new_node_path = path_join(node_path, component)
        if new_node is not None:
          # The component exists.
          if not isinstance(new_node, _WritableMirrorNode):
            # Create a new node, with entries initialized to be the same
            # as those of the old node:
            new_node = self._create_node_raw(new_node.entries)
            node[component] = new_node
        elif create:
          # The component does not exist, so we create it.
          new_node = self._create_node_raw()
          node[component] = new_node
          if invoke_delegates:
            self._invoke_delegates('mkdir', new_node_path)
        else:
          # The component does not exist and we are not instructed to
          # create it, so we give up.
          return None

        node = new_node
        node_path = new_node_path

    return node

  def _open_writable_lod_node(self, lod, create):
    """Open a writable node for the root path in LOD.

    Iff CREATE is True, create the path and any missing directories.
    Return an instance of _WritableMirrorNode, or None if the path
    doesn't already exist and CREATE is not set."""

    return self._open_writable_node_raw(lod.get_path(), create)

  def _open_writable_node(self, cvs_path, lod, create):
    """Open a writable node for CVS_PATH in LOD.

    Iff CREATE is True, create a directory node at SVN_PATH and any
    missing directories.  Return an instance of _WritableMirrorNode,
    or None if SVN_PATH doesn't exist and CREATE is not set."""

    if cvs_path.parent_directory is None:
      return self._open_writable_lod_node(lod, create)

    parent_node = self._open_writable_node(
        cvs_path.parent_directory, lod, create
        )
    if parent_node is None:
      return None

    node = parent_node[cvs_path.basename]
    if isinstance(node, _WritableMirrorNode):
      return node
    elif isinstance(node, _ReadOnlyMirrorNode):
      new_node = self._create_node(node.entries)
      parent_node[cvs_path.basename] = new_node
      return new_node
    elif create:
      # The component does not exist, so we create it.
      new_node = self._create_node()
      parent_node[cvs_path.basename] = new_node
      self._invoke_delegates('mkdir', lod.get_path(cvs_path.cvs_path))
      return new_node
    else:
      return None

  def delete_lod(self, lod):
    """Delete the main path for LOD from the tree.

    The path must currently exist.  Silently refuse to delete trunk
    paths."""

    if isinstance(lod, Trunk):
      # Never delete a Trunk path.
      return

    svn_path = lod.get_path()

    (parent_path, entry,) = path_split(svn_path)
    parent_node = self._open_writable_node_raw(parent_path, create=False)
    del parent_node[entry]
    self._invoke_delegates('delete_path', svn_path)

  def delete_path(self, cvs_path, lod, should_prune=False):
    """Delete CVS_PATH from LOD."""

    if cvs_path.parent_directory is None:
      if should_prune:
        self.delete_lod(lod)
      return

    parent_node = self._open_writable_node(
        cvs_path.parent_directory, lod, False
        )
    del parent_node[cvs_path.basename]
    self._invoke_delegates('delete_path', lod.get_path(cvs_path.cvs_path))

    # The following recursion makes pruning an O(n^2) operation in the
    # worst case (where n is the depth of SVN_PATH), but the worst case
    # is probably rare, and the constant cost is pretty low.  Another
    # drawback is that we issue a delete for each path and not just
    # a single delete for the topmost directory pruned.
    if should_prune and len(parent_node.entries) == 0:
      self.delete_path(cvs_path.parent_directory, lod, True)

  def initialize_project(self, project):
    """Create the basic structure for PROJECT."""

    self._invoke_delegates('initialize_project', project)

    # For a trunk-only conversion, trunk_path might be ''.
    if project.trunk_path:
      self._open_writable_node_raw(
          project.trunk_path, create=True, invoke_delegates=False
          )
    if not Ctx().trunk_only:
      self._open_writable_node_raw(
          project.branches_path, create=True, invoke_delegates=False
          )
      self._open_writable_node_raw(
          project.tags_path, create=True, invoke_delegates=False
          )

  def change_path(self, cvs_rev):
    """Register a change in self._youngest for the CVS_REV's svn_path."""

    # We do not have to update the nodes because our mirror is only
    # concerned with the presence or absence of paths, and a file
    # content change does not cause any path changes.
    self._invoke_delegates('change_path', SVNCommitItem(cvs_rev, False))

  def add_path(self, cvs_rev):
    """Add the CVS_REV's svn_path to the repository mirror."""

    cvs_file = cvs_rev.cvs_file
    parent_node = self._open_writable_node(
        cvs_file.parent_directory, cvs_rev.lod, True
        )

    if cvs_file.basename in parent_node:
      raise self.PathExistsError(
          'Attempt to add path \'%s\' to repository mirror '
          'when it already exists in the mirror.'
          % (cvs_rev.get_svn_path(),)
          )

    parent_node[cvs_file.basename] = self._create_node()

    self._invoke_delegates('add_path', SVNCommitItem(cvs_rev, True))

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy all of SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination's
    parent *must* exist, but the destination itself *must not* exist.

    Return the new node at DEST_LOD.  Note that this node is not
    necessarily writable, though its parent node necessarily is."""

    src_path = src_lod.get_path()
    dest_path = dest_lod.get_path()

    # Get the node of our src_path
    src_node = self._open_readonly_lod_node(src_lod, src_revnum)

    # Get the parent path and the base path of the dest_path
    (dest_parent, dest_basename,) = path_split(dest_path)
    dest_parent_node = self._open_writable_node_raw(dest_parent, False)

    if dest_parent_node is None:
      raise self.ParentMissingError(
          "Attempt to add path '%s' to repository mirror, "
          "but its parent directory doesn't exist in the mirror."
          % dest_path
          )
    elif dest_basename in dest_parent_node:
      raise self.PathExistsError(
          "Attempt to add path '%s' to repository mirror "
          "when it already exists in the mirror." % dest_path
          )

    dest_parent_node[dest_basename] = src_node
    self._invoke_delegates('copy_path', src_path, dest_path, src_revnum)

    # This is a cheap copy, so src_node has the same contents as the
    # new destination node.
    return src_node

  def copy_path(
        self, cvs_path, src_lod, dest_lod, src_revnum, create_parent=False
        ):
    """Copy CVS_PATH from SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination's
    parent *must* exist unless CREATE_PARENT is specified.  But the
    destination itself *must not* exist.

    Return the new node at (CVS_PATH, DEST_LOD).  Note that this node
    is not necessarily writable, though its parent node necessarily
    is."""

    if cvs_path.parent_directory is None:
      return self.copy_lod(src_lod, dest_lod, src_revnum)

    # Get the node of our source:
    src_node = self._open_readonly_node(cvs_path, src_lod, src_revnum)

    # Get the parent path of the destination:
    dest_parent_node = self._open_writable_node(
        cvs_path.parent_directory, dest_lod, create_parent
        )

    if dest_parent_node is None:
      raise self.ParentMissingError(
          'Attempt to add path \'%s\' to repository mirror, '
          'but its parent directory doesn\'t exist in the mirror.'
          % (dest_lod.get_path(cvs_path.cvs_path),)
          )
    elif cvs_path.basename in dest_parent_node:
      raise self.PathExistsError(
          'Attempt to add path \'%s\' to repository mirror '
          'when it already exists in the mirror.'
          % (dest_lod.get_path(cvs_path.cvs_path),)
          )

    dest_parent_node[cvs_path.basename] = src_node
    self._invoke_delegates(
        'copy_path',
        src_lod.get_path(cvs_path.cvs_path),
        dest_lod.get_path(cvs_path.cvs_path),
        src_revnum
        )

    # This is a cheap copy, so src_node has the same contents as the
    # new destination node.
    return src_node

  def fill_symbol(self, svn_symbol_commit, source_set):
    """Perform all copies for the CVSSymbols in SVN_SYMBOL_COMMIT.

    The symbolic name is guaranteed to exist in the Subversion
    repository by the end of this call, even if there are no paths
    under it."""

    symbol = svn_symbol_commit.symbol

    if not source_set:
      raise InternalError(
          'fill_symbol() called for %s with empty source set' % (symbol,)
          )

    dest_node = self._open_writable_lod_node(symbol, False)
    self._fill(symbol, dest_node, source_set)

  def _prune_extra_entries(self, cvs_path, symbol, dest_node, src_entries):
    """Delete any entries in DEST_NODE that are not in SRC_ENTRIES.

    This might require creating a new writable node, so return a
    possibly-modified dest_node."""

    delete_list = [
        component
        for component in dest_node
        if component not in src_entries
        ]
    if delete_list:
      if not isinstance(dest_node, _WritableMirrorNode):
        dest_node = self._open_writable_node(cvs_path, symbol, False)
      # Sort the delete list so that the output is in a consistent
      # order:
      delete_list.sort()
      for component in delete_list:
        del dest_node[component]
        self._invoke_delegates(
            'delete_path', symbol.get_path(cvs_path.cvs_path, component)
            )

    return dest_node

  def _fill(
        self, symbol, dest_node, source_set,
        parent_source=None, prune_ok=False
        ):
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
    it's safe to prune directories that are not in SOURCE_SET.

    PARENT_SOURCE, and PRUNE_OK should only be passed in by recursive
    calls."""

    copy_source = source_set.get_best_source()

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if dest_node is None:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      do_copy = True
    elif prune_ok and (
          parent_source is None
          or copy_source.lod != parent_source.lod
          or copy_source.revnum != parent_source.revnum):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent before we can re-copy from the correct source:
      self.delete_path(source_set.cvs_path, symbol)
      do_copy = True
    else:
      do_copy = False

    if do_copy:
      dest_node = self.copy_path(
          source_set.cvs_path, copy_source.lod, symbol, copy_source.revnum
          )
      prune_ok = True

    # Get the map {entry : FillSourceSet} for entries within this
    # directory that need filling.
    src_entries = source_set.get_subsource_sets(copy_source)

    if prune_ok:
      dest_node = self._prune_extra_entries(
          source_set.cvs_path, symbol, dest_node, src_entries
          )

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
    """Invoke a method on each delegate.

    Iterate through each of our delegates, in the order that they were
    added, and call the delegate's method named METHOD with the
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
  'Node-add:' command to a Subversion dumpfile, the StdoutDelegate
  would merely print that the path is being added to the repository,
  and the RepositoryDelegate would actually cause the path to be added
  to the Subversion repository that it is creating."""

  def start_commit(self, revnum, revprops):
    """An SVN commit is starting.

    Perform any actions needed to start an SVN commit with revision
    number REVNUM and revision properties REVPROPS; see subclass
    implementation for details."""

    raise NotImplementedError()

  def end_commit(self):
    """An SVN commit is ending."""

    raise NotImplementedError()

  def initialize_project(self, project):
    """Create the basic infrastructure for PROJECT.

    For Subversion, this means the trunk, branches, and tags
    directories."""

    raise NotImplementedError()

  def mkdir(self, path):
    """PATH is a string; see subclass implementation for details."""

    raise NotImplementedError()

  def add_path(self, s_item):
    """The path corresponding to S_ITEM is being added to the repository.

    S_ITEM is an SVNCommitItem; see subclass implementation for
    details."""

    raise NotImplementedError()

  def change_path(self, s_item):
    """The path corresponding to S_ITEM is being changed in the repository.

    S_ITEM is an SVNCommitItem; see subclass implementation for
    details."""

    raise NotImplementedError()

  def delete_path(self, path):
    """PATH is being deleted from the repository.

    PATH is a string; see subclass implementation for details."""

    raise NotImplementedError()

  def copy_path(self, src_path, dest_path, src_revnum):
    """SRC_PATH in SRC_REVNUM is being copied to DEST_PATH.

    SRC_PATH and DEST_PATH are both strings, and SRC_REVNUM is a
    subversion revision number (int); see subclass implementation for
    details."""

    raise NotImplementedError()

  def finish(self):
    """All SVN revisions have been committed.

    Perform any necessary cleanup."""

    raise NotImplementedError()


