# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

"""This module contains the SVNCommitCreator class."""


import time

from cvs2svn_lib.common import InternalError
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSBranchNoop
from cvs2svn_lib.cvs_item import CVSTagNoop
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import BranchChangeset
from cvs2svn_lib.changeset import TagChangeset
from cvs2svn_lib.svn_commit import SVNInitialProjectCommit
from cvs2svn_lib.svn_commit import SVNPrimaryCommit
from cvs2svn_lib.svn_commit import SVNPostCommit
from cvs2svn_lib.svn_commit import SVNBranchCommit
from cvs2svn_lib.svn_commit import SVNTagCommit
from cvs2svn_lib.key_generator import KeyGenerator


class SVNCommitCreator:
  """This class creates and yields SVNCommits via process_changeset()."""

  def __init__(self):
    # The revision number to assign to the next new SVNCommit.
    self.revnum_generator = KeyGenerator()

    # A set containing the Projects that have already been
    # initialized:
    self._initialized_projects = set()

  def _post_commit(self, cvs_revs, motivating_revnum, timestamp):
    """Generate any SVNCommits needed to follow CVS_REVS.

    That is, handle non-trunk default branches.  A revision on a CVS
    non-trunk default branch is visible in a default CVS checkout of
    HEAD.  So we copy such commits over to Subversion's trunk so that
    checking out SVN trunk gives the same output as checking out of
    CVS's default branch."""

    cvs_revs = [
          cvs_rev
          for cvs_rev in cvs_revs
          if cvs_rev.ntdbr and not isinstance(cvs_rev, CVSRevisionNoop)
          ]

    if cvs_revs:
      cvs_revs.sort(
          lambda a, b: cmp(a.cvs_file.rcs_path, b.cvs_file.rcs_path)
          )
      # Generate an SVNCommit for all of our default branch cvs_revs.
      yield SVNPostCommit(
          motivating_revnum, cvs_revs, timestamp,
          self.revnum_generator.gen_id(),
          )

  def _process_revision_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP as the commit time.

    Create and yield one or more SVNCommits in the process.  CHANGESET
    must be an OrderedChangeset.  TIMESTAMP is used as the timestamp
    for any resulting SVNCommits."""

    if not changeset.cvs_item_ids:
      logger.warn('Changeset has no items: %r' % changeset)
      return

    logger.verbose('-' * 60)
    logger.verbose('CVS Revision grouping:')
    logger.verbose('  Time: %s' % time.ctime(timestamp))

    # Generate an SVNCommit unconditionally.  Even if the only change in
    # this group of CVSRevisions is a deletion of an already-deleted
    # file (that is, a CVS revision in state 'dead' whose predecessor
    # was also in state 'dead'), the conversion will still generate a
    # Subversion revision containing the log message for the second dead
    # revision, because we don't want to lose that information.

    cvs_revs = list(changeset.iter_cvs_items())
    if cvs_revs:
      cvs_revs.sort(lambda a, b: cmp(a.cvs_file.rcs_path, b.cvs_file.rcs_path))
      svn_commit = SVNPrimaryCommit(
          cvs_revs, timestamp, self.revnum_generator.gen_id()
          )

      yield svn_commit

      for cvs_rev in cvs_revs:
        Ctx()._symbolings_logger.log_revision(cvs_rev, svn_commit.revnum)

      # Generate an SVNPostCommit if we have default branch revs.  If
      # some of the revisions in this commit happened on a non-trunk
      # default branch, then those files have to be copied into trunk
      # manually after being changed on the branch (because the RCS
      # "default branch" appears as head, i.e., trunk, in practice).
      # Unfortunately, Subversion doesn't support copies with sources
      # in the current txn.  All copies must be based in committed
      # revisions.  Therefore, we generate the copies in a new
      # revision.
      for svn_post_commit in self._post_commit(
            cvs_revs, svn_commit.revnum, timestamp
            ):
        yield svn_post_commit

  def _process_tag_changeset(self, changeset, timestamp):
    """Process TagChangeset CHANGESET, producing a SVNTagCommit.

    Filter out CVSTagNoops.  If no CVSTags are left, don't generate a
    SVNTagCommit."""

    if Ctx().trunk_only:
      raise InternalError(
          'TagChangeset encountered during a --trunk-only conversion')

    cvs_tag_ids = [
        cvs_tag.id
        for cvs_tag in changeset.iter_cvs_items()
        if not isinstance(cvs_tag, CVSTagNoop)
        ]
    if cvs_tag_ids:
      yield SVNTagCommit(
          changeset.symbol, cvs_tag_ids, timestamp,
          self.revnum_generator.gen_id(),
          )
    else:
      logger.debug(
          'Omitting %r because it contains only CVSTagNoops' % (changeset,)
          )

  def _process_branch_changeset(self, changeset, timestamp):
    """Process BranchChangeset CHANGESET, producing a SVNBranchCommit.

    Filter out CVSBranchNoops.  If no CVSBranches are left, don't
    generate a SVNBranchCommit."""

    if Ctx().trunk_only:
      raise InternalError(
          'BranchChangeset encountered during a --trunk-only conversion')

    cvs_branches = [
        cvs_branch
        for cvs_branch in changeset.iter_cvs_items()
        if not isinstance(cvs_branch, CVSBranchNoop)
        ]
    if cvs_branches:
      svn_commit = SVNBranchCommit(
          changeset.symbol,
          [cvs_branch.id for cvs_branch in cvs_branches],
          timestamp,
          self.revnum_generator.gen_id(),
          )
      yield svn_commit
      for cvs_branch in cvs_branches:
        Ctx()._symbolings_logger.log_branch_revision(
            cvs_branch, svn_commit.revnum
            )
    else:
      logger.debug(
          'Omitting %r because it contains only CVSBranchNoops' % (changeset,)
          )

  def process_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP for all of its entries.

    Return a generator that generates the resulting SVNCommits.

    The changesets must be fed to this function in proper dependency
    order."""

    # First create any new projects that might be opened by the
    # changeset:
    projects_opened = \
        changeset.get_projects_opened() - self._initialized_projects
    if projects_opened:
      if Ctx().cross_project_commits:
        yield SVNInitialProjectCommit(
            timestamp, projects_opened, self.revnum_generator.gen_id()
            )
      else:
        for project in projects_opened:
          yield SVNInitialProjectCommit(
              timestamp, [project], self.revnum_generator.gen_id()
              )
      self._initialized_projects.update(projects_opened)

    if isinstance(changeset, OrderedChangeset):
      for svn_commit \
              in self._process_revision_changeset(changeset, timestamp):
        yield svn_commit
    elif isinstance(changeset, TagChangeset):
      for svn_commit in self._process_tag_changeset(changeset, timestamp):
        yield svn_commit
    elif isinstance(changeset, BranchChangeset):
      for svn_commit in self._process_branch_changeset(changeset, timestamp):
        yield svn_commit
    else:
      raise TypeError('Illegal changeset %r' % changeset)


