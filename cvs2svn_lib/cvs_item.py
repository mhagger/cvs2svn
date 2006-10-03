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

"""This module contains classes to store CVS atomic items."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.line_of_development import Trunk
from cvs2svn_lib.line_of_development import Branch


class CVSItem(object):
  def __init__(self, id, cvs_file):
    self.id = id
    self.cvs_file = cvs_file

  def __cmp__(self, other):
    return cmp(self.id, other.id)

  def __hash__(self):
    return self.id

  def __getstate__(self):
    raise NotImplementedError()

  def __setstate__(self, data):
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


class CVSRevision(CVSItem):
  """Information about a single CVS revision.

  A CVSRevision holds the information known about a single version of
  a single file."""

  def __init__(self,
               id, cvs_file,
               timestamp, metadata_id,
               prev_id, next_id,
               op, rev, deltatext_exists,
               lod, first_on_branch_id, default_branch_revision,
               default_branch_prev_id, default_branch_next_id,
               tag_ids, branch_ids, branch_commit_ids,
               closed_symbol_ids):
    """Initialize a new CVSRevision object.

    Arguments:
       ID              -->  (string) unique ID for this revision.
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       TIMESTAMP       -->  (int) date stamp for this cvs revision
       METADATA_ID     -->  (int) id of author+logmsg record in metadata_db
       PREV_ID         -->  (int) id of the previous cvs revision (or None)
       NEXT_ID         -->  (int) id of the next cvs revision (or None)
       OP              -->  (char) OP_ADD, OP_CHANGE, or OP_DELETE
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
       TAG_IDS         -->  (list of int) ids of CVSSymbols on this revision
                            that should be treated as tags
       BRANCH_IDS      -->  (list of int) ids of all CVSSymbols rooted in this
                            revision that should be treated as branches
       BRANCH_COMMIT_IDS --> (list of int) ids of commits on branches rooted
                             in this revision
       CLOSED_SYMBOL_IDS --> (list of int) ids of all symbols closed by
                             this revision
    """

    CVSItem.__init__(self, id, cvs_file)

    self.rev = rev
    self.timestamp = timestamp
    self.metadata_id = metadata_id
    self.op = op
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

  def _get_cvs_path(self):
    return self.cvs_file.cvs_path

  cvs_path = property(_get_cvs_path)

  def get_svn_path(self):
    return self.lod.make_path(self.cvs_file)

  svn_path = property(get_svn_path)

  def __getstate__(self):
    """Return the contents of this instance, for pickling.

    The presence of this method improves the space efficiency of
    pickling CVSRevision instances."""

    if isinstance(self.lod, Branch):
      lod_id = self.lod.symbol.id
    else:
      lod_id = None

    return (
        self.id, self.cvs_file.id,
        self.timestamp, self.metadata_id,
        self.prev_id, self.next_id,
        self.op,
        self.rev,
        self.deltatext_exists,
        lod_id,
        self.first_on_branch_id,
        self.default_branch_revision,
        self.default_branch_prev_id, self.default_branch_next_id,
        self.tag_ids, self.branch_ids, self.branch_commit_ids,
        self.closed_symbol_ids,
        )

  def __setstate__(self, data):
    (self.id, cvs_file_id,
     self.timestamp, self.metadata_id,
     self.prev_id, self.next_id,
     self.op,
     self.rev,
     self.deltatext_exists,
     lod_id,
     self.first_on_branch_id,
     self.default_branch_revision,
     self.default_branch_prev_id, self.default_branch_next_id,
     self.tag_ids, self.branch_ids, self.branch_commit_ids,
     self.closed_symbol_ids) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    if lod_id is None:
      self.lod = Trunk()
    else:
      self.lod = Branch(Ctx()._symbol_db.get_symbol(lod_id))

  def opens_symbol(self, symbol_id):
    """Return True iff this CVSRevision is the opening CVSRevision for
    SYMBOL_ID (for this RCS file)."""

    # FIXME: All these DB reads are going to be expensive!
    for tag_id in self.tag_ids:
      cvs_tag = Ctx()._cvs_items_db[tag_id]
      if symbol_id == cvs_tag.symbol.id:
        return True
    # If this cvs_rev opens a branch and our op is OP_DELETE, then
    # that means that the file that this cvs_rev belongs to was
    # created on the branch, so for all intents and purposes, this
    # cvs_rev is *technically* not an opening.  See Issue #62 for
    # more information.
    if self.op != OP_DELETE:
      for branch_id in self.branch_ids:
        cvs_branch = Ctx()._cvs_items_db[branch_id]
        if symbol_id == cvs_branch.symbol.id:
          return True
    return False

  def get_pred_ids(self):
    retval = set()
    if self.first_on_branch_id is not None:
      retval.add(self.first_on_branch_id)
    if self.prev_id is not None:
      retval.add(self.prev_id)
    if self.default_branch_prev_id is not None:
      retval.add(self.default_branch_prev_id)
    return retval

  def get_succ_ids(self):
    retval = set()
    if self.next_id is not None:
      retval.add(self.next_id)
    if self.default_branch_next_id is not None:
      retval.add(self.default_branch_next_id)
    for id in self.branch_ids + self.tag_ids:
      retval.add(id)
    for id in self.branch_commit_ids:
      retval.add(id)
    return retval

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s:%s<%x>' % (self.cvs_file, self.rev, self.id,)


class CVSSymbol(CVSItem):
  """Represent a symbol on a particular CVSFile.

  This is the base class for CVSBranch and CVSTag."""

  def __init__(self, id, cvs_file, symbol, rev_id):
    """Initialize a CVSSymbol object.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       REV_ID          -->  (int) the ID of the revision being tagged"""

    CVSItem.__init__(self, id, cvs_file)

    self.symbol = symbol
    self.rev_id = rev_id


class CVSBranch(CVSSymbol):
  """Represent the creation of a branch in a particular CVSFile."""

  def __init__(self, id, cvs_file, symbol, branch_number, rev_id, next_id):
    """Initialize a CVSBranch.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       BRANCH_NUMBER   -->  (string) the number of this branch (e.g., "1.3.4")
                            or None if this is a converted tag
       REV_ID          -->  (int) id of CVSRevision from which this branch
                            sprouts
       NEXT_ID         -->  (int or None) id of first rev on this branch"""

    CVSSymbol.__init__(self, id, cvs_file, symbol, rev_id)
    self.branch_number = branch_number
    self.next_id = next_id

  def __getstate__(self):
    return (
        self.id, self.cvs_file.id,
        self.symbol.id, self.branch_number, self.rev_id, self.next_id)

  def __setstate__(self, data):
    (self.id, cvs_file_id,
     symbol_id, self.branch_number, self.rev_id, self.next_id) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def get_pred_ids(self):
    return set([self.rev_id])

  def get_succ_ids(self):
    retval = set()
    if self.next_id is not None:
      retval.add(self.next_id)
    return retval

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s Branch \'%s\' <%x>' % (self.cvs_file, self.symbol, self.id,)


class CVSTag(CVSSymbol):
  """Represent the creation of a tag on a particular CVSFile."""

  def __init__(self, id, cvs_file, symbol, rev_id):
    """Initialize a CVSTag.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       SYMBOL          -->  (Symbol) the corresponding symbol
       REV_ID          -->  (int) id of CVSRevision being tagged"""

    CVSSymbol.__init__(self, id, cvs_file, symbol, rev_id)

  def __getstate__(self):
    return (self.id, self.cvs_file.id, self.symbol.id, self.rev_id)

  def __setstate__(self, data):
    (self.id, cvs_file_id, symbol_id, self.rev_id) = data
    self.cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def get_pred_ids(self):
    return set([self.rev_id])

  def get_succ_ids(self):
    return set()

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%s Tag \'%s\' <%x>' % (self.cvs_file, self.symbol, self.id,)


