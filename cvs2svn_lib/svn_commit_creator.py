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

"""This module contains the SVNCommitCreator class."""


from __future__ import generators

import time

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.database import Database
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSBranchNoop
from cvs2svn_lib.cvs_item import CVSTagNoop
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import BranchChangeset
from cvs2svn_lib.changeset import TagChangeset
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.svn_commit import SVNPrimaryCommit
from cvs2svn_lib.svn_commit import SVNSymbolCommit
from cvs2svn_lib.svn_commit import SVNPostCommit


class SVNCommitCreator:
  """This class creates and yields SVNCommits via process_changeset()."""

  def _commit(self, timestamp, cvs_revs):
    """Generate the primary SVNCommit for a set of CVSRevisions."""


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
          if (cvs_rev.default_branch_revision
              and not isinstance(cvs_rev, CVSRevisionNoop))
          ]

    if cvs_revs:
      cvs_revs.sort(
          lambda a, b: cmp(a.cvs_file.filename, b.cvs_file.filename)
          )
      # Generate an SVNCommit for all of our default branch cvs_revs.
      yield SVNPostCommit(
          motivating_revnum, cvs_revs, timestamp,
          SVNCommit.revnum_generator.gen_id(),
          )

  def _process_revision_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP as the commit time.

    Create and yield one or more SVNCommits in the process.  CHANGESET
    must be an OrderedChangeset.  TIMESTAMP is used as the timestamp
    for any resulting SVNCommits."""

    if not changeset.cvs_item_ids:
      Log().warn('Changeset has no items: %r' % changeset)
      return

    Log().verbose('-' * 60)
    Log().verbose('CVS Revision grouping:')
    Log().verbose('  Time: %s' % time.ctime(timestamp))

    # Generate an SVNCommit unconditionally.  Even if the only change in
    # this group of CVSRevisions is a deletion of an already-deleted
    # file (that is, a CVS revision in state 'dead' whose predecessor
    # was also in state 'dead'), the conversion will still generate a
    # Subversion revision containing the log message for the second dead
    # revision, because we don't want to lose that information.

    cvs_revs = list(changeset.get_cvs_items())
    if cvs_revs:
      cvs_revs.sort(lambda a, b: cmp(a.cvs_file.filename, b.cvs_file.filename))
      svn_commit = SVNPrimaryCommit(cvs_revs, timestamp)

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
    """Process TagChangeset CHANGESET, producing a SVNSymbolCommit.

    Filter out CVSTagNoops.  If no CVSTags are left, don't generate a
    SVNSymbolCommit."""

    if Ctx().trunk_only:
      raise InternalError(
          'TagChangeset encountered during a --trunk-only conversion')

    cvs_tag_ids = [
        cvs_tag.id
        for cvs_tag in changeset.get_cvs_items()
        if not isinstance(cvs_tag, CVSTagNoop)
        ]
    if cvs_tag_ids:
      yield SVNSymbolCommit(changeset.symbol, cvs_tag_ids, timestamp)
    else:
      Log().debug(
          'Omitting %r because it contains only CVSTagNoops' % (changeset,)
          )

  def _process_branch_changeset(self, changeset, timestamp):
    """Process BranchChangeset CHANGESET, producing a SVNSymbolCommit.

    Filter out CVSBranchNoops.  If no CVSBranches are left, don't
    generate a SVNSymbolCommit."""

    if Ctx().trunk_only:
      raise InternalError(
          'BranchChangeset encountered during a --trunk-only conversion')

    cvs_branches = [
        cvs_branch
        for cvs_branch in changeset.get_cvs_items()
        if not isinstance(cvs_branch, CVSBranchNoop)
        ]
    if cvs_branches:
      svn_commit = SVNSymbolCommit(
          changeset.symbol,
          [cvs_branch.id for cvs_branch in cvs_branches],
          timestamp,
          )
      yield svn_commit
      for cvs_branch in cvs_branches:
        Ctx()._symbolings_logger.log_branch_revision(
            cvs_branch, svn_commit.revnum
            )
    else:
      Log().debug(
          'Omitting %r because it contains only CVSBranchNoops' % (changeset,)
          )

  def process_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP for all of its entries.

    Return a generator that generates the resulting SVNCommits.

    The changesets must be fed to this function in proper dependency
    order."""

    if isinstance(changeset, OrderedChangeset):
      return self._process_revision_changeset(changeset, timestamp)
    elif isinstance(changeset, TagChangeset):
      return self._process_tag_changeset(changeset, timestamp)
    elif isinstance(changeset, BranchChangeset):
      return self._process_branch_changeset(changeset, timestamp)
    else:
      raise TypeError('Illegal changeset %r' % changeset)


