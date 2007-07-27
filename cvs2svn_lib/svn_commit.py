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

There are four types of SVNCommits:

  SVNInitialProjectCommit -- Initializes a project (creates its trunk,
      branches, and tags directories).

  SVNPrimaryCommit -- Commits one or more CVSRevisions on one or more
      lines of development.

  SVNSymbolCommit -- Creates or fills a symbolic name; that is, copies
      files from a source line of development to a target branch or
      tag.

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
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop


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

  def get_cvs_items(self):
    """Return a list containing the CVSItems in this commit."""

    raise NotImplementedError()

  def _get_author(self):
    """Return the author or this commit, or None if none is to be used."""

    raise NotImplementedError()

  def _get_log_msg(self):
    """Return a log message for this commit."""

    raise NotImplementedError()

  def _get_revprops(self):
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
      if isinstance(self, SVNRevisionCommit):
        Log().warn("(subversion rev %s)  Related files:" % self.revnum)
        for cvs_rev in self.cvs_revs:
          Log().warn(" ", cvs_rev.cvs_file.filename)
      else:
        Log().warn("(subversion rev %s)" % self.revnum)

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

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    ret = "SVNCommit #: " + str(self.revnum) + "\n"
    ret += "   debug description: " + self.get_description() + "\n"
    return ret

  def __getstate__(self):
    return (self.date, self.revnum,)

  def __setstate__(self, state):
    (self.date, self.revnum,) = state


class SVNRevisionCommit(SVNCommit):
  """A SVNCommit that includes actual CVS revisions."""

  def __init__(self, cvs_revs, date, revnum):
    SVNCommit.__init__(self, date, revnum)

    self.cvs_revs = list(cvs_revs)

    # These values are set lazily by _get_metadata():
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


class SVNInitialProjectCommit(SVNCommit):
  def __init__(self, date, projects, revnum):
    SVNCommit.__init__(self, date, revnum)
    self.projects = list(projects)

  def get_cvs_items(self):
    return []

  def _get_author(self):
    return Ctx().username

  def _get_log_msg(self):
    return 'New repository initialized by cvs2svn.'

  def get_description(self):
    return 'Initialization'

  def commit(self, repos):
    # FIXME: It would be nicer to create a project's TTB directories
    # only after the first commit to the project.

    repos.start_commit(self.revnum, self._get_revprops())

    for project in self.projects:
      # For a trunk-only conversion, trunk_path might be ''.
      if project.trunk_path:
        repos.mkdir(project.trunk_path)
      if not Ctx().trunk_only:
        repos.mkdir(project.branches_path)
        repos.mkdir(project.tags_path)

    repos.end_commit()

  def __getstate__(self):
    return (
        SVNCommit.__getstate__(self),
        [project.id for project in self.projects],
        )

  def __setstate__(self, state):
    (svn_commit_state, project_ids,) = state
    SVNCommit.__setstate__(self, svn_commit_state)
    self.projects = [Ctx().projects[project_id] for project_id in project_ids]


class SVNPrimaryCommit(SVNRevisionCommit):
  def __init__(self, cvs_revs, date, revnum):
    SVNRevisionCommit.__init__(self, cvs_revs, date, revnum)

  def _get_log_msg(self):
    """Return the actual log message for this commit."""

    return self._get_metadata()[1]

  def get_description(self):
    return 'commit'

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
      if isinstance(cvs_rev, CVSRevisionNoop):
        pass

      elif isinstance(cvs_rev, CVSRevisionDelete):
        repos.delete_path(cvs_rev.get_svn_path(), Ctx().prune)

      elif isinstance(cvs_rev, CVSRevisionAdd):
        repos.add_path(cvs_rev)

      elif isinstance(cvs_rev, CVSRevisionChange):
        repos.change_path(cvs_rev)

    repos.end_commit()


class SVNSymbolCommit(SVNCommit):
  def __init__(self, symbol, cvs_symbol_ids, date, revnum):
    SVNCommit.__init__(self, date, revnum)

    # The TypedSymbol that is filled in this SVNCommit.
    self.symbol = symbol

    self.cvs_symbol_ids = cvs_symbol_ids

  def get_cvs_items(self):
    return list(Ctx()._cvs_items_db.get_many(self.cvs_symbol_ids))

  def _get_author(self):
    return Ctx().username

  def _get_log_msg(self):
    """Return a manufactured log message for this commit."""

    # Determine whether self.symbol is a tag.
    if isinstance(self.symbol, Tag):
      type = 'tag'
    else:
      assert isinstance(self.symbol, Branch)
      type = 'branch'

    # In Python 2.2.3, we could use textwrap.fill().  Oh well :-).
    space_or_newline = ' '
    cleaned_symbolic_name = self.symbol.get_clean_name()
    if len(cleaned_symbolic_name) >= 13:
      space_or_newline = '\n'

    return "This commit was manufactured by cvs2svn to create %s%s'%s'." \
           % (type, space_or_newline, cleaned_symbolic_name)

  def get_description(self):
    return 'copying to tag/branch %r' % self.symbol.name

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror."""

    repos.start_commit(self.revnum, self._get_revprops())
    Log().verbose("Filling symbolic name:", self.symbol.get_clean_name())
    repos.fill_symbol(self)

    repos.end_commit()

  def __getstate__(self):
    return (
        SVNCommit.__getstate__(self),
        self.symbol.id, self.cvs_symbol_ids,
        )

  def __setstate__(self, state):
    (svn_commit_state, symbol_id, self.cvs_symbol_ids) = state
    SVNCommit.__setstate__(self, svn_commit_state)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)

  def __str__(self):
    """ Print a human-readable description of this SVNCommit.

    This description is not intended to be machine-parseable."""

    return (
        SVNCommit.__str__(self)
        + "   symbolic name: %s\n" % self.symbol.get_clean_name())


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
    self._motivating_revnum = motivating_revnum

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
        'branches.\n') % self._motivating_revnum

  def get_description(self):
    return 'post-commit default branch(es)'

  def commit(self, repos):
    """Commit SELF to REPOS, which is a SVNRepositoryMirror.

    Propagate any changes that happened on a non-trunk default branch
    to the trunk of the repository.  See
    SVNCommitCreator._post_commit() for details on why this is
    necessary."""

    repos.start_commit(self.revnum, self._get_revprops())

    Log().verbose("Synchronizing default_branch motivated by %d"
                  % self._motivating_revnum)

    for cvs_rev in self.cvs_revs:
      svn_trunk_path = cvs_rev.cvs_file.project.get_trunk_path(
          cvs_rev.cvs_path)
      if isinstance(cvs_rev, CVSRevisionAdd):
        # Copy from branch to trunk:
        repos.copy_path(
            cvs_rev.get_svn_path(), svn_trunk_path,
            self._motivating_revnum, True
            )
      elif isinstance(cvs_rev, CVSRevisionChange):
        # Delete old version of the path on trunk...
        repos.delete_path(svn_trunk_path)
        # ...and copy the new version over from branch:
        repos.copy_path(
            cvs_rev.get_svn_path(), svn_trunk_path,
            self._motivating_revnum, True
            )
      elif isinstance(cvs_rev, CVSRevisionDelete):
        # Delete trunk path:
        repos.delete_path(svn_trunk_path)
      elif isinstance(cvs_rev, CVSRevisionNoop):
        # Do nothing
        pass
      else:
        raise InternalError('Unexpected CVSRevision type: %s' % (cvs_rev,))

    repos.end_commit()

  def __getstate__(self):
    return (
        SVNRevisionCommit.__getstate__(self),
        self._motivating_revnum,
        )

  def __setstate__(self, state):
    (rev_state, self._motivating_revnum,) = state
    SVNRevisionCommit.__setstate__(self, rev_state)


