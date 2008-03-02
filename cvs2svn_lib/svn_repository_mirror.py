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


import sys
import bisect

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
from cvs2svn_lib.cvs_file import CVSDirectory
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.svn_commit_item import SVNCommitItem
from cvs2svn_lib.svn_revision_range import SVNRevisionRange


class _MirrorNode(object):
  """Represent a node within the SVNRepositoryMirror.

  Instances of this class act like a map { CVSPath : _MirrorNode },
  where CVSPath is an item within this node (i.e., a file or
  subdirectory within this directory)."""

  def __init__(self, repo, id, entries):
    # The SVNRepositoryMirror containing this directory:
    self.repo = repo

    # The id of this node:
    self.id = id

    # The entries within this directory, stored as a map {CVSPath :
    # node_id}.  The node_ids are integers for CVSDirectories, None
    # for CVSFiles:
    self.entries = entries

  def __getitem__(self, cvs_path):
    """Return the _MirrorNode associated with the specified subnode.

    Return a _MirrorNode instance if the subnode is a CVSDirectory;
    None if it is a CVSFile.  Raise KeyError if the specified subnode
    does not exist."""

    id = self.entries[cvs_path]
    if id is None:
      # This represents a leaf node.
      return None
    else:
      return self.repo._get_node(id)

  def __len__(self):
    """Return the number of CVSPaths within this node."""

    return len(self.entries)

  def __contains__(self, cvs_path):
    """Return True iff CVS_PATH is contained in this node."""

    return cvs_path in self.entries

  def __iter__(self):
    """Iterate over the CVSPaths within this node."""

    return self.entries.__iter__()


class _ReadOnlyMirrorNode(_MirrorNode):
  """Represent a read-only node within the SVNRepositoryMirror."""

  pass


class _WritableMirrorNode(_MirrorNode):
  """Represent a writable node within the SVNRepositoryMirror."""

  def __setitem__(self, cvs_path, node):
    """Create or overwrite a subnode of this node.

    CVS_PATH is the path of the subnode.  NODE will be the new value
    of the node; for CVSDirectories it should be a _MirrorNode
    instance; for CVSFiles it should be None."""

    if node is None:
      self.entries[cvs_path] = None
    else:
      self.entries[cvs_path] = node.id

  def __delitem__(self, cvs_path):
    """Remove the subnode of this node at CVS_PATH.

    If the node does not exist, then raise a KeyError."""

    del self.entries[cvs_path]


class LODHistory(object):
  """The history of root nodes for a line of development.

  Members:

    revnums -- (list of int) the SVN revision numbers in which the id
        changed, in numerical order.

    ids -- (list of (int or None)) the ID of the node describing the
        root of this LOD starting at the corresponding SVN revision
        number, or None if the LOD did not exist in that revision.

  To find the root id for a given SVN revision number, a binary search
  is done within REVNUMS to find the index of the most recent revision
  at the time of REVNUM, then that index is used to read the id out of
  IDS.

  A sentry is written at the zeroth index of both arrays to describe
  the initial situation, namely, that the LOD doesn't exist in SVN
  revision r0.

  """

  __slots__ = ['revnums', 'ids']

  def __init__(self):
    self.revnums = [0]
    self.ids = [None]

  def get_id(self, revnum=sys.maxint):
    """Get the ID of the root path for the specified LOD in REVNUM.

    Raise KeyError if the LOD didn't exist in REVNUM."""

    index = bisect.bisect_right(self.revnums, revnum) - 1
    id = self.ids[index]

    if id is None:
      raise KeyError()

    return id

  def exists(self):
    """Return True iff LOD exists at the end of history."""

    return self.ids[-1] is not None

  def update(self, revnum, id):
    """Indicate that the root node of this LOD changed to ID at REVNUM.

    REVNUM is a revision number that must be the same as that of the
    previous recorded change (in which case the previous change is
    overwritten) or later (in which the new change is appended).

    ID can be a node ID, or it can be None to indicate that this LOD
    ceased to exist in REVNUM."""

    if revnum < self.revnums[-1]:
      raise KeyError()
    elif revnum == self.revnums[-1]:
      # Overwrite old entry (which was presumably read-only):
      self.ids[-1] = id
    else:
      self.revnums.append(revnum)
      self.ids.append(id)


class _NodeSerializer(MarshalSerializer):
  def __init__(self):
    self.cvs_file_db = Ctx()._cvs_file_db

  def _dump(self, node):
    return [
        (cvs_path.id, value)
        for (cvs_path, value) in node.iteritems()
        ]

  def dumpf(self, f, node):
    MarshalSerializer.dumpf(self, f, self._dump(node))

  def dumps(self, node):
    return MarshalSerializer.dumps(self, self._dump(node))

  def _load(self, items):
    retval = {}
    for (id, value) in items:
      retval[self.cvs_file_db.get_file(id)] = value
    return retval

  def loadf(self, f):
    return self._load(MarshalSerializer.loadf(self, f))

  def loads(self, s):
    return self._load(MarshalSerializer.loads(self, s))


class SVNRepositoryMirror:
  """Mirror a Subversion repository and its history.

  Mirror a Subversion repository as it is constructed, one SVNCommit
  at a time.  For each LineOfDevelopment we store a skeleton of the
  directory structure within that LOD for each SVN revision number in
  which it changed.  The creation of a dumpfile or Subversion
  repository is handled by delegates.  See the add_delegate() method
  for how to set delegates.

  For each LOD that has been seen so far, an LODHistory instance is
  stored in self._lod_histories.  An LODHistory keeps track of each
  SVNRevision in which files were added to or deleted from that LOD,
  as well as the node id of the node tree describing the LOD contents
  at that SVN revision.

  The LOD trees themselves are stored in the _nodes_db database, which
  maps node ids to nodes.  A node is a map from CVSPath.id to ids of
  the corresponding subnodes.  The _nodes_db is stored on disk and
  each access is expensive.

  The _nodes_db database only holds the nodes for old revisions.  The
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
        config.SVN_MIRROR_NODES_INDEX_TABLE, which_pass
        )
    artifact_manager.register_temp_file(
        config.SVN_MIRROR_NODES_STORE, which_pass
        )

  def open(self):
    """Set up the SVNRepositoryMirror and prepare it for SVNCommits."""

    self._key_generator = KeyGenerator()

    self._delegates = [ ]

    # A map from LOD to LODHistory instance for all LODs that have
    # been defines so far:
    self._lod_histories = {}

    # This corresponds to the 'nodes' table in a Subversion fs.  (We
    # don't need a 'representations' or 'strings' table because we
    # only track metadata, not file contents.)
    self._nodes_db = IndexedDatabase(
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_STORE),
        artifact_manager.get_temp_file(config.SVN_MIRROR_NODES_INDEX_TABLE),
        DB_OPEN_NEW, serializer=_NodeSerializer()
        )

    # Start at revision 0 without a root node.  It will be created
    # by _open_writable_root_node.
    self._youngest = 0

  def start_commit(self, revnum, revprops):
    """Start a new commit."""

    self._youngest = revnum

    # A map {node_id : _WritableMirrorNode}.
    self._new_nodes = {}

    self._invoke_delegates('start_commit', revnum, revprops)

  def end_commit(self):
    """Called at the end of each commit.

    This method copies the newly created nodes to the on-disk nodes
    db."""

    # Copy the new nodes to the _nodes_db
    for node in self._new_nodes.values():
      self._nodes_db[node.id] = node.entries

    del self._new_nodes

    self._invoke_delegates('end_commit')

  def _get_lod_history(self, lod):
    """Return the LODHistory instance describing LOD.

    Create a new (empty) LODHistory if it doesn't yet exist."""

    try:
      return self._lod_histories[lod]
    except KeyError:
      lod_history = LODHistory()
      self._lod_histories[lod] = lod_history
      return lod_history

  def _create_empty_node(self):
    """Create and return a new, empty, writable node."""

    new_node = _WritableMirrorNode(self, self._key_generator.gen_id(), {})
    self._new_nodes[new_node.id] = new_node
    return new_node

  def _copy_node(self, old_node):
    """Create and return a new, writable node that is a copy of OLD_NODE."""

    new_node = _WritableMirrorNode(
        self, self._key_generator.gen_id(), old_node.entries.copy()
        )

    self._new_nodes[new_node.id] = new_node
    return new_node

  def _get_node(self, id):
    """Return the node for id ID.

    The node might be read from either self._nodes_db or
    self._new_nodes.  Return an instance of _MirrorNode."""

    try:
      return self._new_nodes[id]
    except KeyError:
      return _ReadOnlyMirrorNode(self, id, self._nodes_db[id])

  def _open_readonly_lod_node(self, lod, revnum):
    """Open a readonly node for the root path of LOD at revision REVNUM.

    Return an instance of _MirrorNode if the path exists; otherwise,
    raise KeyError."""

    lod_history = self._get_lod_history(lod)
    node_id = lod_history.get_id(revnum)
    return self._get_node(node_id)

  def _open_readonly_node(self, cvs_path, lod, revnum):
    """Open a readonly node for CVS_PATH from LOD at REVNUM.

    If cvs_path refers to a leaf node, return None.

    Raise KeyError if the node does not exist."""

    if cvs_path.parent_directory is None:
      return self._open_readonly_lod_node(lod, revnum)
    else:
      parent_node = self._open_readonly_node(
          cvs_path.parent_directory, lod, revnum
          )
      return parent_node[cvs_path]

  def _open_writable_lod_node(self, lod, create, invoke_delegates=True):
    """Open a writable node for the root path in LOD.

    Iff CREATE is True, create the path and any missing directories.
    Return an instance of _WritableMirrorNode.  Raise KeyError if the
    path doesn't already exist and CREATE is not set."""

    lod_history = self._get_lod_history(lod)
    try:
      id = lod_history.get_id()
    except KeyError:
      if create:
        node = self._create_empty_node()
        lod_history.update(self._youngest, node.id)
        if invoke_delegates:
          self._invoke_delegates('initialize_lod', lod)
      else:
        raise
    else:
      node = self._get_node(id)
      if not isinstance(node, _WritableMirrorNode):
        # Node was created in an earlier revision, so we have to copy
        # it to make it writable:
        node = self._copy_node(node)
        lod_history.update(self._youngest, node.id)

    return node

  def _open_writable_node(self, cvs_directory, lod, create):
    """Open a writable node for CVS_DIRECTORY in LOD.

    Iff CREATE is True, create a directory node at SVN_PATH and any
    missing directories.  Return an instance of _WritableMirrorNode.

    Raise KeyError if CVS_DIRECTORY doesn't exist and CREATE is not
    set."""

    if cvs_directory.parent_directory is None:
      return self._open_writable_lod_node(lod, create)

    parent_node = self._open_writable_node(
        cvs_directory.parent_directory, lod, create
        )

    try:
      node = parent_node[cvs_directory]
    except KeyError:
      if create:
        # The component does not exist, so we create it.
        new_node = self._create_empty_node()
        parent_node[cvs_directory] = new_node
        self._invoke_delegates('mkdir', lod, cvs_directory)
        return new_node
      else:
        raise
    else:
      if isinstance(node, _WritableMirrorNode):
        return node
      elif isinstance(node, _ReadOnlyMirrorNode):
        new_node = self._copy_node(node)
        parent_node[cvs_directory] = new_node
        return new_node
      else:
        raise InternalError(
            'Attempt to modify file at %s in mirror' % (cvs_directory,)
            )

  def delete_lod(self, lod):
    """Delete the main path for LOD from the tree.

    The path must currently exist.  Silently refuse to delete trunk
    paths."""

    if isinstance(lod, Trunk):
      # Never delete a Trunk path.
      return

    lod_history = self._get_lod_history(lod)
    if not lod_history.exists():
      raise KeyError()
    lod_history.update(self._youngest, None)
    self._invoke_delegates('delete_lod', lod)

  def delete_path(self, cvs_path, lod, should_prune=False):
    """Delete CVS_PATH from LOD."""

    if cvs_path.parent_directory is None:
      self.delete_lod(lod)
      return
    else:
      parent_node = self._open_writable_node(
          cvs_path.parent_directory, lod, False
          )
      del parent_node[cvs_path]
      self._invoke_delegates('delete_path', lod, cvs_path)

      # The following recursion makes pruning an O(n^2) operation in the
      # worst case (where n is the depth of SVN_PATH), but the worst case
      # is probably rare, and the constant cost is pretty low.  Another
      # drawback is that we issue a delete for each path and not just
      # a single delete for the topmost directory pruned.
      if should_prune and len(parent_node) == 0:
        self.delete_path(cvs_path.parent_directory, lod, True)

  def initialize_project(self, project):
    """Create the basic structure for PROJECT."""

    self._invoke_delegates('initialize_project', project)

    self._open_writable_lod_node(
        project.get_trunk(), create=True, invoke_delegates=False
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

    if cvs_file in parent_node:
      raise self.PathExistsError(
          'Attempt to add path \'%s\' to repository mirror '
          'when it already exists in the mirror.'
          % (cvs_rev.get_svn_path(),)
          )

    parent_node[cvs_file] = None

    self._invoke_delegates('add_path', SVNCommitItem(cvs_rev, True))

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy all of SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination LOD
    *must not* already exist.

    Return the new node at DEST_LOD.  Note that this node is not
    necessarily writable, though its parent node necessarily is."""

    dest_path = dest_lod.get_path()

    # Get the node of our src_path
    src_node = self._open_readonly_lod_node(src_lod, src_revnum)

    dest_lod_history = self._get_lod_history(dest_lod)
    if dest_lod_history.exists():
      raise self.PathExistsError(
          "Attempt to add path '%s' to repository mirror "
          "when it already exists in the mirror." % dest_path
          )

    dest_lod_history.update(self._youngest, src_node.id)

    self._invoke_delegates('copy_lod', src_lod, dest_lod, src_revnum)

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

    # Get the node of our source, or None if it is a file:
    src_node = self._open_readonly_node(cvs_path, src_lod, src_revnum)

    # Get the parent path of the destination:
    try:
      dest_parent_node = self._open_writable_node(
          cvs_path.parent_directory, dest_lod, create_parent
          )
    except KeyError:
      raise self.ParentMissingError(
          'Attempt to add path \'%s\' to repository mirror, '
          'but its parent directory doesn\'t exist in the mirror.'
          % (dest_lod.get_path(cvs_path.cvs_path),)
          )

    if cvs_path in dest_parent_node:
      raise self.PathExistsError(
          'Attempt to add path \'%s\' to repository mirror '
          'when it already exists in the mirror.'
          % (dest_lod.get_path(cvs_path.cvs_path),)
          )

    dest_parent_node[cvs_path] = src_node
    self._invoke_delegates(
        'copy_path',
        src_lod.get_path(cvs_path.cvs_path),
        dest_lod.get_path(cvs_path.cvs_path),
        src_revnum
        )

    # This is a cheap copy, so src_node has the same contents as the
    # new destination node.
    return src_node

  def fill_symbol(self, svn_symbol_commit, fill_source):
    """Perform all copies for the CVSSymbols in SVN_SYMBOL_COMMIT.

    The symbolic name is guaranteed to exist in the Subversion
    repository by the end of this call, even if there are no paths
    under it."""

    symbol = svn_symbol_commit.symbol

    try:
      dest_node = self._open_writable_lod_node(symbol, False)
    except KeyError:
      self._fill_directory(symbol, None, fill_source, None)
    else:
      self._fill_directory(symbol, dest_node, fill_source, None)

  def _fill_directory(self, symbol, dest_node, fill_source, parent_source):
    """Fill the tag or branch SYMBOL at the path indicated by FILL_SOURCE.

    Use items from FILL_SOURCE, and recurse into the child items.

    Fill SYMBOL starting at the path FILL_SOURCE.cvs_path.  DEST_NODE
    is the node of this destination path, or None if the destination
    does not yet exist.  All directories above this path have already
    been filled.  FILL_SOURCE is a FillSource instance describing the
    items within a subtree of the repository that still need to be
    copied to the destination.

    PARENT_SOURCE is the SVNRevisionRange that was used to copy the
    parent directory, if it was copied in this commit.  We prefer to
    copy from the same source as was used for the parent, since it
    typically requires less touching-up.  If PARENT_SOURCE is None,
    then the parent directory was not copied in this commit, so no
    revision is preferable to any other."""

    copy_source = fill_source.compute_best_source(parent_source)

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if dest_node is None:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      dest_node = self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    elif (parent_source is not None) and (
          copy_source.source_lod != parent_source.source_lod
          or copy_source.opening_revnum != parent_source.opening_revnum
          ):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent then re-copy from the correct source:
      self.delete_path(fill_source.cvs_path, symbol)
      dest_node = self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    else:
      copy_source = parent_source

    # The map {CVSPath : FillSource} of entries within this directory
    # that need filling:
    src_entries = fill_source.get_subsource_map()

    if copy_source is not None:
      dest_node = self._prune_extra_entries(
          fill_source.cvs_path, symbol, dest_node, src_entries
          )

    # Recurse into the SRC_ENTRIES ids sorted in alphabetical order.
    cvs_paths = src_entries.keys()
    cvs_paths.sort()
    for cvs_path in cvs_paths:
      if isinstance(cvs_path, CVSDirectory):
        # Path is a CVSDirectory:
        try:
          dest_subnode = dest_node[cvs_path]
        except KeyError:
          # Path doesn't exist yet; it has to be created:
          self._fill_directory(symbol, None, src_entries[cvs_path], None)
        else:
          # Path already exists, but might have to be cleaned up:
          self._fill_directory(
              symbol, dest_subnode, src_entries[cvs_path], copy_source
              )
      else:
        # Path is a CVSFile:
        self._fill_file(
            symbol, cvs_path in dest_node, src_entries[cvs_path], copy_source
            )

  def _fill_file(self, symbol, dest_existed, fill_source, parent_source):
    """Fill the tag or branch SYMBOL at the path indicated by FILL_SOURCE.

    Use items from FILL_SOURCE.

    Fill SYMBOL at path FILL_SOURCE.cvs_path.  DEST_NODE is the node
    of this destination path, or None if the destination does not yet
    exist.  All directories above this path have already been filled
    as needed.  FILL_SOURCE is a FillSource instance describing the
    item that needs to be copied to the destination.

    PARENT_SOURCE is the source from which the parent directory was
    copied, or None if the parent directory was not copied during this
    commit.  We prefer to copy from PARENT_SOURCE, since it typically
    requires less touching-up.  If PARENT_SOURCE is None, then the
    parent directory was not copied in this commit, so no revision is
    preferable to any other."""

    copy_source = fill_source.compute_best_source(parent_source)

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if not dest_existed:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    elif (parent_source is not None) and (
          copy_source.source_lod != parent_source.source_lod
          or copy_source.opening_revnum != parent_source.opening_revnum
          ):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent and then re-copy from the correct source:
      self.delete_path(fill_source.cvs_path, symbol)
      self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )

  def _prune_extra_entries(
        self, dest_cvs_path, symbol, dest_node, src_entries
        ):
    """Delete any entries in DEST_NODE that are not in SRC_ENTRIES.

    This might require creating a new writable node, so return a
    possibly-modified dest_node."""

    delete_list = [
        cvs_path
        for cvs_path in dest_node
        if cvs_path not in src_entries
        ]
    if delete_list:
      if not isinstance(dest_node, _WritableMirrorNode):
        dest_node = self._open_writable_node(dest_cvs_path, symbol, False)
      # Sort the delete list so that the output is in a consistent
      # order:
      delete_list.sort()
      for cvs_path in delete_list:
        del dest_node[cvs_path]
        self._invoke_delegates('delete_path', symbol, cvs_path)

    return dest_node

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
    self._lod_histories = None
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
    number REVNUM and revision properties REVPROPS."""

    raise NotImplementedError()

  def end_commit(self):
    """An SVN commit is ending."""

    raise NotImplementedError()

  def initialize_project(self, project):
    """Initialize PROJECT.

    For Subversion, this means to create the trunk, branches, and tags
    directories for PROJECT."""

    raise NotImplementedError()

  def initialize_lod(self, lod):
    """Initialize LOD with no contents.

    LOD is an instance of LineOfDevelopment.  It is also possible for
    an LOD to be created by copying from another LOD; such events are
    indicated via the copy_lod() callback."""

    raise NotImplementedError()

  def mkdir(self, lod, cvs_directory):
    """Create CVS_DIRECTORY within LOD.

    LOD is a LineOfDevelopment; CVS_DIRECTORY is a CVSDirectory."""

    raise NotImplementedError()

  def add_path(self, s_item):
    """Add the path corresponding to S_ITEM to the repository.

    S_ITEM is an SVNCommitItem."""

    raise NotImplementedError()

  def change_path(self, s_item):
    """Change the path corresponding to S_ITEM in the repository.

    S_ITEM is an SVNCommitItem."""

    raise NotImplementedError()

  def delete_lod(self, lod):
    """Delete LOD from the repository.

    LOD is a LineOfDevelopment instance."""

    raise NotImplementedError()

  def delete_path(self, lod, cvs_path):
    """Delete CVS_PATH from LOD.

    LOD is a LineOfDevelopment; CVS_PATH is a CVSPath."""

    raise NotImplementedError()

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy SRC_LOD in SRC_REVNUM to DEST_LOD.

    SRC_LOD and DEST_LOD are both LODs, and SRC_REVNUM is a subversion
    revision number (int)."""

    raise NotImplementedError()

  def copy_path(self, src_path, dest_path, src_revnum):
    """Copy SRC_PATH in SRC_REVNUM to DEST_PATH.

    SRC_PATH and DEST_PATH are both SVN paths, and SRC_REVNUM is a
    subversion revision number (int)."""

    raise NotImplementedError()

  def finish(self):
    """All SVN revisions have been committed.

    Perform any necessary cleanup."""

    raise NotImplementedError()


