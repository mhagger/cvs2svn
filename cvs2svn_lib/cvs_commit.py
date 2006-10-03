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

import time

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import OP_ADD
from cvs2svn_lib.common import OP_CHANGE
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.svn_commit import SVNPrimaryCommit
from cvs2svn_lib.svn_commit import SVNPreCommit
from cvs2svn_lib.svn_commit import SVNPostCommit
from cvs2svn_lib.log import Log
from cvs2svn_lib.line_of_development import Branch


class CVSCommit:
  """Each instance of this class contains a number of CVS Revisions
  that correspond to one or more Subversion Commits.  After all CVS
  Revisions are added to the grouping, calling process_revisions will
  generate a Subversion Commit (or Commits) for the set of CVS
  Revisions in the grouping."""

  def __init__(self, metadata_id, author, log, timestamp):
    self.metadata_id = metadata_id
    self.author = author
    self.log = log
    self.timestamp = timestamp

    # Lists of CVSRevisions
    self.changes = [ ]
    self.deletes = [ ]

    # This will be set to the SVNCommit that occurs in self._commit.
    self.motivating_commit = None

    # This is a list of all non-primary SVNCommits motivated by the
    # main commit.  We gather these so that we can set their dates to
    # the same date as the primary commit.
    self.secondary_commits = [ ]

    # State for handling default branches.
    #
    # Here is a tempting, but ultimately nugatory, bit of logic, which
    # I share with you so you may appreciate the less attractive, but
    # refreshingly non-nugatory, logic which follows it:
    #
    # If some of the commits in this txn happened on a non-trunk
    # default branch, then those files will have to be copied into
    # trunk manually after being changed on the branch (because the
    # RCS "default branch" appears as head, i.e., trunk, in practice).
    # As long as those copies don't overwrite any trunk paths that
    # were also changed in this commit, then we can do the copies in
    # the same revision, because they won't cover changes that don't
    # appear anywhere/anywhen else.  However, if some of the trunk dst
    # paths *did* change in this commit, then immediately copying the
    # branch changes would lose those trunk mods forever.  So in this
    # case, we need to do at least that copy in its own revision.  And
    # for simplicity's sake, if we're creating the new revision for
    # even one file, then we just do all such copies together in the
    # new revision.
    #
    # Doesn't that sound nice?
    #
    # Unfortunately, Subversion doesn't support copies with sources
    # in the current txn.  All copies must be based in committed
    # revisions.  Therefore, we generate the above-described new
    # revision unconditionally.
    #
    # This is a list of cvs_revs, and a cvs_rev is appended for each
    # default branch commit that will need to be copied to trunk (or
    # deleted from trunk) in some generated revision following the
    # "regular" revision.
    self.default_branch_cvs_revisions = [ ]

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'CVSCommit([%s], [%s])' % (
        ', '.join([str(change) for change in self.changes]),
        ', '.join([str(delete) for delete in self.deletes]),)

  def __cmp__(self, other):
    # Commits should be sorted by t_max.  If both self and other have
    # the same t_max, break the tie using t_min, and lastly,
    # metadata_id.  If all those are equal, then compare based on ids,
    # to ensure that no two instances compare equal.
    return (cmp(self.timestamp, other.timestamp)
            or cmp(self.metadata_id, other.metadata_id)
            or cmp(id(self), id(other)))

  def __hash__(self):
    return id(self)

  def revisions(self):
    return self.changes + self.deletes

  def opens_symbol(self, symbol_id):
    """Return True if any CVSRevision in this commit is on a tag or a
    branch or is the origin of a tag or branch."""

    for cvs_rev in self.revisions():
      if cvs_rev.opens_symbol(symbol_id):
        return True
    return False

  def add_revision(self, cvs_rev):
    if cvs_rev.op == OP_DELETE:
      self.deletes.append(cvs_rev)
    else:
      # OP_CHANGE or OP_ADD
      self.changes.append(cvs_rev)

  def _pre_commit(self, done_symbols):
    """Generate any SVNCommits that must exist before the main commit.

    DONE_SYMBOLS is a set of symbols for which the last source
    revision has already been seen and for which the
    CVSRevisionCreator has already generated a fill SVNCommit.  See
    self.process_revisions()."""

    # There may be multiple cvs_revs in this commit that would cause
    # branch B to be filled, but we only want to fill B once.  On the
    # other hand, there might be multiple branches committed on in
    # this commit.  Whatever the case, we should count exactly one
    # commit per branch, because we only fill a branch once per
    # CVSCommit.  This list tracks which symbols we've already
    # counted.
    accounted_for_symbols = set()

    def fill_needed(cvs_rev):
      """Return True iff this is the first commit on a new branch (for
      this file) and we need to fill the branch; else return False.
      See comments below for the detailed rules."""

      if cvs_rev.first_on_branch_id is None:
        # Only commits that are the first on their branch can force fills:
        return False

      pm = Ctx()._persistence_manager
      prev_svn_revnum = pm.get_svn_revnum(cvs_rev.prev_id)

      # It should be the case that when we have a file F that is
      # added on branch B (thus, F on trunk is in state 'dead'), we
      # generate an SVNCommit to fill B iff the branch has never
      # been filled before.
      if cvs_rev.op == OP_ADD:
        # Fill the branch only if it has never been filled before:
        return cvs_rev.lod.symbol.id not in pm.last_filled
      elif cvs_rev.op == OP_CHANGE:
        # We need to fill only if the last commit affecting the file
        # has not been filled yet:
        return prev_svn_revnum > pm.last_filled.get(cvs_rev.lod.symbol.id, 0)
      elif cvs_rev.op == OP_DELETE:
        # If the previous revision was also a delete, we don't need
        # to fill it - and there's nothing to copy to the branch, so
        # we can't anyway.  No one seems to know how to get CVS to
        # produce the double delete case, but it's been observed.
        if Ctx()._cvs_items_db[cvs_rev.prev_id].op == OP_DELETE:
          return False
        # Other deletes need fills only if the last commit affecting
        # the file has not been filled yet:
        return prev_svn_revnum > pm.last_filled.get(cvs_rev.lod.symbol.id, 0)

    for cvs_rev in self.changes + self.deletes:
      # If a commit is on a branch, we must ensure that the branch
      # path being committed exists (in HEAD of the Subversion
      # repository).  If it doesn't exist, we will need to fill the
      # branch.  After the fill, the path on which we're committing
      # will exist.
      if isinstance(cvs_rev.lod, Branch) \
          and cvs_rev.lod.symbol not in accounted_for_symbols \
          and cvs_rev.lod.symbol not in done_symbols \
          and fill_needed(cvs_rev):
        symbol = cvs_rev.lod.symbol
        self.secondary_commits.append(SVNPreCommit(symbol))
        accounted_for_symbols.add(symbol)

  def _commit(self):
    """Generates the primary SVNCommit that corresponds to this
    CVSCommit."""

    def delete_needed(cvs_rev):
      """Return True iff the specified delete CVS_REV is really needed.

      When a file is added on a branch, CVS not only adds the file on
      the branch, but generates a trunk revision (typically 1.1) for
      that file in state 'dead'.  We only want to add this revision if
      the log message is not the standard cvs fabricated log message."""

      if cvs_rev.prev_id is not None:
        return True

      # cvs_rev.branch_ids may be empty if the originating branch has
      # been excluded.
      if not cvs_rev.branch_ids:
        return False
      # FIXME: This message will not match if the RCS file was renamed
      # manually after it was created.
      cvs_generated_msg = 'file %s was initially added on branch %s.\n' % (
          cvs_rev.cvs_file.basename,
          Ctx()._cvs_items_db[cvs_rev.branch_ids[0]].symbol.name,)
      author, log_msg = Ctx()._metadata_db[cvs_rev.metadata_id]
      return log_msg != cvs_generated_msg

    # Generate an SVNCommit unconditionally.  Even if the only change
    # in this CVSCommit is a deletion of an already-deleted file (that
    # is, a CVS revision in state 'dead' whose predecessor was also in
    # state 'dead'), the conversion will still generate a Subversion
    # revision containing the log message for the second dead
    # revision, because we don't want to lose that information.
    needed_deletes = [ cvs_rev
                       for cvs_rev in self.deletes
                       if delete_needed(cvs_rev)
                       ]
    svn_commit = SVNPrimaryCommit(self.changes + needed_deletes)
    self.motivating_commit = svn_commit

    for cvs_rev in self.changes:
      # Only make a change if we need to:
      if cvs_rev.rev == "1.1.1.1" and not cvs_rev.deltatext_exists:
        # When 1.1.1.1 has an empty deltatext, the explanation is
        # almost always that we're looking at an imported file whose
        # 1.1 and 1.1.1.1 are identical.  On such imports, CVS creates
        # an RCS file where 1.1 has the content, and 1.1.1.1 has an
        # empty deltatext, i.e, the same content as 1.1.  There's no
        # reason to reflect this non-change in the repository, so we
        # want to do nothing in this case.  (If we were really
        # paranoid, we could make sure 1.1's log message is the
        # CVS-generated "Initial revision\n", but I think the
        # conditions above are strict enough.)
        pass
      else:
        if cvs_rev.default_branch_revision:
          self.default_branch_cvs_revisions.append(cvs_rev)

    for cvs_rev in needed_deletes:
      if cvs_rev.default_branch_revision:
        self.default_branch_cvs_revisions.append(cvs_rev)

    svn_commit.date = self.timestamp

    # There is a slight chance that we didn't actually register any
    # CVSRevisions with our SVNCommit (see loop over self.deletes
    # above), so if we have no CVSRevisions, we don't flush the
    # svn_commit to disk and roll back our revnum.
    if svn_commit.cvs_revs:
      Ctx()._persistence_manager.put_svn_commit(svn_commit)
    else:
      # We will not be flushing this SVNCommit, so rollback the
      # SVNCommit revision counter.
      SVNCommit.revnum -= 1

    if not Ctx().trunk_only:
      for cvs_rev in self.revisions():
        Ctx()._symbolings_logger.log_revision(cvs_rev, svn_commit.revnum)

  def _post_commit(self):
    """Generates any SVNCommits that we can perform now that _commit
    has happened.  That is, handle non-trunk default branches.
    Sometimes an RCS file has a non-trunk default branch, so a commit
    on that default branch would be visible in a default CVS checkout
    of HEAD.  If we don't copy that commit over to Subversion's trunk,
    then there will be no Subversion tree which corresponds to that
    CVS checkout.  Of course, in order to copy the path over, we may
    first need to delete the existing trunk there."""

    # Only generate a commit if we have default branch revs
    if self.default_branch_cvs_revisions:
      # Generate an SVNCommit for all of our default branch cvs_revs.
      svn_commit = SVNPostCommit(self.motivating_commit.revnum,
                                 self.default_branch_cvs_revisions)
      for cvs_rev in self.default_branch_cvs_revisions:
        Ctx()._symbolings_logger.log_default_branch_closing(
            cvs_rev, svn_commit.revnum)
      self.secondary_commits.append(svn_commit)

  def process_revisions(self, done_symbols):
    """Process all the CVSRevisions that this instance has, creating
    one or more SVNCommits in the process.  Generate fill SVNCommits
    only for symbols not in DONE_SYMBOLS (avoids unnecessary
    fills)."""

    Log().verbose('-' * 60)
    Log().verbose('CVS Revision grouping:')
    Log().verbose('  Time: %s' % time.ctime(self.timestamp))

    if Ctx().trunk_only:
      # When trunk-only, only do the primary commit:
      self._commit()
    else:
      self._pre_commit(done_symbols)
      self._commit()
      self._post_commit()

      for svn_commit in self.secondary_commits:
        svn_commit.date = self.motivating_commit.date
        Ctx()._persistence_manager.put_svn_commit(svn_commit)


