# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

"""This module contains classes to store atomic CVS events.

A CVSItem is a single event, pertaining to a single file, that can be
determined to have occured based on the information in the CVS
repository.

The inheritance tree is as follows:

CVSItem
|
+--CVSRevision
|  |
|  +--CVSRevisionModification (* -> 'Exp')
|  |  |
|  |  +--CVSRevisionAdd ('dead' -> 'Exp')
|  |  |
|  |  +--CVSRevisionChange ('Exp' -> 'Exp')
|  |
|  +--CVSRevisionAbsent (* -> 'dead')
|     |
|     +--CVSRevisionDelete ('Exp' -> 'dead')
|     |
|     +--CVSRevisionNoop ('dead' -> 'dead')
|
+--CVSSymbol
   |
   +--CVSBranch
   |  |
   |  +--CVSBranchNoop
   |
   +--CVSTag
      |
      +--CVSTagNoop

"""


from cvs2svn_lib.context import Ctx


class CVSItem(object):
  __slots__ = [
      'id',
      'cvs_file',
      'revision_reader_token',
      ]

  def __init__(self, id, cvs_file, revision_reader_token):
    self.id = id
    self.cvs_file = cvs_file
    self.revision_reader_token = revision_reader_token

  def __eq__(self, other):
    return self.id == other.id

  def __cmp__(self, other):
    return cmp(self.id, other.id)

  def __hash__(self):
    return self.id

  def __getstate__(self):
    raise NotImplementedError()

  def __setstate__(self, data):
    raise NotImplementedError()

  def get_svn_path(self):
    """Return the SVN path associated with this CVSItem."""

    raise NotImplementedError()

  def get_pred_ids(self):
    """Return the CVSItem.ids of direct predecessors of SELF.

    A predecessor is defined to be a CVSItem that has to have been
    committed before this one."""

    raise NotImplementedError()

  def get_succ_ids(self):
    """Return the CVSItem.ids of direct successors of SELF.

    A direct successor is defined to be a CVSItem that has this one as
    a direct predecessor."""

    raise NotImplementedError()

  def get_cvs_symbol_ids_opened(self):
    """Return an iterable over the ids of CVSSymbols that this item opens.

    The definition of 'open' is that the path corresponding to this
    CVSItem will have to be copied when filling the corresponding
    symbol."""

    raise NotImplementedError()

  def get_ids_closed(self):
    """Return an iterable over the CVSItem.ids of CVSItems closed by this one.

    A CVSItem A is said to close a CVSItem B if committing A causes B
    to be overwritten or deleted (no longer available) in the SVN
    repository.  This is interesting because it sets the last SVN
    revision number from which the contents of B can be copied (for
    example, to fill a symbol).  See the concrete implementations of
    this method for the exact rules about what closes what."""

    raise NotImplementedError()

  def check_links(self, cvs_file_items):
    """Check for consistency of links to other CVSItems.

    Other items can be looked up in CVS_FILE_ITEMS, which is an
    instance of CVSFileItems.  Raise an AssertionError if there is a
    problem."""

    raise NotImplementedError()

  def __repr__(self):
    return '%s(%s)' % (self.__class__.__name__, self,)


class CVSRevision(CVSItem):
  """Information about a single CVS revision.

  A CVSRevision holds the information known about a single version of
  a single file.

  Members:

    id -- (int) unique ID for this revision.

    cvs_file -- (CVSFile) CVSFile affected by this revision.

    timestamp -- (int) date stamp for this revision.

    metadata_id -- (int) id of metadata instance record in
        metadata_db.

    prev_id -- (int) id of the logically previous CVSRevision, either
        on the same or the source branch (or None).

    next_id -- (int) id of the logically next CVSRevision (or None).

    rev -- (string) the CVS revision number, e.g., '1.3'.

    deltatext_exists -- (bool) true iff this revision's deltatext is
        not empty.

    lod -- (LineOfDevelopment) LOD on which this revision occurred.

    first_on_branch_id -- (int or None) if this revision is the first
        on its branch, the cvs_branch_id of that branch; else, None.

    ntdbr -- (bool) true iff this is a non-trunk default branch
        revision.

    ntdbr_prev_id -- (int or None) Iff this is the 1.2 revision after
        the end of a default branch, the id of the last rev on the
        default branch; else, None.

    ntdbr_next_id -- (int or None) Iff this is the last revision on a
        default branch preceding a 1.2 rev, the id of the 1.2
        revision; else, None.

    tag_ids -- (list of int) ids of all CVSTags rooted at this
        CVSRevision.

    branch_ids -- (list of int) ids of all CVSBranches rooted at this
        CVSRevision.

    branch_commit_ids -- (list of int) ids of first CVSRevision
        committed on each branch rooted in this revision (for branches
        with commits).

    opened_symbols -- (None or list of (symbol_id, cvs_symbol_id)
        tuples) information about all CVSSymbols opened by this
        revision.  This member is set in FilterSymbolsPass; before
        then, it is None.

    closed_symbols -- (None or list of (symbol_id, cvs_symbol_id)
        tuples) information about all CVSSymbols closed by this
        revision.  This member is set in FilterSymbolsPass; before
        then, it is None.

    properties -- (dict) the file properties that vary from revision
        to revision.  The get_properties() method combines the
        properties found in SELF.cvs_file.properties with those here;
        the latter take precedence.  Keys are strings.  Values are
        strings (indicating the property value) or None (indicating
        that the property should be left unset, even if it is set in
        SELF.cvs_file.properties).  Different backends can use
        properties for different purposes; for cvs2svn these become
        SVN versioned properties.  Properties whose names start with
        underscore are reserved for internal cvs2svn purposes.

    properties_changed -- (None or bool) Will this CVSRevision's
        get_properties() method return a different value than the same
        call of the predecessor revision?

    revision_reader_token -- (arbitrary) a token that can be set by
        RevisionCollector for the later use of RevisionReader.

  """

  __slots__ = [
      'timestamp',
      'metadata_id',
      'prev_id',
      'next_id',
      'rev',
      'deltatext_exists',
      'lod',
      'first_on_branch_id',
      'ntdbr',
      'ntdbr_prev_id',
      'ntdbr_next_id',
      'tag_ids',
      'branch_ids',
      'branch_commit_ids',
      'opened_symbols',
      'closed_symbols',
      'properties',
      'properties_changed',
      ]

  def __init__(
        self,
        id, cvs_file,
        timestamp, metadata_id,
        prev_id, next_id,
        rev, deltatext_exists,
        lod, first_on_branch_id, ntdbr,
        ntdbr_prev_id, ntdbr_next_id,
        tag_ids, branch_ids, branch_commit_ids,
        revision_reader_token,
        ):
    """Initialize a new CVSRevision object."""

    CVSItem.__init__(self, id, cvs_file, revision_reader_token)

    self.timestamp = timestamp
    self.metadata_id = metadata_id
    self.prev_id = prev_id
    self.next_id = next_id
    self.rev = rev
    self.deltatext_exists = deltatext_exists
    self.lod = lod
    self.first_on_branch_id = first_on_branch_id
    self.ntdbr = ntdbr
    self.ntdbr_prev_id = ntdbr_prev_id
    self.ntdbr_next_id = ntdbr_next_id
    self.tag_ids = tag_ids
    self.branch_ids = branch_ids
    self.branch_commit_ids = branch_commit_ids
    self.opened_symbols = None
    self.closed_symbols = None
    self.properties = None
    self.properties_changed = None

  def _get_cvs_path(self):
    return self.cvs_file.cvs_path

  cvs_path = property(_get_cvs_path)

  def get_svn_path(self):
    return self.lod.get_path(self.cvs_file.cvs_path)

  def __getstate__(self):
    """Return the contents of this instance, for pickling.

    The presence of this method improves the space efficiency of
    pickling CVSRevision instances."""

    return (
        self.id, self.cvs_file.id,
        self.timestamp, self.metadata_id,
        self.prev_id, self.next_id,
        self.rev,
        self.deltatext_exists,
        self.lod.id,
        self.first_on_branch_id,
        self.ntdbr,
        self.ntdbr_prev_id, self.ntdbr_next_id,
        self.tag_ids, self.branch_ids, self.branch_commit_ids,
        self.opened_symbols, self.closed_symbols,
        self.properties, self.properties_changed,
        self.revision_reader_token,
        )

  def __setstate__(self, data):
    (self.id, cvs_file_id,
     self.timestamp, self.metadata_id,
     self.prev_id, self.next_id,
     self.rev,
     self.deltatext_exists,
     lod_id,
     self.first_on_branch_id,
     self.ntdbr,
     self.ntdbr_prev_id, self.ntdbr_next_id,
     self.tag_ids, self.branch_ids, self.branch_commit_ids,
     self.opened_symbols, self.closed_symbols,
     self.properties, self.properties_changed,
     self.revision_reader_token) = data
    self.cvs_file = Ctx()._cvs_path_db.get_path(cvs_file_id)
    self.lod = Ctx()._symbol_db.get_symbol(lod_id)

  def get_properties(self):
    """Return all of the properties needed for this CVSRevision.

    Combine SELF.cvs_file.properties and SELF.properties to get the
    final properties needed for this CVSRevision.  (The properties in
    SELF have precedence.)  Return the properties as a map {key :
    value}, where keys and values are both strings.  (Entries with
    value == None are omitted.)  Different backends can use properties
    for different purposes; for cvs2svn these become SVN versioned
    properties.  Properties whose names start with underscore are
    reserved for internal cvs2svn purposes."""

    properties = self.cvs_file.properties.copy()
    properties.update(self.properties)

    for (k,v) in properties.items():
      if v is None:
        del properties[k]

    return properties

  def get_property(self, name, default=None):
    """Return a particular property for this CVSRevision.

    This is logically the same as SELF.get_properties().get(name,
    default) but implemented more efficiently."""

    if name in self.properties:
      return self.properties[name]
    else:
      return self.cvs_file.properties.get(name, default)

  def get_effective_prev_id(self):
    """Return the ID of the effective predecessor of this item.

    This is the ID of the item that determines whether the object
    existed before this CVSRevision."""

    if self.ntdbr_prev_id is not None:
      return self.ntdbr_prev_id
    else:
      return self.prev_id

  def get_symbol_pred_ids(self):
    """Return the pred_ids for symbol predecessors."""

    retval = set()
    if self.first_on_branch_id is not None:
      retval.add(self.first_on_branch_id)
    return retval

  def get_pred_ids(self):
    retval = self.get_symbol_pred_ids()
    if self.prev_id is not None:
      retval.add(self.prev_id)
    if self.ntdbr_prev_id is not None:
      retval.add(self.ntdbr_prev_id)
    return retval

  def get_symbol_succ_ids(self):
    """Return the succ_ids for symbol successors."""

    retval = set()
    for id in self.branch_ids + self.tag_ids:
      retval.add(id)
    return retval

  def get_succ_ids(self):
    retval = self.get_symbol_succ_ids()
    if self.next_id is not None:
      retval.add(self.next_id)
    if self.ntdbr_next_id is not None:
      retval.add(self.ntdbr_next_id)
    for id in self.branch_commit_ids:
      retval.add(id)
    return retval

  def get_ids_closed(self):
    # Special handling is needed in the case of non-trunk default
    # branches.  The following cases have to be handled:
    #
    # Case 1: Revision 1.1 not deleted; revision 1.2 exists:
    #
    #         1.1 -----------------> 1.2
    #           \    ^          ^    /
    #            \   |          |   /
    #             1.1.1.1 -> 1.1.1.2
    #
    # * 1.1.1.1 closes 1.1 (because its post-commit overwrites 1.1
    #   on trunk)
    #
    # * 1.1.1.2 closes 1.1.1.1
    #
    # * 1.2 doesn't close anything (the post-commit from 1.1.1.1
    #   already closed 1.1, and no symbols can sprout from the
    #   post-commit of 1.1.1.2)
    #
    # Case 2: Revision 1.1 not deleted; revision 1.2 does not exist:
    #
    #         1.1 ..................
    #           \    ^          ^
    #            \   |          |
    #             1.1.1.1 -> 1.1.1.2
    #
    # * 1.1.1.1 closes 1.1 (because its post-commit overwrites 1.1
    #   on trunk)
    #
    # * 1.1.1.2 closes 1.1.1.1
    #
    # Case 3: Revision 1.1 deleted; revision 1.2 exists:
    #
    #                ............... 1.2
    #                ^          ^    /
    #                |          |   /
    #             1.1.1.1 -> 1.1.1.2
    #
    # * 1.1.1.1 doesn't close anything
    #
    # * 1.1.1.2 closes 1.1.1.1
    #
    # * 1.2 doesn't close anything (no symbols can sprout from the
    #   post-commit of 1.1.1.2)
    #
    # Case 4: Revision 1.1 deleted; revision 1.2 doesn't exist:
    #
    #                ...............
    #                ^          ^
    #                |          |
    #             1.1.1.1 -> 1.1.1.2
    #
    # * 1.1.1.1 doesn't close anything
    #
    # * 1.1.1.2 closes 1.1.1.1

    if self.first_on_branch_id is not None:
      # The first CVSRevision on a branch is considered to close the
      # branch:
      yield self.first_on_branch_id
      if self.ntdbr:
        # If the 1.1 revision was not deleted, the 1.1.1.1 revision is
        # considered to close it:
        yield self.prev_id
    elif self.ntdbr_prev_id is not None:
      # This is the special case of a 1.2 revision that follows a
      # non-trunk default branch.  Either 1.1 was deleted or the first
      # default branch revision closed 1.1, so we don't have to close
      # 1.1.  Technically, we close the revision on trunk that was
      # copied from the last non-trunk default branch revision in a
      # post-commit, but for now no symbols can sprout from that
      # revision so we ignore that one, too.
      pass
    elif self.prev_id is not None:
      # Since this CVSRevision is not the first on a branch, its
      # prev_id is on the same LOD and this item closes that one:
      yield self.prev_id

  def _get_branch_ids_recursively(self, cvs_file_items):
    """Return the set of all CVSBranches that sprout from this CVSRevision.

    After parent adjustment in FilterSymbolsPass, it is possible for
    branches to sprout directly from a CVSRevision, or from those
    branches, etc.  Return all branches that sprout from this
    CVSRevision, directly or indirectly."""

    retval = set()
    branch_ids_to_process = list(self.branch_ids)
    while branch_ids_to_process:
      branch = cvs_file_items[branch_ids_to_process.pop()]
      retval.add(branch)
      branch_ids_to_process.extend(branch.branch_ids)

    return retval

  def check_links(self, cvs_file_items):
    assert self.cvs_file == cvs_file_items.cvs_file

    prev = cvs_file_items.get(self.prev_id)
    next = cvs_file_items.get(self.next_id)
    first_on_branch = cvs_file_items.get(self.first_on_branch_id)
    ntdbr_next = cvs_file_items.get(self.ntdbr_next_id)
    ntdbr_prev = cvs_file_items.get(self.ntdbr_prev_id)
    effective_prev = cvs_file_items.get(self.get_effective_prev_id())

    if prev is None:
      # This is the first CVSRevision on trunk or a detached branch:
      assert self.id in cvs_file_items.root_ids
    elif first_on_branch is not None:
      # This is the first CVSRevision on an existing branch:
      assert isinstance(first_on_branch, CVSBranch)
      assert first_on_branch.symbol == self.lod
      assert first_on_branch.next_id == self.id
      cvs_revision_source = first_on_branch.get_cvs_revision_source(
          cvs_file_items
          )
      assert cvs_revision_source.id == prev.id
      assert self.id in prev.branch_commit_ids
    else:
      # This revision follows another revision on the same LOD:
      assert prev.next_id == self.id
      assert prev.lod == self.lod

    if next is not None:
      assert next.prev_id == self.id
      assert next.lod == self.lod

    if ntdbr_next is not None:
      assert self.ntdbr
      assert ntdbr_next.ntdbr_prev_id == self.id

    if ntdbr_prev is not None:
      assert ntdbr_prev.ntdbr_next_id == self.id

    for tag_id in self.tag_ids:
      tag = cvs_file_items[tag_id]
      assert isinstance(tag, CVSTag)
      assert tag.source_id == self.id
      assert tag.source_lod == self.lod

    for branch_id in self.branch_ids:
      branch = cvs_file_items[branch_id]
      assert isinstance(branch, CVSBranch)
      assert branch.source_id == self.id
      assert branch.source_lod == self.lod

    branch_commit_ids = list(self.branch_commit_ids)

    for branch in self._get_branch_ids_recursively(cvs_file_items):
      assert isinstance(branch, CVSBranch)
      if branch.next_id is not None:
        assert branch.next_id in branch_commit_ids
        branch_commit_ids.remove(branch.next_id)

    assert not branch_commit_ids

    assert self.__class__ == cvs_revision_type_map[(
        isinstance(self, CVSRevisionModification),
        effective_prev is not None
            and isinstance(effective_prev, CVSRevisionModification),
        )]

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' % (self.cvs_file, self.rev, self.id,)


class CVSRevisionModification(CVSRevision):
  """Base class for CVSRevisionAdd or CVSRevisionChange."""

  __slots__ = []

  def get_cvs_symbol_ids_opened(self):
    return self.tag_ids + self.branch_ids


class CVSRevisionAdd(CVSRevisionModification):
  """A CVSRevision that creates a file that previously didn't exist.

  The file might have never existed on this LOD, or it might have
  existed previously but been deleted by a CVSRevisionDelete."""

  __slots__ = []


class CVSRevisionChange(CVSRevisionModification):
  """A CVSRevision that modifies a file that already existed on this LOD."""

  __slots__ = []


class CVSRevisionAbsent(CVSRevision):
  """A CVSRevision for which the file is nonexistent on this LOD."""

  __slots__ = []

  def get_cvs_symbol_ids_opened(self):
    return []


class CVSRevisionDelete(CVSRevisionAbsent):
  """A CVSRevision that deletes a file that existed on this LOD."""

  __slots__ = []


class CVSRevisionNoop(CVSRevisionAbsent):
  """A CVSRevision that doesn't do anything.

  The revision was 'dead' and the predecessor either didn't exist or
  was also 'dead'.  These revisions can't necessarily be thrown away
  because (1) they impose ordering constraints on other items; (2)
  they might have a nontrivial log message that we don't want to throw
  away."""

  __slots__ = []


# A map
#
#   {(nondead(cvs_rev), nondead(prev_cvs_rev)) : cvs_revision_subtype}
#
# , where nondead() means that the cvs revision exists and is not
# 'dead', and CVS_REVISION_SUBTYPE is the subtype of CVSRevision that
# should be used for CVS_REV.
cvs_revision_type_map = {
    (False, False) : CVSRevisionNoop,
    (False, True) : CVSRevisionDelete,
    (True, False) : CVSRevisionAdd,
    (True, True) : CVSRevisionChange,
    }


class CVSSymbol(CVSItem):
  """Represent a symbol on a particular CVSFile.

  This is the base class for CVSBranch and CVSTag.

  Members:

    id -- (int) unique ID for this item.

    cvs_file -- (CVSFile) CVSFile affected by this item.

    symbol -- (Symbol) the symbol affected by this CVSSymbol.

    source_lod -- (LineOfDevelopment) the LOD that is the source for
        this CVSSymbol.

    source_id -- (int) the ID of the CVSRevision or CVSBranch that is
        the source for this item.  This initially points to a
        CVSRevision, but can be changed to a CVSBranch via parent
        adjustment in FilterSymbolsPass.

    revision_reader_token -- (arbitrary) a token that can be set by
        RevisionCollector for the later use of RevisionReader.

  """

  __slots__ = [
      'symbol',
      'source_lod',
      'source_id',
      ]

  def __init__(
      self, id, cvs_file, symbol, source_lod, source_id,
      revision_reader_token,
      ):
    """Initialize a CVSSymbol object."""

    CVSItem.__init__(self, id, cvs_file, revision_reader_token)

    self.symbol = symbol
    self.source_lod = source_lod
    self.source_id = source_id

  def get_cvs_revision_source(self, cvs_file_items):
    """Return the CVSRevision that is the ultimate source of this symbol."""

    cvs_source = cvs_file_items[self.source_id]
    while not isinstance(cvs_source, CVSRevision):
      cvs_source = cvs_file_items[cvs_source.source_id]

    return cvs_source

  def get_svn_path(self):
    return self.symbol.get_path(self.cvs_file.cvs_path)

  def get_ids_closed(self):
    # A Symbol does not close any other CVSItems:
    return []


class CVSBranch(CVSSymbol):
  """Represent the creation of a branch in a particular CVSFile.

  Members:

    id -- (int) unique ID for this item.

    cvs_file -- (CVSFile) CVSFile affected by this item.

    symbol -- (Symbol) the symbol affected by this CVSSymbol.

    branch_number -- (string) the number of this branch (e.g.,
        '1.3.4'), or None if this is a converted CVSTag.

    source_lod -- (LineOfDevelopment) the LOD that is the source for
        this CVSSymbol.

    source_id -- (int) id of the CVSRevision or CVSBranch from which
        this branch sprouts.  This initially points to a CVSRevision,
        but can be changed to a CVSBranch via parent adjustment in
        FilterSymbolsPass.

    next_id -- (int or None) id of first CVSRevision on this branch,
        if any; else, None.

    tag_ids -- (list of int) ids of all CVSTags rooted at this
        CVSBranch (can be set due to parent adjustment in
        FilterSymbolsPass).

    branch_ids -- (list of int) ids of all CVSBranches rooted at this
        CVSBranch (can be set due to parent adjustment in
        FilterSymbolsPass).

    opened_symbols -- (None or list of (symbol_id, cvs_symbol_id)
        tuples) information about all CVSSymbols opened by this
        branch.  This member is set in FilterSymbolsPass; before then,
        it is None.

    revision_reader_token -- (arbitrary) a token that can be set by
        RevisionCollector for the later use of RevisionReader.

  """

  __slots__ = [
      'branch_number',
      'next_id',
      'tag_ids',
      'branch_ids',
      'opened_symbols',
      ]

  def __init__(
      self, id, cvs_file, symbol, branch_number,
      source_lod, source_id, next_id,
      revision_reader_token,
      ):
    """Initialize a CVSBranch."""

    CVSSymbol.__init__(
        self, id, cvs_file, symbol, source_lod, source_id,
        revision_reader_token,
        )
    self.branch_number = branch_number
    self.next_id = next_id
    self.tag_ids = []
    self.branch_ids = []
    self.opened_symbols = None

  def __getstate__(self):
    return (
        self.id, self.cvs_file.id,
        self.symbol.id, self.branch_number,
        self.source_lod.id, self.source_id, self.next_id,
        self.tag_ids, self.branch_ids,
        self.opened_symbols,
        self.revision_reader_token,
        )

  def __setstate__(self, data):
    (
        self.id, cvs_file_id,
        symbol_id, self.branch_number,
        source_lod_id, self.source_id, self.next_id,
        self.tag_ids, self.branch_ids,
        self.opened_symbols,
        self.revision_reader_token,
        ) = data
    self.cvs_file = Ctx()._cvs_path_db.get_path(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)
    self.source_lod = Ctx()._symbol_db.get_symbol(source_lod_id)

  def get_pred_ids(self):
    return set([self.source_id])

  def get_succ_ids(self):
    retval = set(self.tag_ids + self.branch_ids)
    if self.next_id is not None:
      retval.add(self.next_id)
    return retval

  def get_cvs_symbol_ids_opened(self):
    return self.tag_ids + self.branch_ids

  def check_links(self, cvs_file_items):
    source = cvs_file_items.get(self.source_id)
    next = cvs_file_items.get(self.next_id)

    assert self.id in source.branch_ids
    if isinstance(source, CVSRevision):
      assert self.source_lod == source.lod
    elif isinstance(source, CVSBranch):
      assert self.source_lod == source.symbol
    else:
      assert False

    if next is not None:
      assert isinstance(next, CVSRevision)
      assert next.lod == self.symbol
      assert next.first_on_branch_id == self.id

    for tag_id in self.tag_ids:
      tag = cvs_file_items[tag_id]
      assert isinstance(tag, CVSTag)
      assert tag.source_id == self.id
      assert tag.source_lod == self.symbol

    for branch_id in self.branch_ids:
      branch = cvs_file_items[branch_id]
      assert isinstance(branch, CVSBranch)
      assert branch.source_id == self.id
      assert branch.source_lod == self.symbol

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.branch_number, self.id,)


class CVSBranchNoop(CVSBranch):
  """A CVSBranch whose source is a CVSRevisionAbsent."""

  __slots__ = []

  def get_cvs_symbol_ids_opened(self):
    return []


# A map
#
#   {nondead(source_cvs_rev) : cvs_branch_subtype}
#
# , where nondead() means that the cvs revision exists and is not
# 'dead', and CVS_BRANCH_SUBTYPE is the subtype of CVSBranch that
# should be used.
cvs_branch_type_map = {
    False : CVSBranchNoop,
    True : CVSBranch,
    }


class CVSTag(CVSSymbol):
  """Represent the creation of a tag on a particular CVSFile.

  Members:

    id -- (int) unique ID for this item.

    cvs_file -- (CVSFile) CVSFile affected by this item.

    symbol -- (Symbol) the symbol affected by this CVSSymbol.

    source_lod -- (LineOfDevelopment) the LOD that is the source for
        this CVSSymbol.

    source_id -- (int) the ID of the CVSRevision or CVSBranch that is
        being tagged.  This initially points to a CVSRevision, but can
        be changed to a CVSBranch via parent adjustment in
        FilterSymbolsPass.

    revision_reader_token -- (arbitrary) a token that can be set by
        RevisionCollector for the later use of RevisionReader.

  """

  __slots__ = []

  def __init__(
      self, id, cvs_file, symbol, source_lod, source_id,
      revision_reader_token,
      ):
    """Initialize a CVSTag."""

    CVSSymbol.__init__(
        self, id, cvs_file, symbol, source_lod, source_id,
        revision_reader_token,
        )

  def __getstate__(self):
    return (
        self.id, self.cvs_file.id, self.symbol.id,
        self.source_lod.id, self.source_id,
        self.revision_reader_token,
        )

  def __setstate__(self, data):
    (
        self.id, cvs_file_id, symbol_id, source_lod_id, self.source_id,
        self.revision_reader_token,
        ) = data
    self.cvs_file = Ctx()._cvs_path_db.get_path(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)
    self.source_lod = Ctx()._symbol_db.get_symbol(source_lod_id)

  def get_pred_ids(self):
    return set([self.source_id])

  def get_succ_ids(self):
    return set()

  def get_cvs_symbol_ids_opened(self):
    return []

  def check_links(self, cvs_file_items):
    source = cvs_file_items.get(self.source_id)

    assert self.id in source.tag_ids
    if isinstance(source, CVSRevision):
      assert self.source_lod == source.lod
    elif isinstance(source, CVSBranch):
      assert self.source_lod == source.symbol
    else:
      assert False

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.id,)


class CVSTagNoop(CVSTag):
  """A CVSTag whose source is a CVSRevisionAbsent."""

  __slots__ = []


# A map
#
#   {nondead(source_cvs_rev) : cvs_tag_subtype}
#
# , where nondead() means that the cvs revision exists and is not
# 'dead', and CVS_TAG_SUBTYPE is the subtype of CVSTag that should be
# used.
cvs_tag_type_map = {
    False : CVSTagNoop,
    True : CVSTag,
    }


