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

"""This module contains the CVSRevisionAggregator class."""


from boolean import *
import config
from context import Ctx
from artifact_manager import artifact_manager
from database import Database
from database import SDatabase
from database import DB_OPEN_NEW
from database import DB_OPEN_READ
from openings_closings import SymbolingsLogger
from persistence_manager import PersistenceManager
from cvs_commit import CVSCommit
from svn_commit import SVNCommit


class CVSRevisionAggregator:
  """This class groups CVSRevisions into CVSCommits that represent
  at least one SVNCommit."""

  # How it works:
  # CVSCommits are accumulated within an interval by digest (commit log
  # and author).
  # In a previous implementation, we would just close a CVSCommit for further
  # CVSRevisions and open a new CVSCommit if a second CVSRevision with the
  # same (CVS) path arrived within the accumulation window.
  # In the new code, there can be multiple open CVSCommits touching the same
  # files within an accumulation window.  A hash of pending CVSRevisions with
  # associated CVSCommits is maintained.  If a new CVSRevision is found to
  # have a prev_rev in this hash, the corresponding CVSCommit is not
  # eligible for accomodating the revision, but will be added to the
  # dependency list of the commit the revision finally goes into.  When a
  # CVSCommit moves out of its accumulation window it is not scheduled for
  # flush immediately, but instead enqueued in expired_queue.  Only if all
  # the CVSCommits this one depends on went out already, it can go out as
  # well.  Timestamps are adjusted accordingly - it could happen that a small
  # CVSCommit is commited while a big commit it depends on is still underway
  # in other directories.

  def __init__(self):
    self._metadata_db = Database(
        artifact_manager.get_temp_file(config.METADATA_DB), DB_OPEN_READ)
    if not Ctx().trunk_only:
      self.last_revs_db = Database(
          artifact_manager.get_temp_file(config.SYMBOL_LAST_CVS_REVS_DB),
          DB_OPEN_READ)

    # Map of CVSRevision digests to arrays of open CVSCommits.  In each such
    # array, every element has direct or indirect dependencies on all the
    # preceding elements in the same array.
    self.cvs_commits = {}

    # Map of CVSRevision unique keys to CVSCommits they are part of.
    self.pending_revs = {}

    # List of closed CVSCommits which might still have pending dependencies.
    self.expired_queue = []

    # List of CVSCommits that are ready to be committed, but
    # might need to be delayed until a CVSRevision with a later timestamp
    # is read.  (This can happen if the timestamp of the ready CVSCommit
    # had to be adjusted to make it later than its dependencies.)
    self.ready_queue = [ ]

    # A map { symbol : None } of symbolic names for which the last
    # source CVSRevision has already been processed but which haven't
    # been closed yet.
    self.pending_symbols = {}

    # A list of closed symbols.  That is, we've already encountered
    # the last CVSRevision that is a source for that symbol, the final
    # fill for this symbol has been done, and we never need to fill it
    # again.
    self.done_symbols = [ ]

    # This variable holds the most recently created primary svn_commit
    # object.  CVSRevisionAggregator maintains this variable merely
    # for its date, so that it can set dates for the SVNCommits
    # created in self._attempt_to_commit_symbols().
    self.latest_primary_svn_commit = None

    Ctx()._symbolings_logger = SymbolingsLogger()
    Ctx()._persistence_manager = PersistenceManager(DB_OPEN_NEW)
    Ctx()._default_branches_db = SDatabase(
        artifact_manager.get_temp_file(config.DEFAULT_BRANCHES_DB),
        DB_OPEN_READ)

  def _get_deps(self, c_rev, deps):
    """Add the CVSCommits that this C_REV depends on to DEPS, which is a
    map { CVSCommit : None }.  The result includes both direct and indirect
    dependencies, because it is used to determine what CVSCommit we can
    be added to.  Return the commit C_REV depends on directly, if any;
    otherwise return None."""

    if c_rev.prev_id is None:
      return None
    dep = self.pending_revs.get('%x' % (c_rev.prev_id,), None)
    if dep is None:
      return None
    deps[dep] = None
    for r in dep.revisions():
      self._get_deps(r, deps)
    return dep

  def _extract_ready_commits(self, timestamp=None):
    """Extract any active commits that expire by TIMESTAMP from
    self.cvs_commits and append them to self.ready_queue.  If
    TIMESTAMP is not specified, then extract all commits."""

    # First take all expired commits out of the pool of available commits.
    for digest_key, cvs_commits in self.cvs_commits.items():
      for cvs_commit in cvs_commits[:]:
        if timestamp is None \
               or cvs_commit.t_max + config.COMMIT_THRESHOLD < timestamp:
          self.expired_queue.append(cvs_commit)
          cvs_commits.remove(cvs_commit)
      if not cvs_commits:
        del self.cvs_commits[digest_key]

    # Then queue all closed commits with resolved dependencies for commit.
    # We do this here instead of in _commit_ready_commits to avoid building
    # deps on revisions that will be flushed immediately afterwards.
    while self.expired_queue:
      chg = False
      for cvs_commit in self.expired_queue[:]:
        if cvs_commit.resolve_dependencies():
          for r in cvs_commit.revisions():
            del self.pending_revs[r.unique_key()]
          self.expired_queue.remove(cvs_commit)
          cvs_commit.pending = False
          self.ready_queue.append(cvs_commit)
          chg = True
      if not chg:
        break

  def _commit_ready_commits(self, timestamp=None):
    """Sort the commits from self.ready_queue by time, then process
    them in order.  If TIMESTAMP is specified, only process commits
    that have timestamp previous to TIMESTAMP."""

    self.ready_queue.sort()
    while self.ready_queue and \
              (timestamp is None or self.ready_queue[0].t_max < timestamp):
      cvs_commit = self.ready_queue.pop(0)
      self.latest_primary_svn_commit = \
          cvs_commit.process_revisions(self.done_symbols)
      self._attempt_to_commit_symbols()

  def process_revision(self, c_rev):
    # Each time we read a new line, scan the accumulating commits to
    # see if any are ready for processing.
    self._extract_ready_commits(c_rev.timestamp)

    # Add this item into the set of still-available commits.
    deps = {}
    dep = self._get_deps(c_rev, deps)
    cvs_commits = self.cvs_commits.setdefault(c_rev.digest, [])
    # This is pretty silly; it will add the revision to the oldest pending
    # commit. It might be wiser to do time range matching to avoid stretching
    # commits more than necessary.
    for cvs_commit in cvs_commits:
      if not deps.has_key(cvs_commit):
        break
    else:
      author, log = self._metadata_db[c_rev.digest]
      cvs_commit = CVSCommit(c_rev.digest, author, log)
      cvs_commits.append(cvs_commit)
    if dep is not None:
      cvs_commit.add_dependency(dep)
    cvs_commit.add_revision(c_rev)
    self.pending_revs[c_rev.unique_key()] = cvs_commit

    # If there are any elements in the ready_queue at this point, they
    # need to be processed, because this latest rev couldn't possibly
    # be part of any of them.  Limit the timestamp of commits to be
    # processed, because re-stamping according to a commit's
    # dependencies can alter the commit's timestamp.
    self._commit_ready_commits(c_rev.timestamp)

    self._add_pending_symbols(c_rev)

  def flush(self):
    """Commit anything left in self.cvs_commits.  Then inform the
    SymbolingsLogger that all commits are done."""

    self._extract_ready_commits()
    self._commit_ready_commits()

    if not Ctx().trunk_only:
      Ctx()._symbolings_logger.close()

  def _add_pending_symbols(self, c_rev):
    """Add to self.pending_symbols any symbols from C_REV for which
    C_REV is the last CVSRevision.

    If we're not doing a trunk-only conversion, get the symbolic names
    that this c_rev is the last *source* CVSRevision for and add them
    to those left over from previous passes through the aggregator."""

    if not Ctx().trunk_only:
      for sym in self.last_revs_db.get(c_rev.unique_key(), []):
        self.pending_symbols[sym] = None

  def _attempt_to_commit_symbols(self):
    """Generate one SVNCommit for each symbol in self.pending_symbols
    that doesn't have an opening CVSRevision in either
    self.cvs_commits, self.expired_queue or self.ready_queue."""

    # Make a list of all symbols from self.pending_symbols that do not
    # have *source* CVSRevisions in the pending commit queues
    # (self.expired_queue or self.ready_queue):
    closeable_symbols = []
    pending_commits = self.expired_queue + self.ready_queue
    for commits in self.cvs_commits.itervalues():
      pending_commits.extend(commits)
    for sym in self.pending_symbols:
      for cvs_commit in pending_commits:
        if cvs_commit.opens_symbolic_name(sym):
          break
      else:
        closeable_symbols.append(sym)

    # Sort the closeable symbols so that we will always process the
    # symbols in the same order, regardless of the order in which the
    # dict hashing algorithm hands them back to us.  We do this so
    # that our tests will get the same results on all platforms.
    closeable_symbols.sort()
    for sym in closeable_symbols:
      svn_commit = SVNCommit("closing tag/branch '%s'" % sym)
      svn_commit.set_symbolic_name(sym)
      svn_commit.set_date(self.latest_primary_svn_commit.get_date())
      svn_commit.flush()
      self.done_symbols.append(sym)
      del self.pending_symbols[sym]


