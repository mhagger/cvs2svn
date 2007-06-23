# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
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
|  +--CVSRevisionModification
|  |  |
|  |  +--CVSRevisionAdd
|  |  |
|  |  +--CVSRevisionChange
|  |
|  +--CVSRevisionDelete
|
+--CVSSymbol
   |
   +--CVSBranch
   |
   +--CVSTag

"""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx


class CVSItem(object):
  def __init__(self, id, cvs_file):
    self.id = id
    self.cvs_file = cvs_file

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

  def get_ids_closed(self):
    """Return an iterable over the CVSItem.ids of CVSItems closed by this one.

    A CVSItem A is said to close a CVSItem B if committing A causes B
    to be overwritten or deleted (no longer available) in the SVN
    repository.  This is interesting because it sets the last SVN
    revision number from which the contents of B can be copied (for
    example, to fill a symbol).  See the concrete implementations of
    this method for the exact rules about what closes what."""

    raise NotImplementedError()


class CVSRevision(CVSItem):
  """Information about a single CVS revision.

  A CVSRevision holds the information known about a single version of
  a single file."""

  def __init__(self,
               id, cvs_file,
               timestamp, metadata_id,
               prev_id, next_id,
               rev, deltatext_exists,
               lod, first_on_branch_id, default_branch_revision,
               default_branch_prev_id, default_branch_next_id,
               tag_ids, branch_ids, branch_commit_ids,
               closed_symbol_ids,
               revision_recorder_token):
    """Initialize a new CVSRevision object.

    Arguments:
       ID              -->  (string) unique ID for this revision.
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       TIMESTAMP       -->  (int) date stamp for this cvs revision
       METADATA_ID     -->  (int) id of author+logmsg record in metadata_db
       PREV_ID         -->  (int) id of the previous cvs revision (or None)
       NEXT_ID         -->  (int) id of the next cvs revision (or None)
       REV             -->  (string) this CVS rev, e.g., '1.3'
       DELTATEXT_EXISTS-->  (bool) true iff non-empty deltatext
       LOD             -->  (LineOfDevelopment) LOD where this rev occurred
       FIRST_ON_BRANCH_ID -->  (int or None) if the first rev on its branch,
                               the branch_id of that branch; else, None
       DEFAULT_BRANCH_REVISION --> (bool) true iff this is a default branch
                                   revision
       DEFAULT_BRANCH_PREV_ID --> (int or None) Iff 1.2 revision after end of
                            default branch, id of last rev on default branch
       DEFAULT_BRANCH_NEXT_ID --> (int or None) Iff last rev on default branch
                                  preceding 1.2 rev, id of 1.2 rev
       TAG_IDS         -->  (list of int) ids of all CVSTags rooted at this
                            CVSRevision
       BRANCH_IDS      -->  (list of int) ids of all CVSBranches rooted at
                            this CVSRevision
       BRANCH_COMMIT_IDS --> (list of int) ids of commits on branches rooted
                             in this revision
       CLOSED_SYMBOL_IDS --> (None or list of int) ids of all symbols closed
                             by this revision (set in FilterSymbolsPass)
       REVISION_RECORDER_TOKEN --> (arbitrary) a token that can be used by
                                   RevisionRecorder/RevisionReader.
    """

    CVSItem.__init__(self, id, cvs_file)

    self.rev = rev
    self.timestamp = timestamp
    self.metadata_id = metadata_id
    self.prev_id = prev_id
    self.next_id = next_id
    self.deltatext_exists = deltatext_exists
    self.lod = lod
    self.first_on_branch_id = first_on_branch_id
    self.default_branch_revision = default_branch_revision
    self.default_branch_prev_id = default_branch_prev_id
    self.default_branch_next_id = default_branch_next_id
    self.tag_ids = tag_ids
    self.branch_ids = branch_ids
    self.branch_commit_ids = branch_commit_ids
    self.closed_symbol_ids = closed_symbol_ids
    self.revision_recorder_token = revision_recorder_token

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
        self.closed_symbol_ids,
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
     self.closed_symbol_ids,
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

  pass


class CVSRevisionAdd(CVSRevisionModification):
  """A CVSRevision that creates a file that previously didn't exist.

  The file might have never existed on this LOD, or it might have
  existed previously but been deleted by a CVSRevisionDelete."""

  pass


class CVSRevisionChange(CVSRevisionModification):
  """A CVSRevision that modifies a file that already existed on this LOD."""

  pass


class CVSRevisionDelete(CVSRevision):
  """A CVSRevision that deletes a file that existed on this LOD."""

  pass


class CVSRevisionNoop(CVSRevision):
  """A CVSRevision that doesn't do anything.

  These revisions can't necessarily be thrown away because (1) they
  impose ordering constraints on other items; (2) they might have a
  nontrivial log message that we don't want to throw away."""

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

  This is the base class for CVSBranch and CVSTag."""

  def __init__(self, id, cvs_file, symbol, source_id):
    """Initialize a CVSSymbol object.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       SOURCE_ID       -->  (int) the ID of the CVSRevision or CVSBranch that
                            is the source for this item"""

    CVSItem.__init__(self, id, cvs_file)

    self.symbol = symbol
    self.source_id = source_id

  def get_svn_path(self):
    return self.symbol.get_path(self.cvs_file.cvs_path)

  def get_ids_closed(self):
    # A Symbol does not close any other CVSItems:
    return []


class CVSBranch(CVSSymbol):
  """Represent the creation of a branch in a particular CVSFile."""

  def __init__(self, id, cvs_file, symbol, branch_number, source_id, next_id):
    """Initialize a CVSBranch.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       BRANCH_NUMBER   -->  (string) the number of this branch (e.g., "1.3.4")
                            or None if this is a converted tag
       SOURCE_ID       -->  (int) id of CVSRevision or CVSBranch from which
                            this branch sprouts
       NEXT_ID         -->  (int or None) id of first rev on this branch
       TAG_IDS         -->  (list of int) ids of all CVSTags rooted at this
                            CVSBranch (can be set due to parent adjustment)
       BRANCH_IDS      -->  (list of int) ids of all CVSBranches rooted at
                            this CVSBranch (can be set due to parent
                            adjustment)"""

    CVSSymbol.__init__(self, id, cvs_file, symbol, source_id)
    self.branch_number = branch_number
    self.next_id = next_id
    self.tag_ids = []
    self.branch_ids = []

  def __getstate__(self):
    return (
        self.id, self.cvs_file.id,
        self.symbol.id, self.branch_number, self.source_id, self.next_id,
        self.tag_ids, self.branch_ids)

  def __setstate__(self, data):
    (self.id, cvs_file_id,
     symbol_id, self.branch_number, self.source_id, self.next_id,
     self.tag_ids, self.branch_ids) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def get_pred_ids(self):
    return set([self.source_id])

  def get_succ_ids(self):
    retval = set(self.tag_ids + self.branch_ids)
    if self.next_id is not None:
      retval.add(self.next_id)
    return retval

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.branch_number, self.id,)


class CVSTag(CVSSymbol):
  """Represent the creation of a tag on a particular CVSFile."""

  def __init__(self, id, cvs_file, symbol, source_id):
    """Initialize a CVSTag.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       SOURCE_ID       -->  (int) id of CVSRevision or CVSBranch being
                            tagged"""

    CVSSymbol.__init__(self, id, cvs_file, symbol, source_id)

  def __getstate__(self):
    return (self.id, self.cvs_file.id, self.symbol.id, self.source_id)

  def __setstate__(self, data):
    (self.id, cvs_file_id, symbol_id, self.source_id) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def get_pred_ids(self):
    return set([self.source_id])

  def get_succ_ids(self):
    return set()

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' \
           % (self.cvs_file, self.symbol, self.id,)


