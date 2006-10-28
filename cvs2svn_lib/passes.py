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
import shutil
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_file_database import CVSFileDatabase
from cvs2svn_lib.metadata_database import MetadataDatabase
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.symbol_database import create_symbol_database
from cvs2svn_lib.symbol_statistics import SymbolStatistics
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.cvs_item_database import NewCVSItemStore
from cvs2svn_lib.cvs_item_database import OldCVSItemStore
from cvs2svn_lib.cvs_item_database import IndexedCVSItemStore
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.changeset import RevisionChangeset
from cvs2svn_lib.changeset import SymbolChangeset
from cvs2svn_lib.changeset_graph import ChangesetGraph
from cvs2svn_lib.changeset_graph_link import ChangesetGraphLink
from cvs2svn_lib.changeset_database import ChangesetDatabase
from cvs2svn_lib.changeset_database import CVSItemToChangesetTable
from cvs2svn_lib.last_symbolic_name_database import LastSymbolicNameDatabase
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.openings_closings import SymbolingsLogger
from cvs2svn_lib.cvs_revision_creator import CVSRevisionCreator
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


class Pass(object):
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
    self._register_temp_file(config.METADATA_DB)
    self._register_temp_file(config.CVS_FILES_DB)
    self._register_temp_file(config.CVS_ITEMS_STORE)
    Ctx().revision_reader.get_revision_recorder().register_artifacts(self)

  def run(self, stats_keeper):
    Log().quiet("Examining all CVS ',v' files...")
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_NEW)
    cd = CollectData(
        Ctx().revision_reader.get_revision_recorder(), stats_keeper)
    for project in Ctx().projects:
      cd.process_project(project)
    cd.flush()

    if cd.fatal_errors:
      raise FatalException("Pass 1 complete.\n"
                           + "=" * 75 + "\n"
                           + "Error summary:\n"
                           + "\n".join(cd.fatal_errors) + "\n"
                           + "Exited due to fatal error(s).\n")

    Ctx()._cvs_file_db.close()
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


class CheckDependenciesPass(Pass):
  """Check that the dependencies are self-consistent."""

  def __init__(self, cvs_items_store_file):
    Pass.__init__(self)
    self.cvs_items_store_file = cvs_items_store_file

  def register_artifacts(self):
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(self.cvs_items_store_file)

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    self.symbol_db = SymbolDatabase()
    Ctx()._symbol_db = self.symbol_db
    cvs_item_store = OldCVSItemStore(
        artifact_manager.get_temp_file(self.cvs_items_store_file))

    Log().quiet("Checking dependency consistency...")

    fatal_errors = []
    for cvs_item in cvs_item_store:
      # Check that the pred_ids and succ_ids are mutually consistent:
      for pred_id in cvs_item.get_pred_ids():
        pred = cvs_item_store[pred_id]
        if not cvs_item.id in pred.get_succ_ids():
          fatal_errors.append(
              '%s lists pred=%s, but not vice versa.' % (cvs_item, pred,))

      for succ_id in cvs_item.get_succ_ids():
        succ = cvs_item_store[succ_id]
        if not cvs_item.id in succ.get_pred_ids():
          fatal_errors.append(
              '%s lists succ=%s, but not vice versa.' % (cvs_item, succ,))

    if fatal_errors:
      raise FatalException("Dependencies inconsistent:\n"
                           + "\n".join(fatal_errors) + "\n"
                           + "Exited due to fatal error(s).\n")

    Log().quiet("Done")


class FilterSymbolsPass(Pass):
  """Delete any branches/tags that are to be excluded.

  Also delete revisions on excluded branches, and delete other
  references to the excluded symbols."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file(config.CVS_REVS_SUMMARY_DATAFILE)
    self._register_temp_file(config.CVS_SYMBOLS_SUMMARY_DATAFILE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_STORE)

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    self.cvs_item_store = OldCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_STORE))
    cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_NEW)
    revs_summary_file = open(
        artifact_manager.get_temp_file(config.CVS_REVS_SUMMARY_DATAFILE),
        'w')
    symbols_summary_file = open(
        artifact_manager.get_temp_file(config.CVS_SYMBOLS_SUMMARY_DATAFILE),
        'w')

    Log().quiet("Filtering out excluded symbols and summarizing items...")

    # Process the cvs items store one file at a time:
    for cvs_file_items in self.cvs_item_store.iter_cvs_file_items():
      cvs_file_items.filter_excluded_symbols()
      cvs_file_items.mutate_symbols()

      # Store whatever is left to the new file:
      for cvs_item in cvs_file_items.values():
        cvs_items_db.add(cvs_item)

        if isinstance(cvs_item, CVSRevision):
          revs_summary_file.write(
              '%x %08x %x\n'
              % (cvs_item.metadata_id, cvs_item.timestamp, cvs_item.id,))
        elif isinstance(cvs_item, CVSSymbol):
          symbols_summary_file.write(
              '%x %x\n' % (cvs_item.symbol.id, cvs_item.id,))

    cvs_items_db.close()
    revs_summary_file.close()
    symbols_summary_file.close()

    Log().quiet("Done")


class SortRevisionSummaryPass(Pass):
  """Sort the revision summary file."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_REVS_SUMMARY_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_REVS_SUMMARY_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Sorting CVS revision summaries...")
    sort_file(
        artifact_manager.get_temp_file(config.CVS_REVS_SUMMARY_DATAFILE),
        artifact_manager.get_temp_file(
            config.CVS_REVS_SUMMARY_SORTED_DATAFILE))
    Log().quiet("Done")


class SortSymbolSummaryPass(Pass):
  """Sort the symbol summary file."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_SYMBOLS_SUMMARY_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_SYMBOLS_SUMMARY_DATAFILE)

  def run(self, stats_keeper):
    Log().quiet("Sorting CVS symbol summaries...")
    sort_file(
        artifact_manager.get_temp_file(config.CVS_SYMBOLS_SUMMARY_DATAFILE),
        artifact_manager.get_temp_file(
            config.CVS_SYMBOLS_SUMMARY_SORTED_DATAFILE))
    Log().quiet("Done")


class InitializeChangesetsPass(Pass):
  """Create preliminary CommitSets."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET)
    self._register_temp_file(config.CHANGESETS_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file_needed(config.CVS_REVS_SUMMARY_SORTED_DATAFILE)
    self._register_temp_file_needed(
        config.CVS_SYMBOLS_SUMMARY_SORTED_DATAFILE)

  def get_revision_changesets(self):
    """Generate revision changesets, one at a time."""

    # Create changesets for CVSRevisions:
    old_metadata_id = None
    old_timestamp = None
    changeset = []
    for l in open(
        artifact_manager.get_temp_file(
            config.CVS_REVS_SUMMARY_SORTED_DATAFILE), 'r'):
      [metadata_id, timestamp, cvs_item_id] = \
          [int(s, 16) for s in l.strip().split()]
      if metadata_id != old_metadata_id \
         or timestamp > old_timestamp + config.COMMIT_THRESHOLD:
        # Start a new changeset.  First finish up the old changeset,
        # if any:
        if changeset:
          yield RevisionChangeset(
              self.changeset_key_generator.gen_id(), changeset)
          changeset = []
        old_metadata_id = metadata_id
      changeset.append(cvs_item_id)
      old_timestamp = timestamp

    # Finish up the last changeset, if any:
    if changeset:
      yield RevisionChangeset(
          self.changeset_key_generator.gen_id(), changeset)

  def get_symbol_changesets(self):
    """Generate symbol changesets, one at a time."""

    old_symbol_id = None
    changeset = []
    for l in open(
        artifact_manager.get_temp_file(
            config.CVS_SYMBOLS_SUMMARY_SORTED_DATAFILE), 'r'):
      [symbol_id, cvs_item_id] = [int(s, 16) for s in l.strip().split()]
      if symbol_id != old_symbol_id:
        # Start a new changeset.  First finish up the old changeset,
        # if any:
        if changeset:
          yield SymbolChangeset(
              self.changeset_key_generator.gen_id(), changeset)
          changeset = []
        old_symbol_id = symbol_id
      changeset.append(cvs_item_id)

    # Finish up the last changeset, if any:
    if changeset:
      yield SymbolChangeset(self.changeset_key_generator.gen_id(), changeset)

  def compare_items(a, b):
      return (
          cmp(a.timestamp, b.timestamp)
          or cmp(a.cvs_file.cvs_path, b.cvs_file.cvs_path)
          or cmp([int(x) for x in a.rev.split('.')],
                 [int(x) for x in b.rev.split('.')])
          or cmp(a.id, b.id))

  compare_items = staticmethod(compare_items)

  def break_internal_dependencies(self, changeset):
    """Split up CHANGESET if necessary to break internal dependencies.

    Return a list containing the resulting changesets.  Iff CHANGESET
    did not have to be split, then the return value will contain a
    single value, namely the original CHANGESET."""

    cvs_items = changeset.get_cvs_items()
    # We only look for succ dependencies, since by doing so we
    # automatically cover pred dependencies as well.  First create a
    # list of tuples (pred, succ) of id pairs for CVSItems that depend
    # on each other.
    dependencies = []
    for cvs_item in cvs_items:
      for next_id in cvs_item.get_succ_ids():
        if next_id in changeset.cvs_item_ids:
          dependencies.append((cvs_item.id, next_id,))
    if dependencies:
      # Sort the cvs_items in a defined order (chronological to the
      # extent that the timestamps are correct and unique).
      cvs_items = list(cvs_items)
      cvs_items.sort(self.compare_items)
      indexes = {}
      for i in range(len(cvs_items)):
        indexes[cvs_items[i].id] = i
      # How many internal dependencies would be broken by breaking the
      # Changeset after a particular index?
      breaks = [0] * len(cvs_items)
      for (pred, succ,) in dependencies:
        pred_index = indexes[pred]
        succ_index = indexes[succ]
        breaks[min(pred_index, succ_index)] += 1
        breaks[max(pred_index, succ_index)] -= 1
      best_i = None
      best_count = -1
      best_time = 0
      for i in range(1, len(breaks)):
        breaks[i] += breaks[i - 1]
      for i in range(0, len(breaks) - 1):
        if breaks[i] > best_count:
          best_i = i
          best_count = breaks[i]
          best_time = cvs_items[i + 1].timestamp - cvs_items[i].timestamp
        elif breaks[i] == best_count \
             and cvs_items[i + 1].timestamp - cvs_items[i].timestamp \
                 < best_time:
          best_i = i
          best_count = breaks[i]
          best_time = cvs_items[i + 1].timestamp - cvs_items[i].timestamp
      # Reuse the old changeset.id for the first of the split changesets.
      return (
          self.break_internal_dependencies(
              RevisionChangeset(
                  changeset.id,
                  [cvs_item.id for cvs_item in cvs_items[:best_i + 1]]))
          + self.break_internal_dependencies(
              RevisionChangeset(
                  self.changeset_key_generator.gen_id(),
                  [cvs_item.id for cvs_item in cvs_items[best_i + 1:]])))
    else:
      return [changeset]

  def store_changeset(self, changeset):
    for cvs_item_id in changeset.cvs_item_ids:
      self.cvs_item_to_changeset_id[cvs_item_id] = changeset.id
    self.changesets_db.store(changeset)

  def run(self, stats_keeper):
    Log().quiet("Creating preliminary commit sets...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    self.symbol_db = SymbolDatabase()
    Ctx()._symbol_db = self.symbol_db
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)

    self.cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(config.CVS_ITEM_TO_CHANGESET),
        DB_OPEN_NEW)
    self.changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_DB), DB_OPEN_NEW)
    self.changeset_key_generator = KeyGenerator(1)

    for changeset in self.get_revision_changesets():
      for split_changeset in self.break_internal_dependencies(changeset):
        Log().verbose(repr(changeset))
        self.store_changeset(split_changeset)

    for changeset in self.get_symbol_changesets():
      Log().verbose(repr(changeset))
      self.store_changeset(changeset)

    self.cvs_item_to_changeset_id.close()
    self.changesets_db.close()

    Log().quiet("Done")


class BreakCVSRevisionChangesetLoopsPass(Pass):
  """Break up any dependency loops involving only RevisionChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_REVBROKEN_DB)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_REVBROKEN)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET)
    self._register_temp_file_needed(config.CHANGESETS_DB)

  def break_cycle(self, cycle):
    """Break up one or more changesets in CYCLE to help break the cycle.

    CYCLE is a list of Changesets where

        cycle[i] depends on cycle[i - 1]

    Break up one or more changesets in CYCLE to make progress towards
    breaking the cycle.  Update self.changeset_graph accordingly.

    It is not guaranteed that the cycle will be broken by one call to
    this routine, but at least some progress must be made."""

    Log().verbose('Breaking cycle: %s' % ' -> '.join([
        '%x' % node.id for node in (cycle + [cycle[0]])]))

    best_i = None
    best_link = None
    for i in range(len(cycle)):
      # It's OK if this index wraps to -1:
      link = ChangesetGraphLink(
          cycle[i - 1], cycle[i], cycle[i + 1 - len(cycle)])

      if best_i is None or link < best_link:
        best_i = i
        best_link = link

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    del self.changeset_graph[best_link.changeset.id]
    del self.changesets_db[best_link.changeset.id]

    for changeset in new_changesets:
      self.changeset_graph.add_changeset(changeset)
      self.changesets_db.store(changeset)
      for item_id in changeset.cvs_item_ids:
        self.cvs_item_to_changeset_id[item_id] = changeset.id

  def run(self, stats_keeper):
    Log().quiet("Breaking CVSRevision dependency loops...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)

    shutil.copyfile(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET),
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN))
    self.cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN),
        DB_OPEN_WRITE)
    Ctx()._cvs_item_to_changeset_id = self.cvs_item_to_changeset_id

    old_changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_DB), DB_OPEN_READ)
    Ctx()._changesets_db = old_changesets_db
    self.changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(
            config.CHANGESETS_REVBROKEN_DB), DB_OPEN_NEW)

    changeset_ids = old_changesets_db.keys()
    changeset_ids.sort()

    self.changeset_graph = ChangesetGraph()

    for changeset_id in changeset_ids:
      changeset = old_changesets_db[changeset_id]
      self.changesets_db.store(changeset)
      if isinstance(changeset, RevisionChangeset):
        self.changeset_graph.add_changeset(changeset)

    self.changeset_key_generator = KeyGenerator(changeset_ids[-1] + 1)
    del changeset_ids

    old_changesets_db.close()
    del old_changesets_db

    Ctx()._changesets_db = self.changesets_db

    while True:
      cycle = self.changeset_graph.find_cycle()
      if cycle is None:
        break
      else:
        self.break_cycle(cycle)

    self.cvs_item_to_changeset_id.close()
    self.changesets_db.close()

    Log().quiet("Done")


class TopologicalSortPass(Pass):
  """Sort changesets into commit order."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_REVBROKEN_DB)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET_REVBROKEN)

  def run(self, stats_keeper):
    Log().quiet("Generating CVSRevisions in commit order...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)

    changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(
            config.CHANGESETS_REVBROKEN_DB), DB_OPEN_READ)
    Ctx()._changesets_db = changesets_db

    Ctx()._cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN),
        DB_OPEN_READ)

    changeset_ids = changesets_db.keys()

    changeset_graph = ChangesetGraph()

    for changeset_id in changeset_ids:
      changeset = changesets_db[changeset_id]
      if isinstance(changeset, RevisionChangeset):
        changeset_graph.add_changeset(changeset)

    del changeset_ids

    sorted_changesets = open(
        artifact_manager.get_temp_file(config.CHANGESETS_SORTED_DATAFILE), 'w')

    # Ensure a monotonically-increasing timestamp series by keeping
    # track of the previous timestamp and ensuring that the following
    # one is larger.
    timestamp = 0

    for (changeset_id, time_range) in changeset_graph.remove_nopred_nodes():
      timestamp = max(time_range.t_max, timestamp + 1)
      sorted_changesets.write('%x %08x\n' % (changeset_id, timestamp,))

    sorted_changesets.close()

    Log().quiet("Done")


class CreateDatabasesPass(Pass):
  """This pass was formerly known as pass4."""

  def register_artifacts(self):
    if not Ctx().trunk_only:
      self._register_temp_file(config.SYMBOL_LAST_CHANGESETS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_REVBROKEN_DB)
    self._register_temp_file_needed(config.CHANGESETS_SORTED_DATAFILE)

  def get_changesets(self):
    """Generate changesets in commit order."""

    changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(
            config.CHANGESETS_REVBROKEN_DB), DB_OPEN_READ)

    for line in file(
            artifact_manager.get_temp_file(
                config.CHANGESETS_SORTED_DATAFILE)):
      [changeset_id, timestamp] = [int(s, 16) for s in line.strip().split()]
      yield changesets_db[changeset_id]

  def run(self, stats_keeper):
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)

    if Ctx().trunk_only:
      Log().quiet("Recording updated statistics...")
      for changeset in self.get_changesets():
        for cvs_item in changeset.get_cvs_items():
          stats_keeper.record_cvs_item(cvs_item)
    else:
      Log().quiet("Finding last CVS revisions for all symbolic names...")
      last_sym_name_db = LastSymbolicNameDatabase()

      for changeset in self.get_changesets():
        for cvs_item in changeset.get_cvs_items():
          stats_keeper.record_cvs_item(cvs_item)
        last_sym_name_db.log_changeset(changeset)

      last_sym_name_db.create_database()

    Ctx()._cvs_items_db.close()

    stats_keeper.set_stats_reflect_exclude(True)

    stats_keeper.archive()

    Log().quiet("Done")


class CreateRevsPass(Pass):
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
      self._register_temp_file_needed(config.SYMBOL_LAST_CHANGESETS_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.CHANGESETS_REVBROKEN_DB)
    self._register_temp_file_needed(config.CHANGESETS_SORTED_DATAFILE)

  def get_changesets(self):
    """Generate (changeset,timestamp,) tuples in commit order."""

    changesets_db = ChangesetDatabase(
        artifact_manager.get_temp_file(
            config.CHANGESETS_REVBROKEN_DB), DB_OPEN_READ)

    for line in file(
            artifact_manager.get_temp_file(
                config.CHANGESETS_SORTED_DATAFILE)):
      [changeset_id, timestamp] = [int(s, 16) for s in line.strip().split()]
      yield (changesets_db[changeset_id], timestamp)

  def run(self, stats_keeper):
    Log().quiet("Mapping CVS revisions to Subversion commits...")

    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)
    Ctx()._persistence_manager = PersistenceManager(DB_OPEN_NEW)

    if not Ctx().trunk_only:
      Ctx()._symbolings_logger = SymbolingsLogger()

    creator = CVSRevisionCreator()
    for (changeset, timestamp) in self.get_changesets():
      creator.process_changeset(changeset, timestamp)

    if not Ctx().trunk_only:
      Ctx()._symbolings_logger.close()
    Ctx()._cvs_items_db.close()
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
    self._register_temp_file(config.SVN_MIRROR_REVISIONS_TABLE)
    self._register_temp_file(config.SVN_MIRROR_NODES_INDEX_TABLE)
    self._register_temp_file(config.SVN_MIRROR_NODES_STORE)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
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
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
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

    Ctx()._cvs_items_db.close()


