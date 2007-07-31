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


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx


class CVSItem(object):
  def __init__(self, id, cvs_file, revision_recorder_token):
    self.id = id
    self.cvs_file = cvs_file
    self.revision_recorder_token = revision_recorder_token

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

  def __repr__(self):
    return '%s(%s)' % (self.__class__.__name__, self,)


class CVSRevision(CVSItem):
  """Information about a single CVS revision.

  A CVSRevision holds the information known about a single version of
  a single file.

  Members:
    ID -- (string) unique ID for this revision.
    CVS_FILE -- (CVSFile) CVSFile affected by this revision.
    TIMESTAMP -- (int) date stamp for this revision.
    METADATA_ID -- (int) id of author + log message record in metadata_db.
    PREV_ID -- (int) id of the logically previous CVSRevision, either on the
        same or the source branch (or None).
    NEXT_ID -- (int) id of the logically next CVSRevision (or None).
    REV -- (string) the CVS revision number, e.g., '1.3'.
    DELTATEXT_EXISTS -- (bool) true iff this revision's deltatext is not
        empty.
    LOD -- (LineOfDevelopment) LOD on which this revision occurred.
    FIRST_ON_BRANCH_ID -- (int or None) if this revision is the first on its
        branch, the cvs_branch_id of that branch; else, None.
    DEFAULT_BRANCH_REVISION -- (bool) true iff this is a default branch
        revision.
    DEFAULT_BRANCH_PREV_ID -- (int or None) Iff this is the 1.2 revision after
        the end of a default branch, the id of the last rev on the default
        branch; else, None.
    DEFAULT_BRANCH_NEXT_ID -- (int or None) Iff this is the last revision on
        a default branch preceding a 1.2 rev, the id of the 1.2 revision;
        else, None.
    TAG_IDS -- (list of int) ids of all CVSTags rooted at this CVSRevision.
    BRANCH_IDS -- (list of int) ids of all CVSBranches rooted at this
        CVSRevision.
    BRANCH_COMMIT_IDS -- (list of int) ids of first CVSRevision committed on
        each branch rooted in this revision (for branches with commits).
    OPENED_SYMBOLS -- (None or list of (symbol_id, cvs_symbol_id) tuples)
        information about all CVSSymbols opened by this revision.  This member
        is set in FilterSymbolsPass; before then, it is None.
    CLOSED_SYMBOLS -- (None or list of (symbol_id, cvs_symbol_id) tuples)
        information about all CVSSymbols closed by this revision.  This member
        is set in FilterSymbolsPass; before then, it is None.
    REVISION_RECORDER_TOKEN -- (arbitrary) a token that can be set by
        RevisionRecorder for the later use of RevisionReader.

  """

  def __init__(self,
               id, cvs_file,
               timestamp, metadata_id,
               prev_id, next_id,
               rev, deltatext_exists,
               lod, first_on_branch_id, default_branch_revision,
               default_branch_prev_id, default_branch_next_id,
               tag_ids, branch_ids, branch_commit_ids,
               revision_recorder_token):
    """Initialize a new CVSRevision object."""

    CVSItem.__init__(self, id, cvs_file, revision_recorder_token)

    self.timestamp = timestamp
    self.metadata_id = metadata_id
    self.prev_id = prev_id
    self.next_id = next_id
    self.rev = rev
    self.deltatext_exists = deltatext_exists
    self.lod = lod
    self.first_on_branch_id = first_on_branch_id
    self.default_branch_revision = default_branch_revision
    self.default_branch_prev_id = default_branch_prev_id
    self.default_branch_next_id = default_branch_next_id
    self.tag_ids = tag_ids
    self.branch_ids = branch_ids
    self.branch_commit_ids = branch_commit_ids
    self.opened_symbols = None
    self.closed_symbols = None

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
        self.default_branch_revision,
        self.default_branch_prev_id, self.default_branch_next_id,
        self.tag_ids, self.branch_ids, self.branch_commit_ids,
        self.opened_symbols, self.closed_symbols,
        self.revision_recorder_token,
        )

  def __setstate__(self, data):
    (self.id, cvs_file_id,
     self.timestamp, self.metadata_id,
     self.prev_id, self.next_id,
     self.rev,
     self.deltatext_exists,
     lod_id,
     self.first_on_branch_id,
     self.default_branch_revision,
     self.default_branch_prev_id, self.default_branch_next_id,
     self.tag_ids, self.branch_ids, self.branch_commit_ids,
     self.opened_symbols, self.closed_symbols,
     self.revision_recorder_token) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.lod = Ctx()._symbol_db.get_symbol(lod_id)

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
    if self.default_branch_prev_id is not None:
      retval.add(self.default_branch_prev_id)
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
    if self.default_branch_next_id is not None:
      retval.add(self.default_branch_next_id)
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
      if self.default_branch_revision:
        # If the 1.1 revision was not deleted, the 1.1.1.1 revision is
        # considered to close it:
        yield self.prev_id
    elif self.default_branch_prev_id is not None:
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

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' % (self.cvs_file, self.rev, self.id,)


class CVSRevisionModification(CVSRevision):
  """Base class for CVSRevisionAdd or CVSRevisionChange."""

  def get_cvs_symbol_ids_opened(self):
    return self.tag_ids + self.branch_ids


class CVSRevisionAdd(CVSRevisionModification):
  """A CVSRevision that creates a file that previously didn't exist.

  The file might have never existed on this LOD, or it might have
  existed previously but been deleted by a CVSRevisionDelete."""

  pass


class CVSRevisionChange(CVSRevisionModification):
  """A CVSRevision that modifies a file that already existed on this LOD."""

  pass


class CVSRevisionAbsent(CVSRevision):
  """A CVSRevision for which the file is nonexistent on this LOD."""

  def get_cvs_symbol_ids_opened(self):
    return []


class CVSRevisionDelete(CVSRevisionAbsent):
  """A CVSRevision that deletes a file that existed on this LOD."""

  pass


class CVSRevisionNoop(CVSRevisionAbsent):
  """A CVSRevision that doesn't do anything.

  The revision was 'dead' and the predecessor either didn't exist or
  was also 'dead'.  These revisions can't necessarily be thrown away
  because (1) they impose ordering constraints on other items; (2)
  they might have a nontrivial log message that we don't want to throw
  away."""

  pass


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
    ID -- (string) unique ID for this item.
    CVS_FILE -- (CVSFile) CVSFile affected by this item.
    SYMBOL -- (Symbol) the symbol affected by this CVSSymbol.
    SOURCE_LOD -- (LineOfDevelopment) the LOD that is the source for this
        CVSSymbol.
    SOURCE_ID -- (int) the ID of the CVSRevision or CVSBranch that is the
        source for this item.
    REVISION_RECORDER_TOKEN -- (arbitrary) a token that can be set by
        RevisionRecorder for the later use of RevisionReader.

  """

  def __init__(
      self, id, cvs_file, symbol, source_lod, source_id,
      revision_recorder_token
      ):
    """Initialize a CVSSymbol object."""

    CVSItem.__init__(self, id, cvs_file, revision_recorder_token)

    self.symbol = symbol
    self.source_lod = source_lod
    self.source_id = source_id

  def get_svn_path(self):
    return self.symbol.get_path(self.cvs_file.cvs_path)

  def get_ids_closed(self):
    # A Symbol does not close any other CVSItems:
    return []


class CVSBranch(CVSSymbol):
  """Represent the creation of a branch in a particular CVSFile.

  Members:
    ID -- (string) unique ID for this item.
    CVS_FILE -- (CVSFile) CVSFile affected by this item.
    SYMBOL -- (Symbol) the symbol affected by this CVSSymbol.
    BRANCH_NUMBER -- (string) the number of this branch (e.g., '1.3.4'), or
        None if this is a converted CVSTag.
    SOURCE_LOD -- (LineOfDevelopment) the LOD that is the source for this
        CVSSymbol.
    SOURCE_ID -- (int) id of the CVSRevision or CVSBranch from which this
        branch sprouts.
    NEXT_ID -- (int or None) id of first CVSRevision on this branch, if any;
        else, None.
    TAG_IDS -- (list of int) ids of all CVSTags rooted at this CVSBranch (can
        be set due to parent adjustment in FilterSymbolsPass).
    BRANCH_IDS -- (list of int) ids of all CVSBranches rooted at this
        CVSBranch (can be set due to parent adjustment in FilterSymbolsPass).
    OPENED_SYMBOLS -- (None or list of (symbol_id, cvs_symbol_id) tuples)
        information about all CVSSymbols opened by this branch.  This member
        is set in FilterSymbolsPass; before then, it is None.
    REVISION_RECORDER_TOKEN -- (arbitrary) a token that can be set by
        RevisionRecorder for the later use of RevisionReader.

  """

  def __init__(
      self, id, cvs_file, symbol, branch_number,
      source_lod, source_id, next_id,
      revision_recorder_token,
      ):
    """Initialize a CVSBranch."""

    CVSSymbol.__init__(
        self, id, cvs_file, symbol, source_lod, source_id,
        revision_recorder_token
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
        self.revision_recorder_token,
        )

  def __setstate__(self, data):
    (
        self.id, cvs_file_id,
        symbol_id, self.branch_number,
        source_lod_id, self.source_id, self.next_id,
        self.tag_ids, self.branch_ids,
        self.opened_symbols,
        self.revision_recorder_token,
        ) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
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

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.branch_number, self.id,)


class CVSBranchNoop(CVSBranch):
  """A CVSBranch whose source is a CVSRevisionAbsent."""

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
    ID -- (string) unique ID for this item.
    CVS_FILE -- (CVSFile) CVSFile affected by this item.
    SYMBOL -- (Symbol) the symbol affected by this CVSSymbol.
    SOURCE_LOD -- (LineOfDevelopment) the LOD that is the source for this
        CVSSymbol.
    SOURCE_ID -- (int) the ID of the CVSRevision or CVSBranch that is being
        tagged.
    REVISION_RECORDER_TOKEN -- (arbitrary) a token that can be set by
        RevisionRecorder for the later use of RevisionReader.

  """

  def __init__(
      self, id, cvs_file, symbol, source_lod, source_id,
      revision_recorder_token,
      ):
    """Initialize a CVSTag."""

    CVSSymbol.__init__(
        self, id, cvs_file, symbol, source_lod, source_id,
        revision_recorder_token,
        )

  def __getstate__(self):
    return (
        self.id, self.cvs_file.id, self.symbol.id,
        self.source_lod.id, self.source_id,
        self.revision_recorder_token,
        )

  def __setstate__(self, data):
    (
        self.id, cvs_file_id, symbol_id, source_lod_id, self.source_id,
        self.revision_recorder_token,
        ) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)
    self.source_lod = Ctx()._symbol_db.get_symbol(source_lod_id)

  def get_pred_ids(self):
    return set([self.source_id])

  def get_succ_ids(self):
    return set()

  def get_cvs_symbol_ids_opened(self):
    return []

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.id,)


class CVSTagNoop(CVSTag):
  """A CVSTag whose source is a CVSRevisionAbsent."""

  pass


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


