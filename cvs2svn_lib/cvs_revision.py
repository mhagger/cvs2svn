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

"""This module contains classes to store CVS revisions."""


from boolean import *
from common import OP_DELETE


class CVSItem(object):
  def __init__(self, id, cvs_file):
    self.id = id
    self.cvs_file = cvs_file


class CVSRevision(CVSItem):
  """Information about a single CVS revision.

  A CVSRevision holds the information known about a single version of
  a single file.

  ctx is the context to use for instances of CVSRevision, or None.  If
  ctx is None, the following properties of instantiated CVSRevision
  class objects will be unavailable (or simply will not work
  correctly, if at all):

     cvs_path
     svn_path
     is_default_branch_revision()

  (Note that this class treats ctx as const, because the caller
  likely passed in a Borg instance of a Ctx.  The reason this class
  stores a Ctx instance, instead of just instantiating a Ctx itself,
  is that this class should be usable outside cvs2svn.)
  """

  ctx = None

  def __init__(self,
               id, cvs_file,
               timestamp, digest,
               prev_id, next_id,
               op, rev, deltatext_exists,
               lod, first_on_branch, tags, branches):
    """Initialize a new CVSRevision object.

    Arguments:
       ID              -->  (string) unique ID for this revision.
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       TIMESTAMP       -->  (int) date stamp for this cvs revision
       DIGEST          -->  (string) digest of author+logmsg
       PREV_ID         -->  (int) id of the previous cvs revision (or None)
       NEXT_ID         -->  (int) id of the next cvs revision (or None)
       OP              -->  (char) OP_ADD, OP_CHANGE, or OP_DELETE
       REV             -->  (string) this CVS rev, e.g., '1.3'
       DELTATEXT_EXISTS-->  (bool) true iff non-empty deltatext
       LOD             -->  (LineOfDevelopment) LOD where this rev occurred
       FIRST_ON_BRANCH -->  (bool) true iff the first rev on its branch
       TAGS            -->  (list of strings) all tags on this revision
       BRANCHES        -->  (list of strings) all branches rooted in this rev

    WARNING: Due to the resync process in pass2, prev_timestamp or
    next_timestamp may be incorrect in the c-revs or s-revs files."""

    CVSItem.__init__(self, id, cvs_file)

    self.rev = rev
    self.timestamp = timestamp
    self.digest = digest
    self.op = op
    self.prev_id = prev_id
    self.next_id = next_id
    self.deltatext_exists = deltatext_exists
    self.lod = lod
    self.first_on_branch = first_on_branch
    self.tags = tags
    self.branches = branches

  def _get_cvs_path(self):
    return self.cvs_file.cvs_path

  cvs_path = property(_get_cvs_path)

  def get_svn_path(self):
    return self.lod.make_path(self.cvs_file)

  svn_path = property(get_svn_path)

  def __getinitargs__(self):
    """Return the contents of this instance, for pickling.

    The presence of this method improves the space efficiency of
    pickling CVSRevision instances."""

    return (
        self.id, self.cvs_file,
        self.timestamp, self.digest,
        self.prev_id, self.next_id,
        self.op,
        self.rev,
        self.deltatext_exists,
        self.lod,
        self.first_on_branch,
        self.tags,
        self.branches,)

  def opens_symbolic_name(self, name):
    """Return True iff this CVSRevision is the opening CVSRevision for
    NAME (for this RCS file)."""

    if name in self.tags:
      return True
    if name in self.branches:
      # If this c_rev opens a branch and our op is OP_DELETE, then
      # that means that the file that this c_rev belongs to was
      # created on the branch, so for all intents and purposes, this
      # c_rev is *technically* not an opening.  See Issue #62 for more
      # information.
      if self.op != OP_DELETE:
        return True
    return False

  def is_default_branch_revision(self):
    """Return True iff SELF.rev of SELF.cvs_file is a default branch
    revision."""

    val = self.cvs_file.default_branch
    if val is not None:
      val_last_dot = val.rindex(".")
      our_last_dot = self.rev.rindex(".")
      default_branch = val[:val_last_dot]
      our_branch = self.rev[:our_last_dot]
      default_rev_component = int(val[val_last_dot + 1:])
      our_rev_component = int(self.rev[our_last_dot + 1:])
      if (default_branch == our_branch
          and our_rev_component <= default_rev_component):
        return True

    return False


class CVSSymbol(CVSItem):
  """Represent a symbol on a particular CVSFile.

  This is the base class for CVSBranch and CVSTag."""

  def __init__(self, id, cvs_file, name, rev_id):
    """Initialize a CVSSymbol object.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       NAME            -->  (string) the name of this branch
       REV_ID          -->  (int) the ID of the revision being tagged"""

    CVSItem.__init__(self, id, cvs_file)

    self.name = name
    self.rev_id = rev_id


class CVSBranch(CVSSymbol):
  """Represent the creation of a branch in a particular CVSFile."""

  def __init__(self, id, cvs_file, name, branch_number, next_id):
    """Initialize a CVSBranch.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       NAME            -->  (string) the name of this branch
       BRANCH_NUMBER   -->  (int) the (3-digit) number of this branch
       NEXT_ID         -->  (int or None) id of first rev on this branch"""

    self.branch_number = branch_number
    sprout_rev = self.branch_number[:self.branch_number.rfind(".")]
    CVSSymbol.__init__(self, id, cvs_file, name, sprout_rev)
    self.next_id = next_id


class CVSTag(CVSSymbol):
  """Represent the creation of a tag on a particular CVSFile."""

  def __init__(self, id, cvs_file, name, rev_id):
    """Initialize a CVSBranch.

    Arguments:
       ID              -->  (string) unique ID for this item
       CVS_FILE        -->  (CVSFile) CVSFile affected by this revision
       NAME            -->  (string) the name of this branch
       BRANCH_NUMBER   -->  (int) the (3-digit) number of this branch
       NEXT_ID         -->  (int or None) id of first rev on this branch"""

    CVSSymbol.__init__(self, id, cvs_file, name, rev_id)


