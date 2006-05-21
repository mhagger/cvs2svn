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


class CVSRevisionID(object):
  """An object that identifies a CVS revision of a file."""

  def __init__(self, id):
    self.id = id


class CVSRevision(CVSRevisionID):
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
               branch_name, first_on_branch, tags, branches):
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
       BRANCH_NAME     -->  (string or None) branch on which this rev occurred
       FIRST_ON_BRANCH -->  (bool) true iff the first rev on its branch
       TAGS            -->  (list of strings) all tags on this revision
       BRANCHES        -->  (list of strings) all branches rooted in this rev

    WARNING: Due to the resync process in pass2, prev_timestamp or
    next_timestamp may be incorrect in the c-revs or s-revs files."""

    CVSRevisionID.__init__(self, id)

    self.cvs_file = cvs_file
    self.rev = rev
    self.timestamp = timestamp
    self.digest = digest
    self.op = op
    self.prev_id = prev_id
    self.next_id = next_id
    self.deltatext_exists = deltatext_exists
    self.branch_name = branch_name
    self.first_on_branch = first_on_branch
    self.tags = tags
    self.branches = branches

  def _get_cvs_path(self):
    return self.cvs_file.cvs_path

  cvs_path = property(_get_cvs_path)

  def get_svn_path(self):
    if self.branch_name:
      return self.ctx.project.make_branch_path(
          self.branch_name, self.cvs_file.cvs_path)
    else:
      return self.ctx.project.make_trunk_path(self.cvs_file.cvs_path)

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
        self.branch_name,
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
    """Return True iff SELF.rev of SELF.cvs_file.cvs_path is a default
    branch revision according to DEFAULT_BRANCHES_DB (see the
    conditions documented there)."""

    val = self.ctx._default_branches_db.get('%x' % self.cvs_file.id, None)
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


