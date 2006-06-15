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


from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import clean_symbolic_name
from cvs2svn_lib.common import format_date
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import OP_ADD
from cvs2svn_lib.common import OP_CHANGE
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol_database import TagSymbol


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

  def __init__(self, description, revnum=None):
    """Instantiate an SVNCommit.  DESCRIPTION is for debugging only.
    If REVNUM, the SVNCommit will correspond to that revision number;
    and if CVS_REVS, then they must be the exact set of CVSRevisions for
    REVNUM.

    It is an error to pass CVS_REVS without REVNUM, but you may pass
    REVNUM without CVS_REVS, and then add a revision at a time by
    invoking add_revision()."""

    self.description = description

    # Revprop metadata for this commit.
    #
    # These initial values are placeholders.  At least the log and the
    # date should be different by the time these are used.
    #
    # They are private because their values should be returned encoded
    # in UTF8, but callers aren't required to set them in UTF8.
    # Therefore, accessor methods are used to set them, and
    # self._get_revprops() is used to to get them, in dictionary form.
    self._author = Ctx().username
    self._log_msg = "This log message means an SVNCommit was used too soon."

    # The date of the commit, as an integer.  While the SVNCommit is
    # being built up, this contains the latest date seen so far.  This
    # member is set externally.
    self.date = 0

    if revnum:
      self.revnum = revnum
    else:
      self.revnum = SVNCommit.revnum
      SVNCommit.revnum += 1

  def _get_revprops(self):
    """Return the Subversion revprops for this SVNCommit."""

    date = format_date(self.date)
    log_msg = self._get_log_msg()
    try:
      utf8_author = None
      if self._author is not None:
        utf8_author = Ctx().to_utf8(self._author)
      utf8_log = Ctx().to_utf8(log_msg)
      return { 'svn:author' : utf8_author,
               'svn:log'    : utf8_log,
               'svn:date'   : date }
    except UnicodeError:
      Log().warn('%s: problem encoding author or log message:'
                 % warning_prefix)
      Log().warn("  author: '%s'" % self._author)
      Log().warn("  log:    '%s'" % log_msg.rstrip())
      Log().warn("  date:   '%s'" % date)
      if isinstance(self, SVNRevisionCommit):
        Log().warn("(subversion rev %s)  Related files:" % self.revnum)
        for c_rev in self.cvs_revs:
          Log().warn(" ", c_rev.cvs_file.filename)
      else:
        Log().warn("(subversion rev %s)" % self.revnum)

      Log().warn(
          "Consider rerunning with one or more '--encoding' parameters.\n")
      # It's better to fall back to the original (unknown encoding) data
      # than to either 1) quit or 2) record nothing at all.
      return { 'svn:author' : self._author,
               'svn:log'    : log_msg,
               'svn:date'   : date }

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    ret = "SVNCommit #: " + str(self.revnum) + "\n"
    ret += "   debug description: " + self.description + "\n"
    return ret


class SVNRevisionCommit(SVNCommit):
  """A mixin for a SVNCommit that includes actual CVS revisions."""

  def __init__(self, c_revs):
    """Initialize the cvs_revs member.

    Derived classes must also call the SVNCommit constructor explicitly."""

    self.cvs_revs = []
    for c_rev in c_revs:
      self.cvs_revs.append(c_rev)

  def __getstate__(self):
    """Return the part of the state represented by this mixin."""

    return ['%x' % (x.id,) for x in self.cvs_revs]

  def __setstate__(self, state):
    """Restore the part of the state represented by this mixin."""

    c_rev_keys = state

    c_revs = []
    for key in c_rev_keys:
      c_rev_id = int(key, 16)
      c_rev = Ctx()._cvs_items_db[c_rev_id]
      c_revs.append(c_rev)

    SVNRevisionCommit.__init__(self, c_revs)

    # Set the author and log message for this commit from the first
    # cvs revision.
    if self.cvs_revs:
      metadata_id = self.cvs_revs[0].metadata_id
      self._author, self._log_msg = Ctx()._metadata_db[metadata_id]

  def __str__(self):
    """Return the revision part of a description of this SVNCommit.

    Derived classes should append the output of this method to the
    output of SVNCommit.__str__()."""

    ret = "   cvs_revs:\n"
    for c_rev in self.cvs_revs:
      ret += "     %x\n" % (c_rev.id,)
    return ret


class SVNInitialProjectCommit(SVNCommit):
  def __init__(self, date, revnum=None):
    SVNCommit.__init__(self, 'Initialization', revnum)
    self.date = date

  def _get_log_msg(self):
    """Return a log message for this commit."""

    return 'New repository initialized by cvs2svn.'

  def commit(self, repos):
    repos.start_commit(self.revnum, self._get_revprops())
    repos.mkdir(Ctx().project.trunk_path)
    if not Ctx().trunk_only:
      repos.mkdir(Ctx().project.branches_path)
      repos.mkdir(Ctx().project.tags_path)

    repos.end_commit()


class SVNPrimaryCommit(SVNCommit, SVNRevisionCommit):
  def __init__(self, c_revs, revnum=None):
    SVNCommit.__init__(self, 'commit', revnum)
    SVNRevisionCommit.__init__(self, c_revs)

  def __str__(self):
    return SVNCommit.__str__(self) + SVNRevisionCommit.__str__(self)

  def _get_log_msg(self):
    """Returns the actual log message for this commit."""

    return self._log_msg

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror."""

    repos.start_commit(self.revnum, self._get_revprops())

    # This actually commits CVSRevisions
    if len(self.cvs_revs) > 1:
      plural = "s"
    else:
      plural = ""
    Log().verbose("Committing %d CVSRevision%s"
                  % (len(self.cvs_revs), plural))
    for cvs_rev in self.cvs_revs:
      # See comment in CVSCommit._commit() for what this is all
      # about.  Note that although asking repos.path_exists() is
      # somewhat expensive, we only do it if the first two (cheap)
      # tests succeed first.
      if (cvs_rev.rev == "1.1.1.1"
          and not cvs_rev.deltatext_exists
          and repos.path_exists(cvs_rev.svn_path)):
        # This change can be omitted.
        pass
      else:
        if cvs_rev.op == OP_ADD:
          repos.add_path(cvs_rev)
        elif cvs_rev.op == OP_CHANGE:
          # Fix for Issue #74:
          #
          # Here's the scenario.  You have file FOO that is imported
          # on a non-trunk vendor branch.  So in r1.1 and r1.1.1.1,
          # the file exists.
          #
          # Moving forward in time, FOO is deleted on the default
          # branch (r1.1.1.2).  cvs2svn determines that this delete
          # also needs to happen on trunk, so FOO is deleted on
          # trunk.
          #
          # Along come r1.2, whose op is OP_CHANGE (because r1.1 is
          # not 'dead', we assume it's a change).  However, since
          # our trunk file has been deleted, svnadmin blows up--you
          # can't change a file that doesn't exist!
          #
          # Soooo... we just check the path, and if it doesn't
          # exist, we do an add... if the path does exist, it's
          # business as usual.
          if not repos.path_exists(cvs_rev.svn_path):
            repos.add_path(cvs_rev)
          else:
            repos.change_path(cvs_rev)

      if cvs_rev.op == OP_DELETE:
        repos.delete_path(cvs_rev.svn_path, Ctx().prune)

    repos.end_commit()

  def __getstate__(self):
    return (self.revnum, self.date, SVNRevisionCommit.__getstate__(self),)

  def __setstate__(self, state):
    (revnum, date, rev_state,) = state
    SVNCommit.__init__(self, "Retrieved from disk", revnum)
    SVNRevisionCommit.__setstate__(self, rev_state)

    self.date = date


class SVNSymbolCommit(SVNCommit):
  def __init__(self, description, name, revnum=None):
    SVNCommit.__init__(self, description, revnum)

    # The (uncleaned) symbolic name that is filled in this SVNCommit.
    self.symbolic_name = name

  def _get_log_msg(self):
    """Return a manufactured log message for this commit."""

    # Determine whether  self.symbolic_name is a tag.
    symbol = Ctx()._symbol_db.get_symbol(self.symbolic_name)
    if isinstance(symbol, TagSymbol):
      type = 'tag'
    else:
      type = 'branch'

    # In Python 2.2.3, we could use textwrap.fill().  Oh well :-).
    space_or_newline = ' '
    cleaned_symbolic_name = clean_symbolic_name(self.symbolic_name)
    if len(cleaned_symbolic_name) >= 13:
      space_or_newline = '\n'

    return "This commit was manufactured by cvs2svn to create %s%s'%s'." \
           % (type, space_or_newline, cleaned_symbolic_name)

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror."""

    repos.start_commit(self.revnum, self._get_revprops())

    Log().verbose("Filling symbolic name:",
                  clean_symbolic_name(self.symbolic_name))
    repos.fill_symbolic_name(self.symbolic_name)

    repos.end_commit()

  def __getstate__(self):
    return (self.revnum, self.symbolic_name, self.date)

  def __setstate__(self, state):
    (revnum, name, date) = state
    SVNSymbolCommit.__init__(self, "Retrieved from disk", name, revnum)

    self.date = date

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    ret = SVNCommit.__str__(self)
    if self.symbolic_name:
      ret += ("   symbolic name: "
              + clean_symbolic_name(self.symbolic_name)
              + "\n")
    return ret


class SVNPreCommit(SVNSymbolCommit):
  def __init__(self, name, revnum=None):
    SVNSymbolCommit.__init__(
        self, 'pre-commit symbolic name %r' % name, name, revnum)


class SVNPostCommit(SVNCommit, SVNRevisionCommit):
  def __init__(self, motivating_revnum, c_revs, revnum=None):
    SVNCommit.__init__(self, 'post-commit default branch(es)', revnum)
    SVNRevisionCommit.__init__(self, c_revs)

    # The subversion revision number of the *primary* commit where the
    # default branch changes actually happened.  (NOTE: Secondary
    # commits that fill branches and tags also have a motivating
    # commit, but we do not record it because it is (currently) not
    # needed for anything.)  motivating_revnum is used when generating
    # the log message for the commit that synchronizes the default
    # branch with trunk.
    #
    # It is possible for multiple synchronization commits to refer to
    # the same motivating commit revision number, and it is possible
    # for a single synchronization commit to contain CVSRevisions on
    # multiple different default branches.
    self._motivating_revnum = motivating_revnum

  def __str__(self):
    return SVNCommit.__str__(self) + SVNRevisionCommit.__str__(self)

  def _get_log_msg(self):
    """Return a manufactured log message for this commit."""

    return (
        'This commit was generated by cvs2svn to compensate for '
        'changes in r%d,\n'
        'which included commits to RCS files with non-trunk default '
        'branches.\n') % self._motivating_revnum

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror.

    Propagate any changes that happened on a non-trunk default branch
    to the trunk of the repository.  See CVSCommit._post_commit() for
    details on why this is necessary."""

    repos.start_commit(self.revnum, self._get_revprops())

    Log().verbose("Synchronizing default_branch motivated by %d"
                  % self._motivating_revnum)

    for cvs_rev in self.cvs_revs:
      svn_trunk_path = Ctx().project.make_trunk_path(cvs_rev.cvs_path)
      if cvs_rev.op == OP_ADD or cvs_rev.op == OP_CHANGE:
        if repos.path_exists(svn_trunk_path):
          # Delete the path on trunk...
          repos.delete_path(svn_trunk_path)
        # ...and copy over from branch
        repos.copy_path(cvs_rev.svn_path, svn_trunk_path,
                        self._motivating_revnum)
      elif cvs_rev.op == OP_DELETE:
        # delete trunk path
        repos.delete_path(svn_trunk_path)
      else:
        msg = ("Unknown CVSRevision operation '%s' in default branch sync."
               % cvs_rev.op)
        raise repos.SVNRepositoryMirrorUnexpectedOperationError, msg

    repos.end_commit()

  def __getstate__(self):
    return (
        self.revnum, self._motivating_revnum, self.date,
        SVNRevisionCommit.__getstate__(self),)

  def __setstate__(self, state):
    (revnum, motivating_revnum, date, rev_state,) = state
    SVNCommit.__init__(self, "Retrieved from disk", revnum)
    SVNRevisionCommit.__setstate__(self, rev_state)

    self.date = date
    self._motivating_revnum = motivating_revnum


class SVNSymbolCloseCommit(SVNSymbolCommit):
  def __init__(self, name, date, revnum=None):
    SVNSymbolCommit.__init__(
        self, 'closing tag/branch %r' % name, name, revnum)
    self.date = date


