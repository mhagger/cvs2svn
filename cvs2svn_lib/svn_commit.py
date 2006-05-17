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

"""This module contains the CVSCommit class."""


from boolean import *
import common
from common import warning_prefix
from context import Ctx
from log import Log


class SVNCommit:
  """This represents one commit to the Subversion Repository.  There
  are three types of SVNCommits:

  1. Commits one or more CVSRevisions (cannot fill a symbolic name).

  2. Creates or fills a symbolic name (cannot commit CVSRevisions).

  3. Updates trunk to reflect the contents of a particular branch
     (this is to handle RCS default branches)."""

  # The revision number to assign to the next new SVNCommit.
  # We start at 2 because SVNRepositoryMirror uses the first commit
  # to create trunk, tags, and branches.
  revnum = 2

  class SVNCommitInternalInconsistencyError(Exception):
    """Exception raised if we encounter an impossible state in the
    SVNCommit Databases."""

    pass

  def __init__(self, description="", revnum=None, cvs_revs=None):
    """Instantiate an SVNCommit.  DESCRIPTION is for debugging only.
    If REVNUM, the SVNCommit will correspond to that revision number;
    and if CVS_REVS, then they must be the exact set of CVSRevisions for
    REVNUM.

    It is an error to pass CVS_REVS without REVNUM, but you may pass
    REVNUM without CVS_REVS, and then add a revision at a time by
    invoking add_revision()."""

    self._description = description

    # Revprop metadata for this commit.
    #
    # These initial values are placeholders.  At least the log and the
    # date should be different by the time these are used.
    #
    # They are private because their values should be returned encoded
    # in UTF8, but callers aren't required to set them in UTF8.
    # Therefore, accessor methods are used to set them, and
    # self.get_revprops() is used to to get them, in dictionary form.
    self._author = Ctx().username
    self._log_msg = "This log message means an SVNCommit was used too soon."
    self._max_date = 0  # Latest date seen so far.

    self.cvs_revs = cvs_revs or []
    if revnum:
      self.revnum = revnum
    else:
      self.revnum = SVNCommit.revnum
      SVNCommit.revnum += 1

    # The (uncleaned) symbolic name that is filled in this SVNCommit, if any.
    self.symbolic_name = None

    # If this commit is a default branch synchronization, this
    # variable represents the subversion revision number of the
    # *primary* commit where the default branch changes actually
    # happened.  It is None otherwise.
    #
    # It is possible for multiple synchronization commits to refer to
    # the same motivating commit revision number, and it is possible
    # for a single synchronization commit to contain CVSRevisions on
    # multiple different default branches.
    self.motivating_revnum = None

    # is_tag is true only if this commit is a fill of a symbolic name
    # that is a tag, None in all other cases.
    self.is_tag = None

  def set_symbolic_name(self, symbolic_name):
    """Set self.symbolic_name to SYMBOLIC_NAME."""

    self.symbolic_name = symbolic_name

  def set_motivating_revnum(self, revnum):
    """Set self.motivating_revnum to REVNUM."""

    self.motivating_revnum = revnum

  def set_author(self, author):
    """Set this SVNCommit's author to AUTHOR (a locally-encoded string).
    This is the only way to set an SVNCommit's author."""

    self._author = author

  def set_log_msg(self, msg):
    """Set this SVNCommit's log message to MSG (a locally-encoded string).
    This is the only way to set an SVNCommit's log message."""

    self._log_msg = msg

  def set_date(self, date):
    """Set this SVNCommit's date to DATE (an integer).
    Note that self.add_revision() updates this automatically based on
    a CVSRevision; so you may not need to call this at all, and even
    if you do, the value may be overwritten by a later call to
    self.add_revision()."""

    self._max_date = date

  def get_date(self):
    """Returns this SVNCommit's date as an integer."""

    return self._max_date

  def get_revprops(self):
    """Return the Subversion revprops for this SVNCommit."""

    date = common.format_date(self._max_date)
    try:
      utf8_author = None
      if self._author is not None:
        utf8_author = Ctx().to_utf8(self._author)
      utf8_log = Ctx().to_utf8(self.get_log_msg())
      return { 'svn:author' : utf8_author,
               'svn:log'    : utf8_log,
               'svn:date'   : date }
    except UnicodeError:
      Log().warn('%s: problem encoding author or log message:'
                 % warning_prefix)
      Log().warn("  author: '%s'" % self._author)
      Log().warn("  log:    '%s'" % self.get_log_msg().rstrip())
      Log().warn("  date:   '%s'" % date)
      Log().warn("(subversion rev %s)  Related files:" % self.revnum)
      for c_rev in self.cvs_revs:
        Log().warn(" ", c_rev.cvs_file.canonical_filename)

      Log().warn(
          "Consider rerunning with one or more '--encoding' parameters.\n")
      # It's better to fall back to the original (unknown encoding) data
      # than to either 1) quit or 2) record nothing at all.
      return { 'svn:author' : self._author,
               'svn:log'    : self.get_log_msg(),
               'svn:date'   : date }

  def add_revision(self, cvs_rev):
    self.cvs_revs.append(cvs_rev)

  def flush(self):
    Log().normal("Creating Subversion r%d (%s)"
                 % (self.revnum, self._description))
    Ctx()._persistence_manager.put_svn_commit(self.revnum,
                                              self.cvs_revs,
                                              self._max_date,
                                              self.symbolic_name,
                                              self.motivating_revnum)

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.  This
    description is not intended to be machine-parseable (although
    we're not going to stop you if you try!)"""

    ret = "SVNCommit #: " + str(self.revnum) + "\n"
    if self.symbolic_name:
      ret += ("   symbolic name: "
              + common.clean_symbolic_name(self.symbolic_name)
              + "\n")
    else:
      ret += "   NO symbolic name\n"
    ret += "   debug description: " + self._description + "\n"
    ret += "   cvs_revs:\n"
    for c_rev in self.cvs_revs:
      ret += "     " + c_rev.unique_key() + "\n"
    return ret

  def get_log_msg(self):
    """Returns the actual log message for a primary commit, and the
    appropriate manufactured log message for a secondary commit."""

    if self.symbolic_name is not None:
      return self._log_msg_for_symbolic_name_commit()
    elif self.motivating_revnum is not None:
      return self._log_msg_for_default_branch_commit()
    else:
      return self._log_msg

  def _log_msg_for_symbolic_name_commit(self):
    """Creates a log message for a manufactured commit that fills
    self.symbolic_name.  If self.is_tag is true, write the log message
    as though for a tag, else write it as though for a branch."""

    type = 'branch'
    if self.is_tag:
      type = 'tag'

    # In Python 2.2.3, we could use textwrap.fill().  Oh well :-).
    space_or_newline = ' '
    cleaned_symbolic_name = common.clean_symbolic_name(self.symbolic_name)
    if len(cleaned_symbolic_name) >= 13:
      space_or_newline = '\n'

    return "This commit was manufactured by cvs2svn to create %s%s'%s'." \
           % (type, space_or_newline, cleaned_symbolic_name)

  def _log_msg_for_default_branch_commit(self):
    """Creates a log message for a manufactured commit that
    synchronizes a non-trunk default branch with trunk."""

    msg = 'This commit was generated by cvs2svn to compensate for '     \
          'changes in r%d,\n'                                           \
          'which included commits to RCS files with non-trunk default ' \
          'branches.\n' % self.motivating_revnum
    return msg


