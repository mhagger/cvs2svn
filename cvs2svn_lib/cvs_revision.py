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


import os

from boolean import *
import common


class CVSRevisionID(object):
  """An object that identifies a CVS revision of a file."""

  def __init__(self, fname, rev):
    self.fname = fname
    self.rev = rev

  def unique_key(self):
    """Return a string that can be used as a unique key for this revision.

    The 'primary key' of a CVS Revision is (revision number,
    filename).  To make a key (say, for a dict), we just glom them
    together into a string."""

    return self.rev + '/' + self.fname


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
               timestamp, digest, prev_timestamp, next_timestamp,
               op, prev_rev, rev, next_rev,
               file_in_attic, file_executable,
               file_size, deltatext_exists,
               fname, mode, branch_name, tags, branches):
    """Initialize a new CVSRevision object.

    Arguments:
       TIMESTAMP       -->  (int) date stamp for this cvs revision
       DIGEST          -->  (string) digest of author+logmsg
       PREV_TIMESTAMP  -->  (int) date stamp for the previous cvs revision
       NEXT_TIMESTAMP  -->  (int) date stamp for the next cvs revision
       OP              -->  (char) OP_ADD, OP_CHANGE, or OP_DELETE
       PREV_REV        -->  (string or None) previous CVS rev, e.g., '1.2'.
                            This is converted to a CVSRevisionID instance.
       REV             -->  (string) this CVS rev, e.g., '1.3'
       NEXT_REV        -->  (string or None) next CVS rev, e.g., '1.4'.
                            This is converted to a CVSRevisionID instance.
       FILE_IN_ATTIC   -->  (bool) true iff RCS file is in Attic
       FILE_EXECUTABLE -->  (bool) true iff RCS file has exec bit set.
       FILE_SIZE       -->  (int) size of the RCS file
       DELTATEXT_EXISTS-->  (bool) true iff non-empty deltatext
       FNAME           -->  (string) relative path of file in CVS repos
       MODE            -->  (string or None) 'kkv', 'kb', etc.
       BRANCH_NAME     -->  (string or None) branch on which this rev occurred
       TAGS            -->  (list of strings) all tags on this revision
       BRANCHES        -->  (list of strings) all branches rooted in this rev

    WARNING: Due to the resync process in pass2, prev_timestamp or
    next_timestamp may be incorrect in the c-revs or s-revs files."""

    CVSRevisionID.__init__(self, fname, rev)

    self.timestamp = timestamp
    self.digest = digest
    self.prev_timestamp = prev_timestamp
    self.next_timestamp = next_timestamp
    self.op = op
    self.prev_rev = prev_rev and CVSRevisionID(self.fname, prev_rev)
    self.next_rev = next_rev and CVSRevisionID(self.fname, next_rev)
    self.file_in_attic = file_in_attic
    self.file_executable = file_executable
    self.file_size = file_size
    self.deltatext_exists = deltatext_exists
    self.mode = mode
    self.branch_name = branch_name
    self.tags = tags
    self.branches = branches

  def get_cvs_path(self):
    return self.ctx.cvs_repository.get_cvs_path(self.fname)

  cvs_path = property(get_cvs_path)

  def get_svn_path(self):
    if self.branch_name:
      return self.ctx.project.make_branch_path(
          self.branch_name, self.cvs_path)
    else:
      return self.ctx.project.make_trunk_path(self.cvs_path)

  svn_path = property(get_svn_path)

  def __str__(self):
    def timestamp_to_string(timestamp):
      if timestamp:
        return '%08lx' % timestamp
      else:
        return '*'

    def rev_to_string(rev):
      if rev is None:
        return '*'
      else:
        return rev.rev

    def bool_to_string(v):
      return { True : 'T', False : 'F' }[bool(v)]

    def list_to_string(l):
      """Format list L as a count of elements followed by the elements
      themselves, each separated by spaces."""

      return ' '.join([str(len(l))] + l)

    return ('%s %s %s %s %s %s %s %s %s %s %d %s %s %s %s %s %s'
            % (timestamp_to_string(self.timestamp),
               self.digest,
               timestamp_to_string(self.prev_timestamp),
               timestamp_to_string(self.next_timestamp),
               self.op,
               rev_to_string(self.prev_rev),
               self.rev,
               rev_to_string(self.next_rev),
               bool_to_string(self.file_in_attic),
               bool_to_string(self.file_executable),
               self.file_size,
               bool_to_string(self.deltatext_exists),
               self.mode or '*',
               self.branch_name or '*',
               list_to_string(self.tags),
               list_to_string(self.branches),
               self.fname,))

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
      if self.op != common.OP_DELETE:
        return True
    return False

  def is_default_branch_revision(self):
    """Return True iff SELF.rev of SELF.cvs_path is a default branch
    revision according to DEFAULT_BRANCHES_DB (see the conditions
    documented there)."""

    val = self.ctx._default_branches_db.get(self.cvs_path, None)
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

  def rcs_path(self):
    """Returns the actual filesystem path to the RCS file of this
    CVSRevision."""

    if self.file_in_attic:
      basepath, filename = os.path.split(self.fname)
      return os.path.join(basepath, 'Attic', filename)
    else:
      return self.fname

  def filename(self):
    """Return the last path component of self.fname, minus the ',v'."""

    return os.path.split(self.fname)[-1][:-2]


def parse_cvs_revision(line):
  """Parse LINE into a CVSRevision object and return the object.
  LINE is a string in the format of a line from a revs file.  It should
  *not* include a trailing newline."""

  def string_to_timestamp(s):
    if s == '*':
      return 0
    else:
      return int(s, 16)

  def string_to_rev(s):
    if s == '*':
      return None
    else:
      return s

  def string_to_bool(s):
    return { 'T' : True, 'F' : False }[s]

  (timestamp, digest, prev_timestamp, next_timestamp,
   op, prev_rev, rev, next_rev, file_in_attic,
   file_executable, file_size, deltatext_exists,
   mode, branch_name, numtags, remainder) = line.split(' ', 15)

  # Patch up items which are not simple strings:
  timestamp = string_to_timestamp(timestamp)
  prev_timestamp = string_to_timestamp(prev_timestamp)
  next_timestamp = string_to_timestamp(next_timestamp)

  prev_rev = string_to_rev(prev_rev)
  next_rev = string_to_rev(next_rev)

  file_in_attic = string_to_bool(file_in_attic)
  file_executable = string_to_bool(file_executable)

  file_size = int(file_size)

  deltatext_exists = string_to_bool(deltatext_exists)

  if mode == "*":
    mode = None

  if branch_name == "*":
    branch_name = None

  numtags = int(numtags)
  tags_and_numbranches_and_remainder = remainder.split(' ', numtags + 1)
  tags = tags_and_numbranches_and_remainder[:-2]
  numbranches = int(tags_and_numbranches_and_remainder[-2])
  remainder = tags_and_numbranches_and_remainder[-1]
  branches_and_fname = remainder.split(' ', numbranches)
  branches = branches_and_fname[:-1]
  fname = branches_and_fname[-1]

  return CVSRevision(timestamp, digest, prev_timestamp, next_timestamp,
                     op, prev_rev, rev, next_rev,
                     file_in_attic, file_executable,
                     file_size, deltatext_exists,
                     fname, mode, branch_name, tags, branches)


