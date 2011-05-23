# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

"""This module contains the RepositoryMirror class and supporting classes.

RepositoryMirror represents the skeleton of a versioned file tree with
multiple lines of development ('LODs').  It records the presence or
absence of files and directories, but not their contents.  Given three
values (revnum, lod, cvs_path), it can tell you whether the specified
CVSPath existed on the specified LOD in the given revision number.
The file trees corresponding to the most recent revision can be
modified.

The individual file trees are stored using immutable tree structures.
Each directory node is represented as a MirrorDirectory instance,
which is basically a map {cvs_path : node_id}, where cvs_path is a
CVSPath within the directory, and node_id is an integer ID that
uniquely identifies another directory node if that node is a
CVSDirectory, or None if that node is a CVSFile.  If a directory node
is to be modified, then first a new node is created with a copy of the
original node's contents, then the copy is modified.  A reference to
the copy also has to be stored in the parent node, meaning that the
parent node needs to be modified, and so on recursively to the root
node of the file tree.  This data structure allows cheap deep copies,
which is useful for tagging and branching.

The class must also be able to find the root directory node
corresponding to a particular (revnum, lod).  This is done by keeping
an LODHistory instance for each LOD, which can determine the root
directory node ID for that LOD for any revnum.  It does so by
recording changes to the root directory node ID only for revisions in
which it changed.  Thus it stores two arrays, revnums (a list of the
revision numbers when the ID changed), and ids (a list of the
corresponding IDs).  To find the ID for a particular revnum, first a
binary search is done in the revnums array to find the index of the
last change preceding revnum, then the corresponding ID is read from
the ids array.  Since most revisions change only one LOD, this allows
storage of the history of potentially tens of thousands of LODs over
hundreds of thousands of revisions in an amount of space that scales
as O(numberOfLODs + numberOfRevisions), rather than O(numberOfLODs *
numberOfRevisions) as would be needed if the information were stored
in the equivalent of a 2D array.

The internal operation of these classes is somewhat intricate, but the
interface attempts to hide the complexity, enforce the usage rules,
and allow efficient access.  The most important facts to remember are
(1) that a directory node can be used for multiple purposes (for
multiple branches and for multiple revisions on a single branch), (2)
that only a node that has been created within the current revision is
allowed to be mutated, and (3) that the current revision can include
nodes carried over from prior revisions, which are immutable.

This leads to a bewildering variety of MirrorDirectory classes.  The
most important distinction is between OldMirrorDirectories and
CurrentMirrorDirectories.  A single node can be represented multiple
ways in memory at the same time, depending on whether it was looked up
as part of the current revision or part of an old revision:

    MirrorDirectory -- the base class for all MirrorDirectory nodes.
        This class allows lookup of subnodes and iteration over
        subnodes.

    OldMirrorDirectory -- a MirrorDirectory that was looked up for an
        old revision.  These instances are immutable, as only the
        current revision is allowed to be modified.

    CurrentMirrorDirectory -- a MirrorDirectory that was looked up for
        the current revision.  Such an instance is always logically
        mutable, though mutating it might require the node to be
        copied first.  Such an instance might represent a node that
        has already been copied during this revision and can therefore
        be modified freely (such nodes implement
        _WritableMirrorDirectoryMixin), or it might represent a node
        that was carried over from an old revision and hasn't been
        copied yet (such nodes implement
        _ReadOnlyMirrorDirectoryMixin).  If the latter, then the node
        copies itself (and bubbles up the change) before allowing
        itself to be modified.  But the distinction is managed
        internally; client classes should not have to worry about it.

    CurrentMirrorLODDirectory -- A CurrentMirrorDirectory representing
        the root directory of a line of development in the current
        revision.  This class has two concrete subclasses,
        _CurrentMirrorReadOnlyLODDirectory and
        _CurrentMirrorWritableLODDirectory, depending on whether the
        node has already been copied during this revision.


    CurrentMirrorSubdirectory -- A CurrentMirrorDirectory representing
        a subdirectory within a line of development's directory tree
        in the current revision.  This class has two concrete
        subclasses, _CurrentMirrorReadOnlySubdirectory and
        _CurrentMirrorWritableSubdirectory, depending on whether the
        node has already been copied during this revision.

    DeletedCurrentMirrorDirectory -- a MirrorDirectory that has been
        deleted.  Such an instance is disabled so that it cannot
        accidentally be used.

While a revision is being processed, RepositoryMirror._new_nodes holds
every writable CurrentMirrorDirectory instance (i.e., every node that
has been created in the revision).  Since these nodes are mutable, it
is important that there be exactly one instance associated with each
node; otherwise there would be problems keeping the instances
synchronized.  These are written to the database by
RepositoryMirror.end_commit().

OldMirrorDirectory and read-only CurrentMirrorDirectory instances are
*not* cached; they are recreated whenever they are referenced.  There
might be multiple instances referring to the same node.  A read-only
CurrentMirrorDirectory instance is mutated in place into a writable
CurrentMirrorDirectory instance if it needs to be modified.

FIXME: The rules for when a MirrorDirectory instance can continue to
be used vs. when it has to be read again (because it has been modified
indirectly and therefore copied) are confusing and error-prone.
Probably the semantics should be changed.

"""


import bisect

from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.cvs_path import CVSFile
from cvs2svn_lib.cvs_path import CVSDirectory
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.serializer import MarshalSerializer
from cvs2svn_lib.indexed_database import IndexedDatabase


class RepositoryMirrorError(Exception):
  """An error related to the RepositoryMirror."""

  pass


class LODExistsError(RepositoryMirrorError):
  """The LOD already exists in the repository.

  Exception raised if an attempt is made to add an LOD to the
  repository mirror and that LOD already exists in the youngest
  revision of the repository."""

  pass


class PathExistsError(RepositoryMirrorError):
  """The path already exists in the repository.

  Exception raised if an attempt is made to add a path to the
  repository mirror and that path already exists in the youngest
  revision of the repository."""

  pass


class DeletedNodeReusedError(RepositoryMirrorError):
  """The MirrorDirectory has already been deleted and shouldn't be reused."""

  pass


class CopyFromCurrentNodeError(RepositoryMirrorError):
  """A CurrentMirrorDirectory cannot be copied to the current revision."""

  pass


class MirrorDirectory(object):
  """Represent a node within the RepositoryMirror.

  Instances of this class act like a map {CVSPath : MirrorDirectory},
  where CVSPath is an item within this directory (i.e., a file or
  subdirectory within this directory).  The value is either another
  MirrorDirectory instance (for directories) or None (for files)."""

  def __init__(self, repo, id, entries):
    # The RepositoryMirror containing this directory:
    self.repo = repo

    # The id of this node:
    self.id = id

    # The entries within this directory, stored as a map {CVSPath :
    # node_id}.  The node_ids are integers for CVSDirectories, None
    # for CVSFiles:
    self._entries = entries

  def __getitem__(self, cvs_path):
    """Return the MirrorDirectory associated with the specified subnode.

    Return a MirrorDirectory instance if the subnode is a
    CVSDirectory; None if it is a CVSFile.  Raise KeyError if the
    specified subnode does not exist."""

    raise NotImplementedError()

  def __len__(self):
    """Return the number of CVSPaths within this node."""

    return len(self._entries)

  def __contains__(self, cvs_path):
    """Return True iff CVS_PATH is contained in this node."""

    return cvs_path in self._entries

  def __iter__(self):
    """Iterate over the CVSPaths within this node."""

    return self._entries.__iter__()

  def _format_entries(self):
    """Format the entries map for output in subclasses' __repr__() methods."""

    def format_item(key, value):
      if value is None:
        return str(key)
      else:
        return '%s -> %x' % (key, value,)

    items = self._entries.items()
    items.sort()
    return '{%s}' % (', '.join([format_item(*item) for item in items]),)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s<%x>' % (self.__class__.__name__, self.id,)


class OldMirrorDirectory(MirrorDirectory):
  """Represent a historical directory within the RepositoryMirror."""

  def __getitem__(self, cvs_path):
    id = self._entries[cvs_path]
    if id is None:
      # This represents a leaf node.
      return None
    else:
      return OldMirrorDirectory(self.repo, id, self.repo._node_db[id])

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s(%s)' % (self, self._format_entries(),)


class CurrentMirrorDirectory(MirrorDirectory):
  """Represent a directory that currently exists in the RepositoryMirror."""

  def __init__(self, repo, id, lod, cvs_path, entries):
    MirrorDirectory.__init__(self, repo, id, entries)
    self.lod = lod
    self.cvs_path = cvs_path

  def __getitem__(self, cvs_path):
    id = self._entries[cvs_path]
    if id is None:
      # This represents a leaf node.
      return None
    else:
      try:
        return self.repo._new_nodes[id]
      except KeyError:
        return _CurrentMirrorReadOnlySubdirectory(
            self.repo, id, self.lod, cvs_path, self,
            self.repo._node_db[id]
            )

  def __setitem__(self, cvs_path, node):
    """Create or overwrite a subnode of this node.

    CVS_PATH is the path of the subnode.  NODE will be the new value
    of the node; for CVSDirectories it should be a MirrorDirectory
    instance; for CVSFiles it should be None."""

    if isinstance(node, DeletedCurrentMirrorDirectory):
      raise DeletedNodeReusedError(
          '%r has already been deleted and should not be reused' % (node,)
          )
    elif isinstance(node, CurrentMirrorDirectory):
      raise CopyFromCurrentNodeError(
          '%r was created in the current node and cannot be copied' % (node,)
          )
    else:
      self._set_entry(cvs_path, node)

  def __delitem__(self, cvs_path):
    """Remove the subnode of this node at CVS_PATH.

    If the node does not exist, then raise a KeyError."""

    node = self[cvs_path]
    self._del_entry(cvs_path)
    if isinstance(node, _WritableMirrorDirectoryMixin):
      node._mark_deleted()

  def mkdir(self, cvs_directory):
    """Create an empty subdirectory of this node at CVS_PATH.

    Return the CurrentDirectory that was created."""

    assert isinstance(cvs_directory, CVSDirectory)
    if cvs_directory in self:
      raise PathExistsError(
          'Attempt to create directory \'%s\' in %s in repository mirror '
          'when it already exists.'
          % (cvs_directory, self.lod,)
          )

    new_node = _CurrentMirrorWritableSubdirectory(
        self.repo, self.repo._key_generator.gen_id(), self.lod, cvs_directory,
        self, {}
        )
    self._set_entry(cvs_directory, new_node)
    self.repo._new_nodes[new_node.id] = new_node
    return new_node

  def add_file(self, cvs_file):
    """Create a file within this node at CVS_FILE."""

    assert isinstance(cvs_file, CVSFile)
    if cvs_file in self:
      raise PathExistsError(
          'Attempt to create file \'%s\' in %s in repository mirror '
          'when it already exists.'
          % (cvs_file, self.lod,)
          )

    self._set_entry(cvs_file, None)

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s(%r, %r, %s)' % (
        self, self.lod, self.cvs_path, self._format_entries(),
        )


class DeletedCurrentMirrorDirectory(object):
  """A MirrorDirectory that has been deleted.

  A MirrorDirectory that used to be a _WritableMirrorDirectoryMixin
  but then was deleted.  Such instances are turned into this class so
  that nobody can accidentally mutate them again."""

  pass


class _WritableMirrorDirectoryMixin:
  """Mixin for MirrorDirectories that are already writable.

  A MirrorDirectory is writable if it has already been recreated
  during the current revision."""

  def _set_entry(self, cvs_path, node):
    """Create or overwrite a subnode of this node, with no checks."""

    if node is None:
      self._entries[cvs_path] = None
    else:
      self._entries[cvs_path] = node.id

  def _del_entry(self, cvs_path):
    """Remove the subnode of this node at CVS_PATH, with no checks."""

    del self._entries[cvs_path]

  def _mark_deleted(self):
    """Mark this object and any writable descendants as being deleted."""

    self.__class__ = DeletedCurrentMirrorDirectory

    for (cvs_path, id) in self._entries.iteritems():
      if id in self.repo._new_nodes:
        node = self[cvs_path]
        if isinstance(node, _WritableMirrorDirectoryMixin):
          # Mark deleted and recurse:
          node._mark_deleted()


class _ReadOnlyMirrorDirectoryMixin:
  """Mixin for a CurrentMirrorDirectory that hasn't yet been made writable."""

  def _make_writable(self):
    raise NotImplementedError()

  def _set_entry(self, cvs_path, node):
    """Create or overwrite a subnode of this node, with no checks."""

    self._make_writable()
    self._set_entry(cvs_path, node)

  def _del_entry(self, cvs_path):
    """Remove the subnode of this node at CVS_PATH, with no checks."""

    self._make_writable()
    self._del_entry(cvs_path)


class CurrentMirrorLODDirectory(CurrentMirrorDirectory):
  """Represent an LOD's main directory in the mirror's current version."""

  def __init__(self, repo, id, lod, entries):
    CurrentMirrorDirectory.__init__(
        self, repo, id, lod, lod.project.get_root_cvs_directory(), entries
        )

  def delete(self):
    """Remove the directory represented by this object."""

    lod_history = self.repo._get_lod_history(self.lod)
    assert lod_history.exists()
    lod_history.update(self.repo._youngest, None)
    self._mark_deleted()


class _CurrentMirrorReadOnlyLODDirectory(
          CurrentMirrorLODDirectory, _ReadOnlyMirrorDirectoryMixin
          ):
  """Represent an LOD's main directory in the mirror's current version."""

  def _make_writable(self):
    self.__class__ = _CurrentMirrorWritableLODDirectory
    # Create a new ID:
    self.id = self.repo._key_generator.gen_id()
    self.repo._new_nodes[self.id] = self
    self.repo._get_lod_history(self.lod).update(self.repo._youngest, self.id)
    self._entries = self._entries.copy()


class _CurrentMirrorWritableLODDirectory(
          CurrentMirrorLODDirectory, _WritableMirrorDirectoryMixin
          ):
  pass


class CurrentMirrorSubdirectory(CurrentMirrorDirectory):
  """Represent a subdirectory in the mirror's current version."""

  def __init__(self, repo, id, lod, cvs_path, parent_mirror_dir, entries):
    CurrentMirrorDirectory.__init__(self, repo, id, lod, cvs_path, entries)
    self.parent_mirror_dir = parent_mirror_dir

  def delete(self):
    """Remove the directory represented by this object."""

    del self.parent_mirror_dir[self.cvs_path]


class _CurrentMirrorReadOnlySubdirectory(
          CurrentMirrorSubdirectory, _ReadOnlyMirrorDirectoryMixin
          ):
  """Represent a subdirectory in the mirror's current version."""

  def _make_writable(self):
    self.__class__ = _CurrentMirrorWritableSubdirectory
    # Create a new ID:
    self.id = self.repo._key_generator.gen_id()
    self.repo._new_nodes[self.id] = self
    self.parent_mirror_dir._set_entry(self.cvs_path, self)
    self._entries = self._entries.copy()


class _CurrentMirrorWritableSubdirectory(
          CurrentMirrorSubdirectory, _WritableMirrorDirectoryMixin
          ):
  pass


class LODHistory(object):
  """The history of root nodes for a line of development.

  Members:

    _mirror -- (RepositoryMirror) the RepositoryMirror that manages
        this LODHistory.

    lod -- (LineOfDevelopment) the LOD described by this LODHistory.

    revnums -- (list of int) the revision numbers in which the id
        changed, in numerical order.

    ids -- (list of (int or None)) the ID of the node describing the
        root of this LOD starting at the corresponding revision
        number, or None if the LOD did not exist in that revision.

  To find the root id for a given revision number, a binary search is
  done within REVNUMS to find the index of the most recent revision at
  the time of REVNUM, then that index is used to read the id out of
  IDS.

  A sentry is written at the zeroth index of both arrays to describe
  the initial situation, namely, that the LOD doesn't exist in
  revision r0."""

  __slots__ = ['_mirror', 'lod', 'revnums', 'ids']

  def __init__(self, mirror, lod):
    self._mirror = mirror
    self.lod = lod
    self.revnums = [0]
    self.ids = [None]

  def get_id(self, revnum):
    """Get the ID of the root path for this LOD in REVNUM.

    Raise KeyError if this LOD didn't exist in REVNUM."""

    index = bisect.bisect_right(self.revnums, revnum) - 1
    id = self.ids[index]

    if id is None:
      raise KeyError(revnum)

    return id

  def get_current_id(self):
    """Get the ID of the root path for this LOD in the current revision.

    Raise KeyError if this LOD doesn't currently exist."""

    id = self.ids[-1]

    if id is None:
      raise KeyError()

    return id

  def exists(self):
    """Return True iff LOD exists in the current revision."""

    return self.ids[-1] is not None

  def update(self, revnum, id):
    """Indicate that the root node of this LOD changed to ID at REVNUM.

    REVNUM is a revision number that must be the same as that of the
    previous recorded change (in which case the previous change is
    overwritten) or later (in which the new change is appended).

    ID can be a node ID, or it can be None to indicate that this LOD
    ceased to exist in REVNUM."""

    if revnum < self.revnums[-1]:
      raise KeyError(revnum)
    elif revnum == self.revnums[-1]:
      # This is an attempt to overwrite an entry that was already
      # updated during this revision.  Don't allow the replacement
      # None -> None or allow one new id to be replaced with another:
      old_id = self.ids[-1]
      if old_id is None and id is None:
        raise InternalError(
            'ID changed from None -> None for %s, r%d' % (self.lod, revnum,)
            )
      elif (old_id is not None and id is not None
            and old_id in self._mirror._new_nodes):
        raise InternalError(
            'ID changed from %x -> %x for %s, r%d'
            % (old_id, id, self.lod, revnum,)
            )
      self.ids[-1] = id
    else:
      self.revnums.append(revnum)
      self.ids.append(id)


class _NodeDatabase(object):
  """A database storing all of the directory nodes.

  The nodes are written in groups every time write_new_nodes() is
  called.  To the database is written a dictionary {node_id :
  [(cvs_path.id, node_id),...]}, where the keys are the node_ids of
  the new nodes.  When a node is read, its whole group is read and
  cached under the assumption that the other nodes in the group are
  likely to be needed soon.  The cache is retained across revisions
  and cleared when _cache_max_size is exceeded.

  The dictionaries for nodes that have been read from the database
  during the current revision are cached by node_id in the _cache
  member variable.  The corresponding dictionaries are *not* copied
  when read.  To avoid cross-talk between distinct MirrorDirectory
  instances that have the same node_id, users of these dictionaries
  have to copy them before modification."""

  # How many entries should be allowed in the cache for each
  # CVSDirectory in the repository.  (This number is very roughly the
  # number of complete lines of development that can be stored in the
  # cache at one time.)
  CACHE_SIZE_MULTIPLIER = 5

  # But the cache will never be limited to less than this number:
  MIN_CACHE_LIMIT = 5000

  def __init__(self):
    self.cvs_path_db = Ctx()._cvs_path_db
    self.db = IndexedDatabase(
        artifact_manager.get_temp_file(config.MIRROR_NODES_STORE),
        artifact_manager.get_temp_file(config.MIRROR_NODES_INDEX_TABLE),
        DB_OPEN_NEW, serializer=MarshalSerializer(),
        )

    # A list of the maximum node_id stored by each call to
    # write_new_nodes():
    self._max_node_ids = [0]

    # A map {node_id : {cvs_path : node_id}}:
    self._cache = {}

    # The number of directories in the repository:
    num_dirs = len([
        cvs_path
        for cvs_path in self.cvs_path_db.itervalues()
        if isinstance(cvs_path, CVSDirectory)
        ])

    self._cache_max_size = max(
        int(self.CACHE_SIZE_MULTIPLIER * num_dirs),
        self.MIN_CACHE_LIMIT,
        )

  def _load(self, items):
    retval = {}
    for (id, value) in items:
      retval[self.cvs_path_db.get_path(id)] = value
    return retval

  def _dump(self, node):
    return [
        (cvs_path.id, value)
        for (cvs_path, value) in node.iteritems()
        ]

  def _determine_index(self, id):
    """Return the index of the record holding the node with ID."""

    return bisect.bisect_left(self._max_node_ids, id)

  def __getitem__(self, id):
    try:
      items = self._cache[id]
    except KeyError:
      index = self._determine_index(id)
      for (node_id, items) in self.db[index].items():
        self._cache[node_id] = self._load(items)
      items = self._cache[id]

    return items

  def write_new_nodes(self, nodes):
    """Write NODES to the database.

    NODES is an iterable of writable CurrentMirrorDirectory instances."""

    if len(self._cache) > self._cache_max_size:
      # The size of the cache has exceeded the threshold.  Discard the
      # old cache values (but still store the new nodes into the
      # cache):
      logger.debug('Clearing node cache')
      self._cache.clear()

    data = {}
    max_node_id = 0
    for node in nodes:
      max_node_id = max(max_node_id, node.id)
      data[node.id] = self._dump(node._entries)
      self._cache[node.id] = node._entries

    self.db[len(self._max_node_ids)] = data

    if max_node_id == 0:
      # Rewrite last value:
      self._max_node_ids.append(self._max_node_ids[-1])
    else:
      self._max_node_ids.append(max_node_id)

  def close(self):
    self._cache.clear()
    self.db.close()
    self.db = None


class RepositoryMirror:
  """Mirror a repository and its history.

  Mirror a repository as it is constructed, one revision at a time.
  For each LineOfDevelopment we store a skeleton of the directory
  structure within that LOD for each revnum in which it changed.

  For each LOD that has been seen so far, an LODHistory instance is
  stored in self._lod_histories.  An LODHistory keeps track of each
  revnum in which files were added to or deleted from that LOD, as
  well as the node id of the root of the node tree describing the LOD
  contents at that revision.

  The LOD trees themselves are stored in the _node_db database, which
  maps node ids to nodes.  A node is a map from CVSPath to ids of the
  corresponding subnodes.  The _node_db is stored on disk and each
  access is expensive.

  The _node_db database only holds the nodes for old revisions.  The
  revision that is being constructed is kept in memory in the
  _new_nodes map, which is cheap to access.

  You must invoke start_commit() before each commit and end_commit()
  afterwards."""

  def register_artifacts(self, which_pass):
    """Register the artifacts that will be needed for this object."""

    artifact_manager.register_temp_file(
        config.MIRROR_NODES_INDEX_TABLE, which_pass
        )
    artifact_manager.register_temp_file(
        config.MIRROR_NODES_STORE, which_pass
        )

  def open(self):
    """Set up the RepositoryMirror and prepare it for commits."""

    self._key_generator = KeyGenerator()

    # A map from LOD to LODHistory instance for all LODs that have
    # been referenced so far:
    self._lod_histories = {}

    # This corresponds to the 'nodes' table in a Subversion fs.  (We
    # don't need a 'representations' or 'strings' table because we
    # only track file existence, not file contents.)
    self._node_db = _NodeDatabase()

    # Start at revision 0 without a root node.
    self._youngest = 0

  def start_commit(self, revnum):
    """Start a new commit."""

    assert revnum > self._youngest
    self._youngest = revnum

    # A map {node_id : _WritableMirrorDirectoryMixin}.
    self._new_nodes = {}

  def end_commit(self):
    """Called at the end of each commit.

    This method copies the newly created nodes to the on-disk nodes
    db."""

    # Copy the new nodes to the _node_db
    self._node_db.write_new_nodes([
        node
        for node in self._new_nodes.values()
        if not isinstance(node, DeletedCurrentMirrorDirectory)
        ])

    del self._new_nodes

  def _get_lod_history(self, lod):
    """Return the LODHistory instance describing LOD.

    Create a new (empty) LODHistory if it doesn't yet exist."""

    try:
      return self._lod_histories[lod]
    except KeyError:
      lod_history = LODHistory(self, lod)
      self._lod_histories[lod] = lod_history
      return lod_history

  def get_old_lod_directory(self, lod, revnum):
    """Return the directory for the root path of LOD at revision REVNUM.

    Return an instance of MirrorDirectory if the path exists;
    otherwise, raise KeyError."""

    lod_history = self._get_lod_history(lod)
    id = lod_history.get_id(revnum)
    return OldMirrorDirectory(self, id, self._node_db[id])

  def get_old_path(self, cvs_path, lod, revnum):
    """Return the node for CVS_PATH from LOD at REVNUM.

    If CVS_PATH is a CVSDirectory, then return an instance of
    OldMirrorDirectory.  If CVS_PATH is a CVSFile, return None.

    If CVS_PATH does not exist in the specified LOD and REVNUM, raise
    KeyError."""

    node = self.get_old_lod_directory(lod, revnum)

    for sub_path in cvs_path.get_ancestry()[1:]:
      node = node[sub_path]

    return node

  def get_current_lod_directory(self, lod):
    """Return the directory for the root path of LOD in the current revision.

    Return an instance of CurrentMirrorDirectory.  Raise KeyError if
    the path doesn't already exist."""

    lod_history = self._get_lod_history(lod)
    id = lod_history.get_current_id()
    try:
      return self._new_nodes[id]
    except KeyError:
      return _CurrentMirrorReadOnlyLODDirectory(
          self, id, lod, self._node_db[id]
          )

  def get_current_path(self, cvs_path, lod):
    """Return the node for CVS_PATH from LOD in the current revision.

    If CVS_PATH is a CVSDirectory, then return an instance of
    CurrentMirrorDirectory.  If CVS_PATH is a CVSFile, return None.

    If CVS_PATH does not exist in the current revision of the
    specified LOD, raise KeyError."""

    node = self.get_current_lod_directory(lod)

    for sub_path in cvs_path.get_ancestry()[1:]:
      node = node[sub_path]

    return node

  def add_lod(self, lod):
    """Create a new LOD in this repository.

    Return the CurrentMirrorDirectory that was created.  If the LOD
    already exists, raise LODExistsError."""

    lod_history = self._get_lod_history(lod)
    if lod_history.exists():
      raise LODExistsError(
          'Attempt to create %s in repository mirror when it already exists.'
          % (lod,)
          )
    new_node = _CurrentMirrorWritableLODDirectory(
        self, self._key_generator.gen_id(), lod, {}
        )
    lod_history.update(self._youngest, new_node.id)
    self._new_nodes[new_node.id] = new_node
    return new_node

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy all of SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination LOD
    *must not* already exist.

    Return the new node at DEST_LOD, as a CurrentMirrorDirectory."""

    # Get the node of our src_path
    src_node = self.get_old_lod_directory(src_lod, src_revnum)

    dest_lod_history = self._get_lod_history(dest_lod)
    if dest_lod_history.exists():
      raise LODExistsError(
          'Attempt to copy to %s in repository mirror when it already exists.'
          % (dest_lod,)
          )

    dest_lod_history.update(self._youngest, src_node.id)

    # Return src_node, except packaged up as a CurrentMirrorDirectory:
    return self.get_current_lod_directory(dest_lod)

  def close(self):
    """Free resources and close databases."""

    self._lod_histories = None
    self._node_db.close()
    self._node_db = None


