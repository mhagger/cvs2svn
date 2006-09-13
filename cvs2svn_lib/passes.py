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


from __future__ import generators

import sys
import os
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import DB_OPEN_NEW
from cvs2svn_lib.database import DB_OPEN_READ
from cvs2svn_lib.database import DB_OPEN_WRITE
from cvs2svn_lib.cvs_file_database import CVSFileDatabase
from cvs2svn_lib.metadata_database import MetadataDatabase
from cvs2svn_lib.symbol import BranchSymbol
from cvs2svn_lib.symbol import TagSymbol
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.symbol_database import create_symbol_database
from cvs2svn_lib.line_of_development import Branch
from cvs2svn_lib.symbol_statistics import SymbolStatistics
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item_database import NewCVSItemStore
from cvs2svn_lib.cvs_item_database import OldCVSItemStore
from cvs2svn_lib.cvs_item_database import CVSItemDatabase
from cvs2svn_lib.cvs_revision_resynchronizer import CVSRevisionResynchronizer
from cvs2svn_lib.last_symbolic_name_database import LastSymbolicNameDatabase
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.openings_closings import SymbolingsLogger
from cvs2svn_lib.cvs_revision_aggregator import CVSRevisionAggregator
from cvs2svn_lib.svn_repository_mirror import SVNRepositoryMirror
from cvs2svn_lib.svn_commit import SVNInitialProjectCommit
from cvs2svn_lib.persistence_manager import PersistenceManager
from cvs2svn_lib.stdout_delegate import StdoutDelegate
from cvs2svn_lib.collect_data import CollectData
from cvs2svn_lib.process import run_command


def sort_file(infilename, outfilename, options=''):
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
    run_command('%s -T %s %s %s > %s'
                % (Ctx().sort_executable, Ctx().tmpdir, options,
                   infilename, outfilename))
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
    self._register_temp_file(config.SYMBOL_STATISTICS_LIST)
    self._register_temp_file(config.RESYNC_DATAFILE)
    self._register_temp_file(config.METADATA_DB)
    self._register_temp_file(config.CVS_FILES_DB)
    self._register_temp_file(config.CVS_ITEMS_STORE)

  def run(self, stats_keeper):
    Log().quiet("Examining all CVS ',v' files...")
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_NEW)
    cd = CollectData(stats_keeper)
    for project in Ctx().projects:
      cd.process_project(project)
    cd.flush()

    if cd.fatal_errors:
      raise FatalException("Pass 1 complete.\n"
                           + "=" * 75 + "\n"
                           + "Error summary:\n"
                           + "\n".join(cd.fatal_errors) + "\n"
                           + "Exited due to fatal error(s).\n")

    stats_keeper.reset_cvs_rev_info()
    stats_keeper.archive()
    Log().quiet("Done")


class CollateSymbolsPass(Pass):
  """Divide symbols into branches, tags, and excludes."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_DB)
    self._register_temp_file_needed(config.SYMBOL_STATISTICS_LIST)

  def run(self, stats_keeper):
    symbol_stats = SymbolStatistics()

    symbols = Ctx().symbol_strategy.get_symbols(symbol_stats)

    # Check the symbols for consistency and bail out if there were errors:
    if symbols is None or symbol_stats.check_consistency(symbols):
      sys.exit(1)

    create_symbol_database(symbols)

    Log().quiet("Done")


class ResyncRevsPass(Pass):
  """Clean up the revision information.

  This pass was formerly known as pass2."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_REVS_RESYNC_DATAFILE)
    self._register_temp_file(config.CVS_ITEMS_RESYNC_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.RESYNC_DATAFILE)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_STORE)

  def update_symbols(self, cvs_rev):
    """Update CVS_REV.branch_ids and tag_ids based on self.symbol_db."""

    branch_ids = []
    tag_ids = []
    for id in cvs_rev.branch_ids + cvs_rev.tag_ids:
      symbol = self.symbol_db.get_symbol(id)
      if isinstance(symbol, BranchSymbol):
        branch_ids.append(symbol.id)
      elif isinstance(symbol, TagSymbol):
        tag_ids.append(symbol.id)
    cvs_rev.branch_ids = branch_ids
    cvs_rev.tag_ids = tag_ids

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    self.symbol_db = SymbolDatabase()
    Ctx()._symbol_db = self.symbol_db
    cvs_item_store = OldCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_STORE))
    cvs_items_resync_db = CVSItemDatabase(
        artifact_manager.get_temp_file(config.CVS_ITEMS_RESYNC_DB),
        DB_OPEN_NEW)

    Log().quiet("Re-synchronizing CVS revision timestamps...")

    resynchronizer = CVSRevisionResynchronizer(cvs_item_store)

    # We may have recorded some changes in revisions' timestamp.  We need to
    # scan for any other files which may have had the same log message and
    # occurred at "the same time" and change their timestamps, too.

    # Process the revisions file, looking for items to clean up
    for cvs_item in cvs_item_store:
      if isinstance(cvs_item, CVSRevision):
        # Skip this entire revision if it's on an excluded branch
        if isinstance(cvs_item.lod, Branch):
          symbol = self.symbol_db.get_symbol(cvs_item.lod.symbol.id)
          if isinstance(symbol, ExcludedSymbol):
            continue

        self.update_symbols(cvs_item)

        resynchronizer.resynchronize(cvs_item)

      cvs_items_resync_db.add(cvs_item)

    Log().quiet("Done")


class SortRevsPass(Pass):
  """This pass was formerly known as pass3."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_REVS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_REVS_RESYNC_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Sorting CVS revisions...")
    sort_file(artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DATAFILE),
              artifact_manager.get_temp_file(config.CVS_REVS_SORTED_DATAFILE))
    Log().quiet("Done")


class CreateDatabasesPass(Pass):
  """This pass was formerly known as pass4."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_LAST_CVS_REVS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_RESYNC_DB)
    self._register_temp_file_needed(config.CVS_REVS_SORTED_DATAFILE)

  def get_cvs_revs(self):
    """Generator the CVSRevisions in CVS_REVS_SORTED_DATAFILE order."""

    cvs_items_db = CVSItemDatabase(
        artifact_manager.get_temp_file(config.CVS_ITEMS_RESYNC_DB),
        DB_OPEN_READ)
    for line in file(
            artifact_manager.get_temp_file(config.CVS_REVS_SORTED_DATAFILE)):
      cvs_rev_id = int(line.strip().split()[-1], 16)
      yield cvs_items_db[cvs_rev_id]

  def run(self, stats_keeper):
    """If we're not doing a trunk-only conversion, generate the
    LastSymbolicNameDatabase, which contains the last CVSRevision that
    is a source for each tag or branch.  Also record the remaining
    revisions to the StatsKeeper."""

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()

    if Ctx().trunk_only:
      for cvs_rev in self.get_cvs_revs():
        stats_keeper.record_cvs_rev(cvs_rev)
    else:
      Log().quiet("Finding last CVS revisions for all symbolic names...")
      last_sym_name_db = LastSymbolicNameDatabase()

      for cvs_rev in self.get_cvs_revs():
        last_sym_name_db.log_revision(cvs_rev)
        stats_keeper.record_cvs_rev(cvs_rev)

      last_sym_name_db.create_database()

    stats_keeper.set_stats_reflect_exclude(True)

    stats_keeper.archive()

    Log().quiet("Done")


class AggregateRevsPass(Pass):
  """Generate the SVNCommit <-> CVSRevision mapping databases.
  CVSCommit._commit also calls SymbolingsLogger to register
  CVSRevisions that represent an opening or closing for a path on a
  branch or tag.  See SymbolingsLogger for more details.

  This pass was formerly known as pass5."""

  def register_artifacts(self):
    self._register_temp_file(config.SVN_COMMITS_DB)
    self._register_temp_file(config.CVS_REVS_TO_SVN_REVNUMS)
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS)
      self._register_temp_file_needed(config.SYMBOL_LAST_CVS_REVS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_RESYNC_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.CVS_REVS_SORTED_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Mapping CVS revisions to Subversion commits...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)
    Ctx()._cvs_items_db = CVSItemDatabase(
        artifact_manager.get_temp_file(config.CVS_ITEMS_RESYNC_DB),
        DB_OPEN_READ)
    if not Ctx().trunk_only:
      Ctx()._symbolings_logger = SymbolingsLogger()
    aggregator = CVSRevisionAggregator()
    for line in file(
            artifact_manager.get_temp_file(config.CVS_REVS_SORTED_DATAFILE)):
      cvs_rev_id = int(line.strip().split()[-1], 16)
      cvs_rev = Ctx()._cvs_items_db[cvs_rev_id]
      if not (Ctx().trunk_only and isinstance(cvs_rev.lod, Branch)):
        aggregator.process_revision(cvs_rev)
    aggregator.flush()
    if not Ctx().trunk_only:
      Ctx()._symbolings_logger.close()

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
              config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
          options='-k1,1 -k2,2n -k3')
    Log().quiet("Done")


class IndexSymbolsPass(Pass):
  """This pass was formerly known as pass7."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_OFFSETS_DB)
      self._register_temp_file_needed(config.SYMBOL_DB)
      self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)

  def generate_offsets_for_symbolings(self):
    """This function iterates through all the lines in
    SYMBOL_OPENINGS_CLOSINGS_SORTED, writing out a file mapping
    SYMBOLIC_NAME to the file offset in SYMBOL_OPENINGS_CLOSINGS_SORTED
    where SYMBOLIC_NAME is first encountered.  This will allow us to
    seek to the various offsets in the file and sequentially read only
    the openings and closings that we need."""

    offsets = {}

    f = open(
        artifact_manager.get_temp_file(
            config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
        'r')
    old_id = None
    while True:
      fpos = f.tell()
      line = f.readline()
      if not line:
        break
      id, svn_revnum, ignored = line.split(" ", 2)
      id = int(id, 16)
      if id != old_id:
        Log().verbose(' ', Ctx()._symbol_db.get_symbol(id).name)
        old_id = id
        offsets[id] = fpos

    offsets_db = file(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB), 'wb')
    cPickle.dump(offsets, offsets_db, -1)
    offsets_db.close()

  def run(self, stats_keeper):
    Log().quiet("Determining offsets for all symbolic names...")

    if not Ctx().trunk_only:
      Ctx()._symbol_db = SymbolDatabase()
      self.generate_offsets_for_symbolings()
    Log().quiet("Done.")


class OutputPass(Pass):
  """This pass was formerly known as pass8."""

  def register_artifacts(self):
    self._register_temp_file(config.SVN_MIRROR_REVISIONS_DB)
    self._register_temp_file(config.SVN_MIRROR_NODES_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_RESYNC_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.SVN_COMMITS_DB)
    self._register_temp_file_needed(config.CVS_REVS_TO_SVN_REVNUMS)
    if not Ctx().trunk_only:
      self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)
      self._register_temp_file_needed(config.SYMBOL_OFFSETS_DB)

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)
    Ctx()._cvs_items_db = CVSItemDatabase(
        artifact_manager.get_temp_file(config.CVS_ITEMS_RESYNC_DB),
        DB_OPEN_READ)
    if not Ctx().trunk_only:
      Ctx()._symbol_db = SymbolDatabase()
    repos = SVNRepositoryMirror()
    persistence_manager = PersistenceManager(DB_OPEN_READ)

    Ctx().output_option.setup(repos)

    repos.add_delegate(StdoutDelegate(stats_keeper.svn_rev_count()))

    svn_revnum = 2 # Repository initialization is 1.

    # Peek at the first revision to find the date to use to initialize
    # the repository:
    svn_commit = persistence_manager.get_svn_commit(svn_revnum)

    # Initialize the repository by creating the directories for trunk,
    # tags, and branches.
    SVNInitialProjectCommit(svn_commit.date, 1).commit(repos)

    while True:
      svn_commit = persistence_manager.get_svn_commit(svn_revnum)
      if not svn_commit:
        break
      svn_commit.commit(repos)
      svn_revnum += 1

    repos.finish()

    Ctx().output_option.cleanup()


