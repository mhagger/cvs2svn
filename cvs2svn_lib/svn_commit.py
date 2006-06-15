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

  def __init__(self, description="", revnum=None, cvs_revs=None):
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
    # self.get_revprops() is used to to get them, in dictionary form.
    self._author = Ctx().username
    self._log_msg = "This log message means an SVNCommit was used too soon."

    # The date of the commit, as an integer.  While the SVNCommit is
    # being built up, this contains the latest date seen so far.  This
    # member is set externally.
    self.date = 0

    self.cvs_revs = cvs_revs or []
    if revnum:
      self.revnum = revnum
    else:
      self.revnum = SVNCommit.revnum
      SVNCommit.revnum += 1

    # The (uncleaned) symbolic name that is filled in this SVNCommit
    # (if it filled a symbolic name); otherwise it is None.
    self.symbolic_name = None

    # If this commit is a default branch synchronization, this
    # variable represents the subversion revision number of the
    # *primary* commit where the default branch changes actually
    # happened.  It is None otherwise.  (NOTE: Secondary commits that
    # fill branches and tags also have a motivating commit, but we do
    # not record it because it is (currently) not needed for
    # anything.)  motivating_revnum is used when generating the log
    # message for the commit that synchronizes the default branch with
    # trunk.
    #
    # It is possible for multiple synchronization commits to refer to
    # the same motivating commit revision number, and it is possible
    # for a single synchronization commit to contain CVSRevisions on
    # multiple different default branches.
    self.motivating_revnum = None

    # is_tag is true only if this commit is a fill of a symbolic name
    # that is a tag, None in all other cases.
    self.is_tag = None

  def get_revprops(self):
    """Return the Subversion revprops for this SVNCommit."""

    date = format_date(self.date)
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
        Log().warn(" ", c_rev.cvs_file.filename)

      Log().warn(
          "Consider rerunning with one or more '--encoding' parameters.\n")
      # It's better to fall back to the original (unknown encoding) data
      # than to either 1) quit or 2) record nothing at all.
      return { 'svn:author' : self._author,
               'svn:log'    : self.get_log_msg(),
               'svn:date'   : date }

  def _add_revision(self, cvs_rev):
    self.cvs_revs.append(cvs_rev)

  def __getstate__(self):
    return (
        self.revnum,
        ['%x' % (x.id,) for x in self.cvs_revs],
        self.motivating_revnum, self.symbolic_name,
        self.date)

  def __setstate__(self, state):
    (revnum, c_rev_keys, motivating_revnum, name, date) = state
    SVNCommit.__init__(self, "Retrieved from disk", revnum)

    metadata_id = None
    for key in c_rev_keys:
      c_rev_id = int(key, 16)
      c_rev = Ctx()._cvs_items_db[c_rev_id]
      self._add_revision(c_rev)
      # Set the author and log message for this commit by using
      # CVSRevision metadata, but only if haven't done so already.
      if metadata_id is None:
        metadata_id = c_rev.metadata_id
        self._author, self._log_msg = Ctx()._metadata_db[metadata_id]

    self.date = date

    # If we're doing a trunk-only conversion, we don't need to do any more
    # work.
    if Ctx().trunk_only:
      return

    if name:
      if self.cvs_revs:
        raise SVNCommit.SVNCommitInternalInconsistencyError(
            "An SVNCommit cannot have CVSRevisions *and* a corresponding\n"
            "symbolic name ('%s') to fill."
            % (clean_symbolic_name(name),))
      self.symbolic_name = name
      symbol = Ctx()._symbol_db.get_symbol(name)
      if isinstance(symbol, TagSymbol):
        self.is_tag = 1

    if motivating_revnum is not None:
      self.motivating_revnum = motivating_revnum

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.  This
    description is not intended to be machine-parseable (although
    we're not going to stop you if you try!)"""

    ret = "SVNCommit #: " + str(self.revnum) + "\n"
    if self.symbolic_name:
      ret += ("   symbolic name: "
              + clean_symbolic_name(self.symbolic_name)
              + "\n")
    else:
      ret += "   NO symbolic name\n"
    ret += "   debug description: " + self.description + "\n"
    ret += "   cvs_revs:\n"
    for c_rev in self.cvs_revs:
      ret += "     %x\n" % (c_rev.id,)
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
    cleaned_symbolic_name = clean_symbolic_name(self.symbolic_name)
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


class SVNInitialProjectCommit(SVNCommit):
  def __init__(self, date):
    SVNCommit.__init__(self, 'Initialization', 1)
    self.date = date
    self._log_msg = 'New repository initialized by cvs2svn.'

  def commit(self, repos):
    repos.start_commit(self)
    repos.mkdir(Ctx().project.trunk_path)
    if not Ctx().trunk_only:
      repos.mkdir(Ctx().project.branches_path)
      repos.mkdir(Ctx().project.tags_path)

    repos.end_commit()


class SVNPrimaryCommit(SVNCommit):
  def __init__(self, c_revs):
    SVNCommit.__init__(self, 'commit')
    for c_rev in c_revs:
      self._add_revision(c_rev)

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror."""

    repos.start_commit(self)

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


class SVNSymbolCommit(SVNCommit):
  def __init__(self, description, name):
    SVNCommit.__init__(self, description)
    self.symbolic_name = name

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror."""

    repos.start_commit(self)

    Log().verbose("Filling symbolic name:",
                  clean_symbolic_name(self.symbolic_name))
    repos.fill_symbolic_name(self.symbolic_name)

    repos.end_commit()


class SVNPreCommit(SVNSymbolCommit):
  def __init__(self, name):
    SVNSymbolCommit.__init__(self, 'pre-commit symbolic name %r' % name, name)


class SVNPostCommit(SVNCommit):
  def __init__(self, motivating_revnum, c_revs):
    SVNCommit.__init__(self, 'post-commit default branch(es)')
    self.motivating_revnum = motivating_revnum
    for c_rev in c_revs:
      self._add_revision(c_rev)

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror.

    Propagate any changes that happened on a non-trunk default branch
    to the trunk of the repository.  See CVSCommit._post_commit() for
    details on why this is necessary."""

    repos.start_commit(self)

    Log().verbose("Synchronizing default_branch motivated by %d"
                  % self.motivating_revnum)

    for cvs_rev in self.cvs_revs:
      svn_trunk_path = Ctx().project.make_trunk_path(cvs_rev.cvs_path)
      if cvs_rev.op == OP_ADD or cvs_rev.op == OP_CHANGE:
        if repos.path_exists(svn_trunk_path):
          # Delete the path on trunk...
          repos.delete_path(svn_trunk_path)
        # ...and copy over from branch
        repos.copy_path(cvs_rev.svn_path, svn_trunk_path,
                        self.motivating_revnum)
      elif cvs_rev.op == OP_DELETE:
        # delete trunk path
        repos.delete_path(svn_trunk_path)
      else:
        msg = ("Unknown CVSRevision operation '%s' in default branch sync."
               % cvs_rev.op)
        raise repos.SVNRepositoryMirrorUnexpectedOperationError, msg

    repos.end_commit()


class SVNSymbolCloseCommit(SVNSymbolCommit):
  def __init__(self, name, date):
    SVNSymbolCommit.__init__(self, 'closing tag/branch %r' % name, name)
    self.date = date


