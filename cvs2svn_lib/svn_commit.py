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

"""This module contains the SVNCommit classes.

There are five types of SVNCommits:

  SVNInitialProjectCommit -- Initializes a project (creates its trunk,
      branches, and tags directories).

  SVNPrimaryCommit -- Commits one or more CVSRevisions on one or more
      lines of development.

  SVNBranchCommit -- Creates or fills a branch; that is, copies files
      from a source line of development to a target branch.

  SVNTagCommit -- Creates or fills a tag; that is, copies files from a
      source line of development to a target tag.

  SVNPostCommit -- Updates trunk to reflect changes on a non-trunk
      default branch.

"""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import format_date
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag


class SVNCommit:
  """This represents one commit to the Subversion Repository."""

  def __init__(self, date, revnum):
    """Instantiate an SVNCommit.

    REVNUM is the SVN revision number of this commit."""

    # The date of the commit, as an integer.  While the SVNCommit is
    # being built up, this contains the latest date seen so far.  This
    # member is set externally.
    self.date = date

    # The SVN revision number of this commit, as an integer.
    self.revnum = revnum

  def __getstate__(self):
    return (self.date, self.revnum,)

  def __setstate__(self, state):
    (self.date, self.revnum,) = state

  def get_cvs_items(self):
    """Return a list containing the CVSItems in this commit."""

    raise NotImplementedError()

  def _get_author(self):
    """Return the author or this commit, or None if none is to be used."""

    raise NotImplementedError()

  def _get_log_msg(self):
    """Return a log message for this commit."""

    raise NotImplementedError()

  def get_warning_summary(self):
    """Return a summary of this commit that can be used in warnings."""

    return '(subversion rev %s)' % (self.revnum,)

  def get_revprops(self):
    """Return the Subversion revprops for this SVNCommit."""

    date = format_date(self.date)
    log_msg = self._get_log_msg()
    try:
      utf8_author = None
      author = self._get_author()
      if author is not None:
        utf8_author = Ctx().utf8_encoder(author)
      utf8_log = Ctx().utf8_encoder(log_msg)
      return { 'svn:author' : utf8_author,
               'svn:log'    : utf8_log,
               'svn:date'   : date }
    except UnicodeError:
      Log().warn('%s: problem encoding author or log message:'
                 % warning_prefix)
      Log().warn("  author: '%s'" % self._get_author())
      Log().warn("  log:    '%s'" % log_msg.rstrip())
      Log().warn("  date:   '%s'" % date)
      Log().warn(self.get_warning_summary())
      Log().warn(
          "Consider rerunning with one or more '--encoding' parameters or\n"
          "with '--fallback-encoding'.\n")
      # It's better to fall back to the original (unknown encoding) data
      # than to either 1) quit or 2) record nothing at all.
      return { 'svn:author' : self._get_author(),
               'svn:log'    : log_msg,
               'svn:date'   : date }

  def get_description(self):
    """Return a partial description of this SVNCommit, for logging."""

    raise NotImplementedError()

  def output(self, output_option):
    """Cause this commit to be output to OUTPUT_OPTION.

    This method is used for double-dispatch.  Derived classes should
    call the OutputOption.process_*_commit() method appropriate for
    the type of SVNCommit."""

    raise NotImplementedError()

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    ret = "SVNCommit #: " + str(self.revnum) + "\n"
    ret += "   debug description: " + self.get_description() + "\n"
    return ret


class SVNInitialProjectCommit(SVNCommit):
  def __init__(self, date, projects, revnum):
    SVNCommit.__init__(self, date, revnum)
    self.projects = list(projects)

  def __getstate__(self):
    return (
        SVNCommit.__getstate__(self),
        [project.id for project in self.projects],
        )

  def __setstate__(self, state):
    (svn_commit_state, project_ids,) = state
    SVNCommit.__setstate__(self, svn_commit_state)
    self.projects = [Ctx().projects[project_id] for project_id in project_ids]

  def get_cvs_items(self):
    return []

  def _get_author(self):
    return Ctx().username

  def _get_log_msg(self):
    return 'New repository initialized by cvs2svn.'

  def get_description(self):
    return 'Initialization'

  def output(self, output_option):
    output_option.process_initial_project_commit(self)


class SVNRevisionCommit(SVNCommit):
  """A SVNCommit that includes actual CVS revisions."""

  def __init__(self, cvs_revs, date, revnum):
    SVNCommit.__init__(self, date, revnum)

    self.cvs_revs = list(cvs_revs)

    # These values are set lazily by _get_metadata():
    self._author = None
    self._log_msg = None

  def __getstate__(self):
    """Return the part of the state represented by this mixin."""

    return (
        SVNCommit.__getstate__(self),
        [cvs_rev.id for cvs_rev in self.cvs_revs],
        )

  def __setstate__(self, state):
    """Restore the part of the state represented by this mixin."""

    (svn_commit_state, cvs_rev_ids) = state
    SVNCommit.__setstate__(self, svn_commit_state)

    self.cvs_revs = list(Ctx()._cvs_items_db.get_many(cvs_rev_ids))
    self._author = None
    self._log_msg = None

  def get_cvs_items(self):
    return self.cvs_revs

  def _get_metadata(self):
    """Return the tuple (author, log_msg,) for this commit."""

    if self._author is None:
      # Set self._author and self._log_msg for this commit from that
      # of the first cvs revision.
      if not self.cvs_revs:
        raise InternalError('SVNPrimaryCommit contains no CVS revisions')

      metadata_id = self.cvs_revs[0].metadata_id
      self._author, self._log_msg = Ctx()._metadata_db[metadata_id]

    return self._author, self._log_msg

  def _get_author(self):
    return self._get_metadata()[0]

  def get_warning_summary(self):
    retval = []
    retval.append(SVNCommit.get_warning_summary(self) + '  Related files:')
    for cvs_rev in self.cvs_revs:
      retval.append('  ' + cvs_rev.cvs_file.filename)
    return '\n'.join(retval)

  def __str__(self):
    """Return the revision part of a description of this SVNCommit.

    Derived classes should append the output of this method to the
    output of SVNCommit.__str__()."""

    ret = []
    ret.append(SVNCommit.__str__(self))
    ret.append('   cvs_revs:\n')
    for cvs_rev in self.cvs_revs:
      ret.append('     %x\n' % (cvs_rev.id,))
    return ''.join(ret)


class SVNPrimaryCommit(SVNRevisionCommit):
  def __init__(self, cvs_revs, date, revnum):
    SVNRevisionCommit.__init__(self, cvs_revs, date, revnum)

  def _get_log_msg(self):
    """Return the actual log message for this commit."""

    return self._get_metadata()[1]

  def get_description(self):
    return 'commit'

  def output(self, output_option):
    output_option.process_primary_commit(self)


class SVNPostCommit(SVNRevisionCommit):
  def __init__(self, motivating_revnum, cvs_revs, date, revnum):
    SVNRevisionCommit.__init__(self, cvs_revs, date, revnum)

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
    self.motivating_revnum = motivating_revnum

  def __getstate__(self):
    return (
        SVNRevisionCommit.__getstate__(self),
        self.motivating_revnum,
        )

  def __setstate__(self, state):
    (rev_state, self.motivating_revnum,) = state
    SVNRevisionCommit.__setstate__(self, rev_state)

  def get_cvs_items(self):
    # It might seem that we should return
    # SVNRevisionCommit.get_cvs_items(self) here, but this commit
    # doesn't really include those CVSItems, but rather followup
    # commits to those.
    return []

  def _get_log_msg(self):
    """Return a manufactured log message for this commit."""

    return (
        'This commit was generated by cvs2svn to compensate for '
        'changes in r%d,\n'
        'which included commits to RCS files with non-trunk default '
        'branches.\n') % self.motivating_revnum

  def get_description(self):
    return 'post-commit default branch(es)'

  def output(self, output_option):
    output_option.process_post_commit(self)


class SVNSymbolCommit(SVNCommit):
  def __init__(self, symbol, cvs_symbol_ids, date, revnum):
    SVNCommit.__init__(self, date, revnum)

    # The TypedSymbol that is filled in this SVNCommit.
    self.symbol = symbol

    self.cvs_symbol_ids = cvs_symbol_ids

  def __getstate__(self):
    return (
        SVNCommit.__getstate__(self),
        self.symbol.id, self.cvs_symbol_ids,
        )

  def __setstate__(self, state):
    (svn_commit_state, symbol_id, self.cvs_symbol_ids) = state
    SVNCommit.__setstate__(self, svn_commit_state)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def get_cvs_items(self):
    return list(Ctx()._cvs_items_db.get_many(self.cvs_symbol_ids))

  def _get_symbol_type(self):
    """Return the type of the self.symbol ('branch' or 'tag')."""

    raise NotImplementedError()

  def _get_author(self):
    return Ctx().username

  def _get_log_msg(self):
    """Return a manufactured log message for this commit."""

    # In Python 2.2.3, we could use textwrap.fill().  Oh well :-).
    space_or_newline = ' '
    cleaned_symbolic_name = self.symbol.get_clean_name()
    if len(cleaned_symbolic_name) >= 13:
      space_or_newline = '\n'

    return (
        "This commit was manufactured by cvs2svn to create %s%s'%s'."
        % (self._get_symbol_type(), space_or_newline, cleaned_symbolic_name)
        )

  def get_description(self):
    return 'copying to %s %r' % (self._get_symbol_type(), self.symbol.name,)

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    return (
        SVNCommit.__str__(self)
        + "   symbolic name: %s\n" % self.symbol.get_clean_name())


class SVNBranchCommit(SVNSymbolCommit):
  def __init__(self, symbol, cvs_symbol_ids, date, revnum):
    if not isinstance(symbol, Branch):
      raise InternalError('Incorrect symbol type %r' % (symbol,))

    SVNSymbolCommit.__init__(self, symbol, cvs_symbol_ids, date, revnum)

  def _get_symbol_type(self):
    return 'branch'

  def output(self, output_option):
    output_option.process_branch_commit(self)


class SVNTagCommit(SVNSymbolCommit):
  def __init__(self, symbol, cvs_symbol_ids, date, revnum):
    if not isinstance(symbol, Tag):
      raise InternalError('Incorrect symbol type %r' % (symbol,))

    SVNSymbolCommit.__init__(self, symbol, cvs_symbol_ids, date, revnum)

  def _get_symbol_type(self):
    return 'tag'

  def output(self, output_option):
    output_option.process_tag_commit(self)


