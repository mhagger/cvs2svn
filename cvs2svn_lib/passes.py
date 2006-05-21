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

"""This module contains database facilities used by cvs2svn."""


import sys
import os
import time
import fileinput
import re
import sha

from boolean import *
import config
from context import Ctx
from common import warning_prefix
from common import error_prefix
from common import FatalException
from common import FatalError
from log import Log
from artifact_manager import artifact_manager
from database import Database
from database import DB_OPEN_NEW
from database import DB_OPEN_READ
from database import DB_OPEN_WRITE
from cvs_file_database import CVSFileDatabase
from symbol_database import SymbolDatabase
from tags_database import TagsDatabase
from cvs_revision_database import CVSRevisionDatabase
from last_symbolic_name_database import LastSymbolicNameDatabase
from svn_commit import SVNCommit
from cvs_revision_aggregator import CVSRevisionAggregator
from svn_repository_mirror import SVNRepositoryMirror
from persistence_manager import PersistenceManager
from dumpfile_delegate import DumpfileDelegate
from repository_delegate import RepositoryDelegate
from stdout_delegate import StdoutDelegate
from collect_data import CollectData
from process import run_command


ctrl_characters_regexp = re.compile('[\\\x00-\\\x1f\\\x7f]')

def verify_filename_legal(filename):
  """Verify that FILENAME does not include any control characters.  If
  it does, raise a FatalError."""

  m = ctrl_characters_regexp.search(filename)
  if m:
    raise FatalError(
        "Character %r in filename %r is not supported by subversion."
        % (m.group(), filename,))


def sort_file(infilename, outfilename):
  """Sort file INFILENAME, storing the results to OUTFILENAME."""

  # GNU sort will sort our dates differently (incorrectly!) if our
  # LC_ALL is anything but 'C', so if LC_ALL is set, temporarily set
  # it to 'C'
  lc_all_tmp = os.environ.get('LC_ALL', None)
  os.environ['LC_ALL'] = 'C'
  try:
    # The -T option to sort has a nice side effect.  The Win32 sort is
    # case insensitive and cannot be used, and since it does not
    # understand the -T option and dies if we try to use it, there is
    # no risk that we use that sort by accident.
    run_command('sort -T %s %s > %s'
                % (Ctx().tmpdir, infilename, outfilename))
  finally:
    if lc_all_tmp is None:
      del os.environ['LC_ALL']
    else:
      os.environ['LC_ALL'] = lc_all_tmp


class Pass:
  """Base class for one step of the conversion."""

  def __init__(self):
    # By default, use the pass object's class name as the pass name:
    self.name = self.__class__.__name__

  def register_artifacts(self):
    """Register artifacts (created and needed) in artifact_manager."""

    raise NotImplementedError

  def _register_temp_file(self, basename):
    """Helper method; for brevity only."""

    artifact_manager.register_temp_file(basename, self)

  def _register_temp_file_needed(self, basename):
    """Helper method; for brevity only."""

    artifact_manager.register_temp_file_needed(basename, self)

  def run(self, stats_keeper):
    """Carry out this step of the conversion.
    STATS_KEEPER is a StatsKeeper instance."""

    raise NotImplementedError


class CollectRevsPass(Pass):
  """This pass was formerly known as pass1."""

  def register_artifacts(self):
    self._register_temp_file(config.TAGS_LIST)
    self._register_temp_file(config.BRANCHES_LIST)
    self._register_temp_file(config.RESYNC_DATAFILE)
    self._register_temp_file(config.METADATA_DB)
    self._register_temp_file(config.CVS_FILES_DB)
    self._register_temp_file(config.CVS_REVS_DB)
    self._register_temp_file(config.ALL_REVS_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Examining all CVS ',v' files...")
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_NEW)
    cd = CollectData(stats_keeper)

    def visit_file(cd, dirname, files):
      for fname in files:
        verify_filename_legal(fname)
        if not fname.endswith(',v'):
          continue
        cd.found_valid_file = 1
        pathname = os.path.join(dirname, fname)
        Log().normal(pathname)

        cd.process_file(pathname)

    os.path.walk(Ctx().project.project_cvs_repos_path, visit_file, cd)
    Log().verbose('Processed', cd.num_files, 'files')

    cd.write_symbol_db()

    if len(cd.fatal_errors) > 0:
      raise FatalException("Pass 1 complete.\n"
                           + "=" * 75 + "\n"
                           + "Error summary:\n"
                           + "\n".join(cd.fatal_errors) + "\n"
                           + "Exited due to fatal error(s).\n")

    if cd.found_valid_file is None:
      raise FatalException(
          "\n"
          "No RCS files found in your CVS Repository!\n"
          "Are you absolutely certain you are pointing cvs2svn\n"
          "at a CVS repository?\n"
          "\n"
          "Exited due to fatal error(s).\n")

    stats_keeper.reset_c_rev_info()
    stats_keeper.archive()
    Log().quiet("Done")


class ResyncRevsPass(Pass):
  """Clean up the revision information.

  This pass was formerly known as pass2."""

  DIGEST_END_IDX = 9 + (sha.digestsize * 2)

  def register_artifacts(self):
    self._register_temp_file(config.TAGS_DB)
    self._register_temp_file(config.CLEAN_REVS_DATAFILE)
    self._register_temp_file(config.CVS_REVS_RESYNC_DB)
    self._register_temp_file_needed(config.TAGS_LIST)
    self._register_temp_file_needed(config.BRANCHES_LIST)
    self._register_temp_file_needed(config.RESYNC_DATAFILE)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_REVS_DB)
    self._register_temp_file_needed(config.ALL_REVS_DATAFILE)

  def _read_resync(self):
    """Read RESYNC_DATAFILE and return its contents.

    Return a map that maps a digest to a sequence of lists which
    specify a lower and upper time bound for matching up the commit:

    { digest -> [[old_time_lower, old_time_upper, new_time], ...] }

    Each triplet is a list because we will dynamically expand the
    lower/upper bound as we find commits that fall into a particular
    msg and time range.  We keep a sequence of these for each digest
    because a number of checkins with the same log message (e.g. an
    empty log message) could need to be remapped.  The lists of
    triplets are sorted by old_time_lower.

    Note that we assume that we can hold the entire resync file in
    memory.  Really large repositories with wacky timestamps could
    bust this assumption.  Should that ever happen, then it is
    possible to split the resync file into pieces and make multiple
    passes, using each piece."""

    DELTA = config.COMMIT_THRESHOLD/2

    resync = { }
    for line in fileinput.FileInput(
            artifact_manager.get_temp_file(config.RESYNC_DATAFILE)):
      [t1, digest, t2] = line.strip().split()
      t1 = int(t1, 16)
      digest = line[9:self.DIGEST_END_IDX]
      t2 = int(t2, 16)
      resync.setdefault(digest, []).append([t1 - DELTA, t1 + DELTA, t2])

    # For each digest, sort the resync items:
    for val in resync.values():
      val.sort()

    return resync

  def _get_non_excluded_symbols(self, symbols, excludes):
    return [ symbol
             for symbol in symbols
             if symbol not in excludes ]

  def _force_tags(self, c_rev):
    """Convert all branches in C_REV that are forced to be tags."""
    for forced_tag in Ctx().forced_tags:
      if forced_tag in c_rev.branches:
        c_rev.branches.remove(forced_tag)
        c_rev.tags.append(forced_tag)

  def _force_branches(self, c_rev):
    """Convert all tags in C_REV that are forced to be branches."""
    for forced_branch in Ctx().forced_branches:
      if forced_branch in c_rev.tags:
        c_rev.tags.remove(forced_branch)
        c_rev.branches.append(forced_branch)

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    cvs_revs_db = CVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_DB), DB_OPEN_WRITE)
    cvs_revs_resync_db = CVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DB),
        DB_OPEN_NEW)
    symbol_db = SymbolDatabase()
    symbol_db.read()

    # Convert the list of regexps to a list of strings
    excludes = symbol_db.find_excluded_symbols(Ctx().excludes)

    error_detected = False

    Log().quiet("Checking for blocked exclusions...")
    if symbol_db.check_blocked_excludes(excludes):
      error_detected = True

    Log().quiet("Checking for forced tags with commits...")
    if symbol_db.check_invalid_forced_tags(excludes):
      error_detected = True

    Log().quiet("Checking for tag/branch mismatches...")
    if symbol_db.check_symbol_mismatches(excludes):
      error_detected = True

    # Bail out now if we found errors
    if error_detected:
      sys.exit(1)

    # Create the tags database
    tags_db = TagsDatabase(DB_OPEN_NEW)
    for tag in symbol_db.tags:
      if tag not in Ctx().forced_branches:
        tags_db.add(tag)
    for tag in Ctx().forced_tags:
      tags_db.add(tag)

    Log().quiet("Re-synchronizing CVS revision timestamps...")

    # We may have recorded some changes in revisions' timestamp.  We need to
    # scan for any other files which may have had the same log message and
    # occurred at "the same time" and change their timestamps, too.

    resync = self._read_resync()

    output = open(artifact_manager.get_temp_file(config.CLEAN_REVS_DATAFILE),
                  'w')

    # process the revisions file, looking for items to clean up
    for line in open(
            artifact_manager.get_temp_file(config.ALL_REVS_DATAFILE)):
      c_rev_id = int(line.strip(), 16)
      c_rev = cvs_revs_db.get_revision(c_rev_id)

      if c_rev.prev_id is not None:
        prev_c_rev = cvs_revs_db.get_revision(c_rev.prev_id)
      else:
        prev_c_rev = None

      if c_rev.next_id is not None:
        next_c_rev = cvs_revs_db.get_revision(c_rev.next_id)
      else:
        next_c_rev = None

      # Skip this entire revision if it's on an excluded branch
      if c_rev.branch_name in excludes:
        continue

      c_rev.branches = self._get_non_excluded_symbols(c_rev.branches, excludes)
      c_rev.tags = self._get_non_excluded_symbols(c_rev.tags, excludes)

      self._force_tags(c_rev)
      self._force_branches(c_rev)

      # see if this is "near" any of the resync records we
      # have recorded for this digest [of the log message].
      for record in resync.get(c_rev.digest, []):
        if record[2] == c_rev.timestamp:
          # This means that either c_rev is the same revision that
          # caused the resync record to exist, or c_rev is a different
          # CVS revision that happens to have the same timestamp.  In
          # either case, we don't have to do anything, so we...
          continue

        if record[0] <= c_rev.timestamp <= record[1]:
          # bingo!  We probably want to remap the time on this c_rev,
          # unless the remapping would be useless because the new time
          # would fall outside the COMMIT_THRESHOLD window for this
          # commit group.
          new_timestamp = record[2]
          # If the new timestamp is earlier than that of our previous revision
          if prev_c_rev and new_timestamp < prev_c_rev.timestamp:
            Log().warn(
                "%s: Attempt to set timestamp of revision %s on file %s"
                " to time %s, which is before previous the time of"
                " revision %s (%s):"
                % (warning_prefix, c_rev.rev, c_rev.cvs_path, new_timestamp,
                   prev_c_rev.rev, prev_c_rev.timestamp))

            # If resyncing our rev to prev_c_rev.timestamp + 1 will place
            # the timestamp of c_rev within COMMIT_THRESHOLD of the
            # attempted resync time, then sync back to prev_c_rev.timestamp
            # + 1...
            if ((prev_c_rev.timestamp + 1) - new_timestamp) \
                   < config.COMMIT_THRESHOLD:
              new_timestamp = prev_c_rev.timestamp + 1
              Log().warn("%s: Time set to %s"
                         % (warning_prefix, new_timestamp))
            else:
              Log().warn("%s: Timestamp left untouched" % warning_prefix)
              continue

          # If the new timestamp is later than that of our next revision
          elif next_c_rev and new_timestamp > next_c_rev.timestamp:
            Log().warn(
                "%s: Attempt to set timestamp of revision %s on file %s"
                " to time %s, which is after time of next"
                " revision %s (%s):"
                % (warning_prefix, c_rev.rev, c_rev.cvs_path, new_timestamp,
                   next_c_rev.rev, next_c_rev.timestamp))

            # If resyncing our rev to next_c_rev.timestamp - 1 will place
            # the timestamp of c_rev within COMMIT_THRESHOLD of the
            # attempted resync time, then sync forward to
            # next_c_rev.timestamp - 1...
            if (new_timestamp - (next_c_rev.timestamp - 1)) \
                   < config.COMMIT_THRESHOLD:
              new_timestamp = next_c_rev.timestamp - 1
              Log().warn("%s: Time set to %s"
                         % (warning_prefix, new_timestamp))
            else:
              Log().warn("%s: Timestamp left untouched" % warning_prefix)
              continue

          # Fix for Issue #71: Avoid resyncing two consecutive revisions
          # to the same timestamp.
          elif (prev_c_rev and new_timestamp == prev_c_rev.timestamp
                or next_c_rev and new_timestamp == next_c_rev.timestamp):
            continue

          # adjust the time range. we want the COMMIT_THRESHOLD from the
          # bounds of the earlier/latest commit in this group.
          record[0] = min(record[0],
                          c_rev.timestamp - config.COMMIT_THRESHOLD/2)
          record[1] = max(record[1],
                          c_rev.timestamp + config.COMMIT_THRESHOLD/2)

          msg = "PASS2 RESYNC: '%s' (%s): old time='%s' delta=%ds" \
                % (c_rev.cvs_path, c_rev.rev, time.ctime(c_rev.timestamp),
                   new_timestamp - c_rev.timestamp)
          Log().verbose(msg)

          c_rev.timestamp = new_timestamp

          # stop looking for hits
          break

      output.write('%08lx %s %x\n'
                   % (c_rev.timestamp, c_rev.digest, c_rev.id,))
      cvs_revs_resync_db.log_revision(c_rev)
    Log().quiet("Done")


class SortRevsPass(Pass):
  """This pass was formerly known as pass3."""

  def register_artifacts(self):
    self._register_temp_file(config.SORTED_REVS_DATAFILE)
    self._register_temp_file_needed(config.CLEAN_REVS_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Sorting CVS revisions...")
    sort_file(artifact_manager.get_temp_file(config.CLEAN_REVS_DATAFILE),
              artifact_manager.get_temp_file(config.SORTED_REVS_DATAFILE))
    Log().quiet("Done")


class CreateDatabasesPass(Pass):
  """This pass was formerly known as pass4."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_LAST_CVS_REVS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_REVS_RESYNC_DB)
    self._register_temp_file_needed(config.SORTED_REVS_DATAFILE)

  def run(self, stats_keeper):
    """If we're not doing a trunk-only conversion, generate the
    LastSymbolicNameDatabase, which contains the last CVSRevision that
    is a source for each tag or branch.  Also record the remaining
    revisions to the StatsKeeper."""

    Log().quiet("Copying CVS revision data from flat file to database...")
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    cvs_revs_db = CVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DB),
        DB_OPEN_READ)
    if not Ctx().trunk_only:
      Log().quiet("Finding last CVS revisions for all symbolic names...")
      last_sym_name_db = LastSymbolicNameDatabase()
    else:
      # This is to avoid testing Ctx().trunk_only every time around the loop
      class DummyLSNDB:
        def noop(*args): pass
        log_revision = noop
        create_database = noop
      last_sym_name_db = DummyLSNDB()

    for line in fileinput.FileInput(
            artifact_manager.get_temp_file(config.SORTED_REVS_DATAFILE)):
      c_rev_id = int(line.strip().split()[-1], 16)
      c_rev = cvs_revs_db.get_revision(c_rev_id)
      last_sym_name_db.log_revision(c_rev)
      stats_keeper.record_c_rev(c_rev)

    stats_keeper.set_stats_reflect_exclude(True)

    last_sym_name_db.create_database()
    stats_keeper.archive()
    Log().quiet("Done")


class AggregateRevsPass(Pass):
  """Generate the SVNCommit <-> CVSRevision mapping databases.
  CVSCommit._commit also calls SymbolingsLogger to register
  CVSRevisions that represent an opening or closing for a path on a
  branch or tag.  See SymbolingsLogger for more details.

  This pass was formerly known as pass5."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS)
    self._register_temp_file(config.SYMBOL_CLOSINGS_TMP)
    self._register_temp_file(config.SVN_REVNUMS_TO_CVS_REVS)
    self._register_temp_file(config.CVS_REVS_TO_SVN_REVNUMS)
    if not Ctx().trunk_only:
      self._register_temp_file_needed(config.SYMBOL_LAST_CVS_REVS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_REVS_RESYNC_DB)
    self._register_temp_file_needed(config.TAGS_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.SORTED_REVS_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Mapping CVS revisions to Subversion commits...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    cvs_revs_db = CVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DB),
        DB_OPEN_READ)
    aggregator = CVSRevisionAggregator()
    for line in fileinput.FileInput(
            artifact_manager.get_temp_file(config.SORTED_REVS_DATAFILE)):
      c_rev_id = int(line.strip().split()[-1], 16)
      c_rev = cvs_revs_db.get_revision(c_rev_id)
      if not (Ctx().trunk_only and c_rev.branch_name is not None):
        aggregator.process_revision(c_rev)
    aggregator.flush()

    stats_keeper.set_svn_rev_count(SVNCommit.revnum - 1)
    stats_keeper.archive()
    Log().quiet("Done")


class SortSymbolsPass(Pass):
  """This pass was formerly known as pass6."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)
    self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS)

  def run(self, stats_keeper):
    Log().quiet("Sorting symbolic name source revisions...")

    if not Ctx().trunk_only:
      sort_file(
          artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS),
          artifact_manager.get_temp_file(
              config.SYMBOL_OPENINGS_CLOSINGS_SORTED))
    Log().quiet("Done")


class IndexSymbolsPass(Pass):
  """This pass was formerly known as pass7."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_OFFSETS_DB)
      self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)

  def run(self, stats_keeper):
    Log().quiet("Determining offsets for all symbolic names...")

    def generate_offsets_for_symbolings():
      """This function iterates through all the lines in
      SYMBOL_OPENINGS_CLOSINGS_SORTED, writing out a file mapping
      SYMBOLIC_NAME to the file offset in SYMBOL_OPENINGS_CLOSINGS_SORTED
      where SYMBOLIC_NAME is first encountered.  This will allow us to
      seek to the various offsets in the file and sequentially read only
      the openings and closings that we need."""

      ###PERF This is a fine example of a db that can be in-memory and
      #just flushed to disk when we're done.  Later, it can just be sucked
      #back into memory.
      offsets_db = Database(
          artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB),
          DB_OPEN_NEW)

      file = open(
          artifact_manager.get_temp_file(
              config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
          'r')
      old_sym = ""
      while 1:
        fpos = file.tell()
        line = file.readline()
        if not line:
          break
        sym, svn_revnum, cvs_rev_key = line.split(" ", 2)
        if sym != old_sym:
          Log().verbose(" ", sym)
          old_sym = sym
          offsets_db[sym] = fpos

    if not Ctx().trunk_only:
      generate_offsets_for_symbolings()
    Log().quiet("Done.")


class OutputPass(Pass):
  """This pass was formerly known as pass8."""

  def register_artifacts(self):
    self._register_temp_file(config.SVN_MIRROR_REVISIONS_DB)
    self._register_temp_file(config.SVN_MIRROR_NODES_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_REVS_RESYNC_DB)
    self._register_temp_file_needed(config.TAGS_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.SVN_REVNUMS_TO_CVS_REVS)
    self._register_temp_file_needed(config.CVS_REVS_TO_SVN_REVNUMS)
    if not Ctx().trunk_only:
      self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)
      self._register_temp_file_needed(config.SYMBOL_OFFSETS_DB)

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    svncounter = 2 # Repository initialization is 1.
    repos = SVNRepositoryMirror()
    persistence_manager = PersistenceManager(DB_OPEN_READ)

    if Ctx().target:
      if not Ctx().dry_run:
        repos.add_delegate(RepositoryDelegate())
      Log().quiet("Starting Subversion Repository.")
    else:
      if not Ctx().dry_run:
        repos.add_delegate(DumpfileDelegate())
      Log().quiet("Starting Subversion Dumpfile.")

    repos.add_delegate(StdoutDelegate(stats_keeper.svn_rev_count()))

    while 1:
      svn_commit = persistence_manager.get_svn_commit(svncounter)
      if not svn_commit:
        break
      repos.commit(svn_commit)
      svncounter += 1

    repos.finish()


