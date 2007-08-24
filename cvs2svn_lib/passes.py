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

"""This module defines the passes that make up a conversion."""


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
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import Timestamper
from cvs2svn_lib.log import Log
from cvs2svn_lib.pass_manager import Pass
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_file_database import CVSFileDatabase
from cvs2svn_lib.metadata_database import MetadataDatabase
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.symbol_database import create_symbol_database
from cvs2svn_lib.symbol_statistics import SymbolStatistics
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.cvs_item_database import OldCVSItemStore
from cvs2svn_lib.cvs_item_database import IndexedCVSItemStore
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.changeset import RevisionChangeset
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import SymbolChangeset
from cvs2svn_lib.changeset import BranchChangeset
from cvs2svn_lib.changeset import create_symbol_changeset
from cvs2svn_lib.changeset_graph import ChangesetGraph
from cvs2svn_lib.changeset_graph_link import ChangesetGraphLink
from cvs2svn_lib.changeset_database import ChangesetDatabase
from cvs2svn_lib.changeset_database import CVSItemToChangesetTable
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.svn_commit import SVNRevisionCommit
from cvs2svn_lib.openings_closings import SymbolingsLogger
from cvs2svn_lib.svn_commit_creator import SVNCommitCreator
from cvs2svn_lib.persistence_manager import PersistenceManager
from cvs2svn_lib.collect_data import CollectData
from cvs2svn_lib.process import run_command
from cvs2svn_lib.check_dependencies_pass \
    import CheckItemStoreDependenciesPass
from cvs2svn_lib.check_dependencies_pass \
    import CheckIndexedItemStoreDependenciesPass


def sort_file(infilename, outfilename, options=''):
  """Sort file INFILENAME, storing the results to OUTFILENAME."""

  # GNU sort will sort our dates differently (incorrectly!) if our
  # LC_ALL is anything but 'C', so if LC_ALL is set, temporarily set
  # it to 'C'
  lc_all_tmp = os.environ.get('LC_ALL', None)
  os.environ['LC_ALL'] = 'C'
  command = '%s -T %s %s %s > %s' % (
      Ctx().sort_executable, Ctx().tmpdir, options, infilename, outfilename
      )
  try:
    # The -T option to sort has a nice side effect.  The Win32 sort is
    # case insensitive and cannot be used, and since it does not
    # understand the -T option and dies if we try to use it, there is
    # no risk that we use that sort by accident.
    run_command(command)
  finally:
    if lc_all_tmp is None:
      del os.environ['LC_ALL']
    else:
      os.environ['LC_ALL'] = lc_all_tmp

  # On some versions of Windows, os.system() does not return an error
  # if the command fails.  So add a little consistency test here that
  # the output file was created and has the right size:
  if not os.path.exists(outfilename) \
     or os.path.getsize(outfilename) != os.path.getsize(infilename):
    raise FatalError('Command failed: "%s"' % (command,))


def read_projects(filename):
  retval = {}
  for project in cPickle.load(open(filename, 'rb')):
    retval[project.id] = project
  return retval


def write_projects(filename):
  cPickle.dump(Ctx()._projects.values(), open(filename, 'wb'), -1)


class CollectRevsPass(Pass):
  """This pass was formerly known as pass1."""

  def register_artifacts(self):
    self._register_temp_file(config.PROJECTS)
    self._register_temp_file(config.SYMBOL_STATISTICS)
    self._register_temp_file(config.METADATA_DB)
    self._register_temp_file(config.CVS_FILES_DB)
    self._register_temp_file(config.CVS_ITEMS_STORE)
    Ctx().revision_recorder.register_artifacts(self)

  def run(self, run_options, stats_keeper):
    Log().quiet("Examining all CVS ',v' files...")
    Ctx()._projects = {}
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_NEW)
    cd = CollectData(Ctx().revision_recorder, stats_keeper)
    for project in run_options.projects:
      cd.process_project(project)
    run_options.projects = None

    fatal_errors = cd.close()

    if fatal_errors:
      raise FatalException("Pass 1 complete.\n"
                           + "=" * 75 + "\n"
                           + "Error summary:\n"
                           + "\n".join(fatal_errors) + "\n"
                           + "Exited due to fatal error(s).\n")

    Ctx()._cvs_file_db.close()
    write_projects(artifact_manager.get_temp_file(config.PROJECTS))
    Log().quiet("Done")


class CollateSymbolsPass(Pass):
  """Divide symbols into branches, tags, and excludes."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_DB)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_STATISTICS)

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    symbol_stats = SymbolStatistics(
        artifact_manager.get_temp_file(config.SYMBOL_STATISTICS)
        )

    symbols = Ctx().symbol_strategy.get_symbols(symbol_stats)

    # Check the symbols for consistency and bail out if there were errors:
    if symbols is None or symbol_stats.check_consistency(symbols):
      sys.exit(1)

    for symbol in symbols:
      if isinstance(symbol, ExcludedSymbol):
        symbol_stats.exclude_symbol(symbol)

    preferred_parents = symbol_stats.get_preferred_parents()

    for symbol in symbols:
      if symbol in preferred_parents:
        preferred_parent = preferred_parents[symbol]
        del preferred_parents[symbol]
        if preferred_parent is None:
          symbol.preferred_parent_id = None
          Log().debug('%s has no preferred parent' % (symbol,))
        else:
          symbol.preferred_parent_id = preferred_parent.id
          Log().debug(
              'The preferred parent of %s is %s' % (symbol, preferred_parent,)
              )

    if preferred_parents:
      raise InternalError('Some symbols unaccounted for')

    create_symbol_database(symbols)

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
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_STORE)
    Ctx().revision_excluder.register_artifacts(self)

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    cvs_item_store = OldCVSItemStore(
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

    revision_excluder = Ctx().revision_excluder

    Log().quiet("Filtering out excluded symbols and summarizing items...")

    stats_keeper.reset_cvs_rev_info()
    revision_excluder.start()
    # Process the cvs items store one file at a time:
    for cvs_file_items in cvs_item_store.iter_cvs_file_items():
      cvs_file_items.filter_excluded_symbols(revision_excluder)
      cvs_file_items.mutate_symbols()
      cvs_file_items.adjust_parents()
      cvs_file_items.refine_symbols()
      cvs_file_items.record_opened_symbols()
      cvs_file_items.record_closed_symbols()

      if Log().is_on(Log.DEBUG):
        cvs_file_items.check_link_consistency()

      # Store whatever is left to the new file and update statistics:
      for cvs_item in cvs_file_items.values():
        stats_keeper.record_cvs_item(cvs_item)
        cvs_items_db.add(cvs_item)

        if isinstance(cvs_item, CVSRevision):
          revs_summary_file.write(
              '%x %08x %x\n'
              % (cvs_item.metadata_id, cvs_item.timestamp, cvs_item.id,))
        elif isinstance(cvs_item, CVSSymbol):
          symbols_summary_file.write(
              '%x %x\n' % (cvs_item.symbol.id, cvs_item.id,))

    stats_keeper.set_stats_reflect_exclude(True)

    revision_excluder.finish()
    symbols_summary_file.close()
    revs_summary_file.close()
    cvs_items_db.close()
    cvs_item_store.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class SortRevisionSummaryPass(Pass):
  """Sort the revision summary file."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_REVS_SUMMARY_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_REVS_SUMMARY_DATAFILE)

  def run(self, run_options, stats_keeper):
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

  def run(self, run_options, stats_keeper):
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
    self._register_temp_file(config.CHANGESETS_STORE)
    self._register_temp_file(config.CHANGESETS_INDEX)
    self._register_temp_file(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.PROJECTS)
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
          yield create_symbol_changeset(
              self.changeset_key_generator.gen_id(),
              Ctx()._symbol_db.get_symbol(old_symbol_id), changeset)
          changeset = []
        old_symbol_id = symbol_id
      changeset.append(cvs_item_id)

    # Finish up the last changeset, if any:
    if changeset:
      yield create_symbol_changeset(
          self.changeset_key_generator.gen_id(),
          Ctx()._symbol_db.get_symbol(symbol_id), changeset)

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

    Return a list containing the resulting changeset(s).  Iff
    CHANGESET did not have to be split, then the return value will
    contain a single value, namely the original CHANGESET.  Split
    CHANGESET at most once, even though the resulting changesets might
    themselves have internal dependencies."""

    cvs_items = list(changeset.get_cvs_items())
    # We only look for succ dependencies, since by doing so we
    # automatically cover pred dependencies as well.  First create a
    # list of tuples (pred, succ) of id pairs for CVSItems that depend
    # on each other.
    dependencies = []
    changeset_cvs_item_ids = set(changeset.cvs_item_ids)
    for cvs_item in cvs_items:
      for next_id in cvs_item.get_succ_ids():
        if next_id in changeset_cvs_item_ids:
          # Sanity check: a CVSItem should never depend on itself:
          if next_id == cvs_item.id:
            raise InternalError('Item depends on itself: %s' % (cvs_item,))

          dependencies.append((cvs_item.id, next_id,))

    if dependencies:
      # Sort the cvs_items in a defined order (chronological to the
      # extent that the timestamps are correct and unique).
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
      return [
          RevisionChangeset(
              changeset.id,
              [cvs_item.id for cvs_item in cvs_items[:best_i + 1]]),
          RevisionChangeset(
              self.changeset_key_generator.gen_id(),
              [cvs_item.id for cvs_item in cvs_items[best_i + 1:]]),
          ]
    else:
      return [changeset]

  def break_all_internal_dependencies(self, changeset):
    """Keep breaking CHANGESET up until all internal dependencies are broken.

    Generate the changeset fragments.  This method is written
    non-recursively to avoid any possible problems with recursion
    depth."""

    changesets_to_split = [changeset]
    while changesets_to_split:
      changesets = self.break_internal_dependencies(changesets_to_split.pop())
      if len(changesets) == 1:
        yield changesets[0]
      else:
        # The changeset had to be split; see if either of the
        # fragments have to be split:
        changesets.reverse()
        changesets_to_split.extend(changesets)

  def get_changesets(self):
    """Return all changesets, with internal dependencies already broken."""

    for changeset in self.get_revision_changesets():
      for split_changeset in self.break_all_internal_dependencies(changeset):
        yield split_changeset

    for changeset in self.get_symbol_changesets():
      yield changeset

  def run(self, run_options, stats_keeper):
    Log().quiet("Creating preliminary commit sets...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
        DB_OPEN_READ)

    changeset_graph = ChangesetGraph(
        ChangesetDatabase(
            artifact_manager.get_temp_file(config.CHANGESETS_STORE),
            artifact_manager.get_temp_file(config.CHANGESETS_INDEX),
            DB_OPEN_NEW,
            ),
        CVSItemToChangesetTable(
            artifact_manager.get_temp_file(config.CVS_ITEM_TO_CHANGESET),
            DB_OPEN_NEW,
            ),
        )

    self.sorted_cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_NEW)

    self.changeset_key_generator = KeyGenerator()

    for changeset in self.get_changesets():
      if Log().is_on(Log.DEBUG):
        Log().debug(repr(changeset))
      changeset_graph.store_changeset(changeset)
      for cvs_item in list(changeset.get_cvs_items()):
        self.sorted_cvs_items_db.add(cvs_item)

    self.sorted_cvs_items_db.close()
    changeset_graph.close()
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class ProcessedChangesetLogger:
  def __init__(self):
    self.processed_changeset_ids = []

  def log(self, changeset_id):
    if Log().is_on(Log.DEBUG):
      self.processed_changeset_ids.append(changeset_id)

  def flush(self):
    if self.processed_changeset_ids:
      Log().debug(
          'Consumed changeset ids %s'
          % (', '.join(['%x' % id for id in self.processed_changeset_ids]),))

      del self.processed_changeset_ids[:]


class BreakRevisionChangesetCyclesPass(Pass):
  """Break up any dependency cycles involving only RevisionChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_REVBROKEN_STORE)
    self._register_temp_file(config.CHANGESETS_REVBROKEN_INDEX)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_REVBROKEN)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_STORE)
    self._register_temp_file_needed(config.CHANGESETS_INDEX)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET)

  def get_source_changesets(self):
    old_changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_INDEX),
        DB_OPEN_READ)

    changeset_ids = old_changeset_db.keys()

    for changeset_id in changeset_ids:
      yield old_changeset_db[changeset_id]

    old_changeset_db.close()
    del old_changeset_db

  def break_cycle(self, cycle):
    """Break up one or more changesets in CYCLE to help break the cycle.

    CYCLE is a list of Changesets where

        cycle[i] depends on cycle[i - 1]

    Break up one or more changesets in CYCLE to make progress towards
    breaking the cycle.  Update self.changeset_graph accordingly.

    It is not guaranteed that the cycle will be broken by one call to
    this routine, but at least some progress must be made."""

    self.processed_changeset_logger.flush()
    best_i = None
    best_link = None
    for i in range(len(cycle)):
      # It's OK if this index wraps to -1:
      link = ChangesetGraphLink(
          cycle[i - 1], cycle[i], cycle[i + 1 - len(cycle)])

      if best_i is None or link < best_link:
        best_i = i
        best_link = link

    if Log().is_on(Log.DEBUG):
      Log().debug(
          'Breaking cycle %s by breaking node %x' % (
          ' -> '.join(['%x' % node.id for node in (cycle + [cycle[0]])]),
          best_link.changeset.id,))

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    self.changeset_graph.delete_changeset(best_link.changeset)

    for changeset in new_changesets:
      self.changeset_graph.add_new_changeset(changeset)

  def run(self, run_options, stats_keeper):
    Log().quiet("Breaking revision changeset dependency cycles...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    shutil.copyfile(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET),
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN))
    cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN),
        DB_OPEN_WRITE)

    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_REVBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_REVBROKEN_INDEX),
        DB_OPEN_NEW)

    self.changeset_graph = ChangesetGraph(
        changeset_db, cvs_item_to_changeset_id
        )

    max_changeset_id = 0
    for changeset in self.get_source_changesets():
      changeset_db.store(changeset)
      if isinstance(changeset, RevisionChangeset):
        self.changeset_graph.add_changeset(changeset)
      max_changeset_id = max(max_changeset_id, changeset.id)

    self.changeset_key_generator = KeyGenerator(max_changeset_id + 1)

    self.processed_changeset_logger = ProcessedChangesetLogger()

    # Consume the graph, breaking cycles using self.break_cycle():
    for (changeset_id, time_range) in self.changeset_graph.consume_graph(
          cycle_breaker=self.break_cycle):
      self.processed_changeset_logger.log(changeset_id)

    self.processed_changeset_logger.flush()
    del self.processed_changeset_logger

    self.changeset_graph.close()
    self.changeset_graph = None
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class RevisionTopologicalSortPass(Pass):
  """Sort RevisionChangesets into commit order.

  Also convert them to OrderedChangesets, without changing their ids."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_REVSORTED_STORE)
    self._register_temp_file(config.CHANGESETS_REVSORTED_INDEX)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_REVBROKEN_STORE)
    self._register_temp_file_needed(config.CHANGESETS_REVBROKEN_INDEX)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET_REVBROKEN)

  def get_source_changesets(self, changeset_db):
    changeset_ids = changeset_db.keys()

    for changeset_id in changeset_ids:
      yield changeset_db[changeset_id]

  def get_changesets(self):
    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_REVBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_REVBROKEN_INDEX),
        DB_OPEN_READ,
        )

    changeset_graph = ChangesetGraph(
        changeset_db,
        CVSItemToChangesetTable(
            artifact_manager.get_temp_file(
                config.CVS_ITEM_TO_CHANGESET_REVBROKEN
                ),
            DB_OPEN_READ,
            )
        )

    for changeset in self.get_source_changesets(changeset_db):
      if isinstance(changeset, RevisionChangeset):
        changeset_graph.add_changeset(changeset)
      else:
        yield changeset

    changeset_ids = []

    # Sentry:
    changeset_ids.append(None)

    for (changeset_id, time_range) in changeset_graph.consume_graph():
      changeset_ids.append(changeset_id)

    # Sentry:
    changeset_ids.append(None)

    for i in range(1, len(changeset_ids) - 1):
      changeset = changeset_db[changeset_ids[i]]
      yield OrderedChangeset(
          changeset.id, changeset.cvs_item_ids, i - 1,
          changeset_ids[i - 1], changeset_ids[i + 1])

    changeset_graph.close()

  def run(self, run_options, stats_keeper):
    Log().quiet("Generating CVSRevisions in commit order...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    changesets_revordered_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_REVSORTED_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_REVSORTED_INDEX),
        DB_OPEN_NEW)

    for changeset in self.get_changesets():
      changesets_revordered_db.store(changeset)

    changesets_revordered_db.close()
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class BreakSymbolChangesetCyclesPass(Pass):
  """Break up any dependency cycles involving only SymbolChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_SYMBROKEN_STORE)
    self._register_temp_file(config.CHANGESETS_SYMBROKEN_INDEX)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_SYMBROKEN)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_REVSORTED_STORE)
    self._register_temp_file_needed(config.CHANGESETS_REVSORTED_INDEX)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET_REVBROKEN)

  def get_source_changesets(self):
    old_changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_REVSORTED_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_REVSORTED_INDEX),
        DB_OPEN_READ)

    changeset_ids = old_changeset_db.keys()

    for changeset_id in changeset_ids:
      yield old_changeset_db[changeset_id]

    old_changeset_db.close()

  def break_cycle(self, cycle):
    """Break up one or more changesets in CYCLE to help break the cycle.

    CYCLE is a list of Changesets where

        cycle[i] depends on cycle[i - 1]

    Break up one or more changesets in CYCLE to make progress towards
    breaking the cycle.  Update self.changeset_graph accordingly.

    It is not guaranteed that the cycle will be broken by one call to
    this routine, but at least some progress must be made."""

    self.processed_changeset_logger.flush()
    best_i = None
    best_link = None
    for i in range(len(cycle)):
      # It's OK if this index wraps to -1:
      link = ChangesetGraphLink(
          cycle[i - 1], cycle[i], cycle[i + 1 - len(cycle)])

      if best_i is None or link < best_link:
        best_i = i
        best_link = link

    if Log().is_on(Log.DEBUG):
      Log().debug(
          'Breaking cycle %s by breaking node %x' % (
          ' -> '.join(['%x' % node.id for node in (cycle + [cycle[0]])]),
          best_link.changeset.id,))

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    self.changeset_graph.delete_changeset(best_link.changeset)

    for changeset in new_changesets:
      self.changeset_graph.add_new_changeset(changeset)

  def run(self, run_options, stats_keeper):
    Log().quiet("Breaking symbol changeset dependency cycles...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    shutil.copyfile(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_REVBROKEN),
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_SYMBROKEN))
    cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_SYMBROKEN),
        DB_OPEN_WRITE)

    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_SYMBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_SYMBROKEN_INDEX),
        DB_OPEN_NEW)

    self.changeset_graph = ChangesetGraph(
        changeset_db, cvs_item_to_changeset_id
        )

    max_changeset_id = 0
    for changeset in self.get_source_changesets():
      changeset_db.store(changeset)
      if isinstance(changeset, SymbolChangeset):
        self.changeset_graph.add_changeset(changeset)
      max_changeset_id = max(max_changeset_id, changeset.id)

    self.changeset_key_generator = KeyGenerator(max_changeset_id + 1)

    self.processed_changeset_logger = ProcessedChangesetLogger()

    # Consume the graph, breaking cycles using self.break_cycle():
    for (changeset_id, time_range) in self.changeset_graph.consume_graph(
          cycle_breaker=self.break_cycle):
      self.processed_changeset_logger.log(changeset_id)

    self.processed_changeset_logger.flush()
    del self.processed_changeset_logger

    self.changeset_graph.close()
    self.changeset_graph = None
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class BreakAllChangesetCyclesPass(Pass):
  """Break up any dependency cycles that are closed by SymbolChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_ALLBROKEN_STORE)
    self._register_temp_file(config.CHANGESETS_ALLBROKEN_INDEX)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_ALLBROKEN)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_SYMBROKEN_STORE)
    self._register_temp_file_needed(config.CHANGESETS_SYMBROKEN_INDEX)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET_SYMBROKEN)

  def get_source_changesets(self):
    old_changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_SYMBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_SYMBROKEN_INDEX),
        DB_OPEN_READ)

    changeset_ids = old_changeset_db.keys()

    for changeset_id in changeset_ids:
      yield old_changeset_db[changeset_id]

    old_changeset_db.close()

  def _split_retrograde_changeset(self, changeset):
    """CHANGESET is retrograde.  Split it into non-retrograde changesets."""

    Log().debug('Breaking retrograde changeset %x' % (changeset.id,))

    self.changeset_graph.delete_changeset(changeset)

    # A map { cvs_branch_id : (max_pred_ordinal, min_succ_ordinal) }
    ordinal_limits = {}
    for cvs_branch in changeset.get_cvs_items():
      max_pred_ordinal = 0
      min_succ_ordinal = sys.maxint

      for pred_id in cvs_branch.get_pred_ids():
        pred_ordinal = self.ordinals.get(
            self.cvs_item_to_changeset_id[pred_id], 0)
        max_pred_ordinal = max(max_pred_ordinal, pred_ordinal)

      for succ_id in cvs_branch.get_succ_ids():
        succ_ordinal = self.ordinals.get(
            self.cvs_item_to_changeset_id[succ_id], sys.maxint)
        min_succ_ordinal = min(min_succ_ordinal, succ_ordinal)

      assert max_pred_ordinal < min_succ_ordinal
      ordinal_limits[cvs_branch.id] = (max_pred_ordinal, min_succ_ordinal,)

    # Find the earliest successor ordinal:
    min_min_succ_ordinal = sys.maxint
    for (max_pred_ordinal, min_succ_ordinal) in ordinal_limits.values():
      min_min_succ_ordinal = min(min_min_succ_ordinal, min_succ_ordinal)

    early_item_ids = []
    late_item_ids = []
    for (id, (max_pred_ordinal, min_succ_ordinal)) in ordinal_limits.items():
      if max_pred_ordinal >= min_min_succ_ordinal:
        late_item_ids.append(id)
      else:
        early_item_ids.append(id)

    assert early_item_ids
    assert late_item_ids

    early_changeset = changeset.create_split_changeset(
        self.changeset_key_generator.gen_id(), early_item_ids)
    late_changeset = changeset.create_split_changeset(
        self.changeset_key_generator.gen_id(), late_item_ids)

    self.changeset_graph.add_new_changeset(early_changeset)
    self.changeset_graph.add_new_changeset(late_changeset)

    early_split = self._split_if_retrograde(early_changeset.id)

    # Because of the way we constructed it, the early changeset should
    # not have to be split:
    assert not early_split

    self._split_if_retrograde(late_changeset.id)

  def _split_if_retrograde(self, changeset_id):
    node = self.changeset_graph[changeset_id]
    pred_ordinals = [
        self.ordinals[id]
        for id in node.pred_ids
        if id in self.ordinals
        ]
    pred_ordinals.sort()
    succ_ordinals = [
        self.ordinals[id]
        for id in node.succ_ids
        if id in self.ordinals
        ]
    succ_ordinals.sort()
    if pred_ordinals and succ_ordinals \
           and pred_ordinals[-1] >= succ_ordinals[0]:
      self._split_retrograde_changeset(self.changeset_db[node.id])
      return True
    else:
      return False

  def break_segment(self, segment):
    """Break a changeset in SEGMENT[1:-1].

    The range SEGMENT[1:-1] is not empty, and all of the changesets in
    that range are SymbolChangesets."""

    best_i = None
    best_link = None
    for i in range(1, len(segment) - 1):
      link = ChangesetGraphLink(segment[i - 1], segment[i], segment[i + 1])

      if best_i is None or link < best_link:
        best_i = i
        best_link = link

    if Log().is_on(Log.DEBUG):
      Log().debug(
          'Breaking segment %s by breaking node %x' % (
          ' -> '.join(['%x' % node.id for node in segment]),
          best_link.changeset.id,))

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    self.changeset_graph.delete_changeset(best_link.changeset)

    for changeset in new_changesets:
      self.changeset_graph.add_new_changeset(changeset)

  def break_cycle(self, cycle):
    """Break up one or more SymbolChangesets in CYCLE to help break the cycle.

    CYCLE is a list of SymbolChangesets where

        cycle[i] depends on cycle[i - 1]

    .  Break up one or more changesets in CYCLE to make progress
    towards breaking the cycle.  Update self.changeset_graph
    accordingly.

    It is not guaranteed that the cycle will be broken by one call to
    this routine, but at least some progress must be made."""

    if Log().is_on(Log.DEBUG):
      Log().debug(
          'Breaking cycle %s' % (
          ' -> '.join(['%x' % changeset.id
                       for changeset in cycle + [cycle[0]]]),))

    # Unwrap the cycle into a segment then break the segment:
    self.break_segment([cycle[-1]] + cycle + [cycle[0]])

  def run(self, run_options, stats_keeper):
    Log().quiet("Breaking CVSSymbol dependency loops...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    shutil.copyfile(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_SYMBROKEN),
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_ALLBROKEN))
    self.cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(
            config.CVS_ITEM_TO_CHANGESET_ALLBROKEN),
        DB_OPEN_WRITE)

    self.changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_INDEX),
        DB_OPEN_NEW)

    self.changeset_graph = ChangesetGraph(
        self.changeset_db, self.cvs_item_to_changeset_id
        )

    # A map {changeset_id : ordinal} for OrderedChangesets:
    self.ordinals = {}
    # A map {ordinal : changeset_id}:
    ordered_changeset_map = {}
    # A list of all BranchChangeset ids:
    branch_changeset_ids = []
    max_changeset_id = 0
    for changeset in self.get_source_changesets():
      self.changeset_db.store(changeset)
      self.changeset_graph.add_changeset(changeset)
      if isinstance(changeset, OrderedChangeset):
        ordered_changeset_map[changeset.ordinal] = changeset.id
        self.ordinals[changeset.id] = changeset.ordinal
      elif isinstance(changeset, BranchChangeset):
        branch_changeset_ids.append(changeset.id)
      max_changeset_id = max(max_changeset_id, changeset.id)

    # An array of ordered_changeset ids, indexed by ordinal:
    ordered_changesets = []
    for ordinal in range(len(ordered_changeset_map)):
      id = ordered_changeset_map[ordinal]
      ordered_changesets.append(id)

    ordered_changeset_ids = set(ordered_changeset_map.values())
    del ordered_changeset_map

    self.changeset_key_generator = KeyGenerator(max_changeset_id + 1)

    # First we scan through all BranchChangesets looking for
    # changesets that are individually "retrograde" and splitting
    # those up:
    for changeset_id in branch_changeset_ids:
      self._split_if_retrograde(changeset_id)

    del self.ordinals

    next_ordered_changeset = 0

    self.processed_changeset_logger = ProcessedChangesetLogger()

    while self.changeset_graph:
      # Consume any nodes that don't have predecessors:
      for (changeset_id, time_range) \
              in self.changeset_graph.consume_nopred_nodes():
        self.processed_changeset_logger.log(changeset_id)
        if changeset_id in ordered_changeset_ids:
          next_ordered_changeset += 1
          ordered_changeset_ids.remove(changeset_id)

      self.processed_changeset_logger.flush()

      if not self.changeset_graph:
        break

      # Now work on the next ordered changeset that has not yet been
      # processed.  BreakSymbolChangesetCyclesPass has broken any
      # cycles involving only SymbolChangesets, so the presence of a
      # cycle implies that there is at least one ordered changeset
      # left in the graph:
      assert next_ordered_changeset < len(ordered_changesets)

      id = ordered_changesets[next_ordered_changeset]
      path = self.changeset_graph.search_for_path(id, ordered_changeset_ids)
      if path:
        if Log().is_on(Log.DEBUG):
          Log().debug('Breaking path from %s to %s' % (path[0], path[-1],))
        self.break_segment(path)
      else:
        # There were no ordered changesets among the reachable
        # predecessors, so do generic cycle-breaking:
        if Log().is_on(Log.DEBUG):
          Log().debug(
              'Breaking generic cycle found from %s'
              % (self.changeset_db[id],)
              )
        self.break_cycle(self.changeset_graph.find_cycle(id))

    del self.processed_changeset_logger
    self.changeset_graph.close()
    self.changeset_graph = None
    self.cvs_item_to_changeset_id = None
    self.changeset_db = None

    Log().quiet("Done")


class TopologicalSortPass(Pass):
  """Sort changesets into commit order."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.CHANGESETS_ALLBROKEN_STORE)
    self._register_temp_file_needed(config.CHANGESETS_ALLBROKEN_INDEX)
    self._register_temp_file_needed(config.CVS_ITEM_TO_CHANGESET_ALLBROKEN)

  def get_source_changesets(self, changeset_db):
    for changeset_id in changeset_db.keys():
      yield changeset_db[changeset_id]

  def get_changesets(self):
    """Generate (changeset, timestamp) pairs in commit order."""

    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_INDEX),
        DB_OPEN_READ)

    changeset_graph = ChangesetGraph(
        changeset_db,
        CVSItemToChangesetTable(
            artifact_manager.get_temp_file(
                config.CVS_ITEM_TO_CHANGESET_ALLBROKEN
                ),
            DB_OPEN_READ,
            ),
        )
    symbol_changeset_ids = set()

    for changeset in self.get_source_changesets(changeset_db):
      changeset_graph.add_changeset(changeset)
      if isinstance(changeset, SymbolChangeset):
        symbol_changeset_ids.add(changeset.id)

    # Ensure a monotonically-increasing timestamp series by keeping
    # track of the previous timestamp and ensuring that the following
    # one is larger.
    timestamper = Timestamper()

    for (changeset_id, time_range) in changeset_graph.consume_graph():
      changeset = changeset_db[changeset_id]
      timestamp = timestamper.get(
          time_range.t_max, changeset.id in symbol_changeset_ids
          )
      yield (changeset, timestamp)

    changeset_graph.close()

  def run(self, run_options, stats_keeper):
    Log().quiet("Generating CVSRevisions in commit order...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    sorted_changesets = open(
        artifact_manager.get_temp_file(config.CHANGESETS_SORTED_DATAFILE),
        'w')

    for (changeset, timestamp) in self.get_changesets():
      sorted_changesets.write('%x %08x\n' % (changeset.id, timestamp,))

    sorted_changesets.close()

    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class CreateRevsPass(Pass):
  """Generate the SVNCommit <-> CVSRevision mapping databases.

  SVNCommitCreator also calls SymbolingsLogger to register
  CVSRevisions that represent an opening or closing for a path on a
  branch or tag.  See SymbolingsLogger for more details.

  This pass was formerly known as pass5."""

  def register_artifacts(self):
    self._register_temp_file(config.SVN_COMMITS_INDEX_TABLE)
    self._register_temp_file(config.SVN_COMMITS_STORE)
    self._register_temp_file(config.CVS_REVS_TO_SVN_REVNUMS)
    self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.CHANGESETS_ALLBROKEN_STORE)
    self._register_temp_file_needed(config.CHANGESETS_ALLBROKEN_INDEX)
    self._register_temp_file_needed(config.CHANGESETS_SORTED_DATAFILE)

  def get_changesets(self):
    """Generate (changeset,timestamp,) tuples in commit order."""

    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_ALLBROKEN_INDEX),
        DB_OPEN_READ)

    for line in file(
            artifact_manager.get_temp_file(
                config.CHANGESETS_SORTED_DATAFILE)):
      [changeset_id, timestamp] = [int(s, 16) for s in line.strip().split()]
      yield (changeset_db[changeset_id], timestamp)

    changeset_db.close()

  def get_svn_commits(self, creator):
    """Generate the SVNCommits, in order."""

    for (changeset, timestamp) in self.get_changesets():
      for svn_commit in creator.process_changeset(changeset, timestamp):
        yield svn_commit

  def log_svn_commit(self, svn_commit):
    """Output information about SVN_COMMIT."""

    Log().normal(
        'Creating Subversion r%d (%s)'
        % (svn_commit.revnum, svn_commit.get_description(),)
        )

    if isinstance(svn_commit, SVNRevisionCommit):
      for cvs_rev in svn_commit.cvs_revs:
        Log().verbose(' %s %s' % (cvs_rev.cvs_path, cvs_rev.rev,))

  def run(self, run_options, stats_keeper):
    Log().quiet("Mapping CVS revisions to Subversion commits...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)

    Ctx()._symbolings_logger = SymbolingsLogger()

    persistence_manager = PersistenceManager(DB_OPEN_NEW)

    creator = SVNCommitCreator()
    for svn_commit in self.get_svn_commits(creator):
      self.log_svn_commit(svn_commit)
      persistence_manager.put_svn_commit(svn_commit)

    stats_keeper.set_svn_rev_count(creator.revnum_generator.get_last_id())
    del creator

    persistence_manager.close()
    Ctx()._symbolings_logger.close()
    Ctx()._cvs_items_db.close()
    Ctx()._metadata_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_file_db.close()

    Log().quiet("Done")


class SortSymbolsPass(Pass):
  """This pass was formerly known as pass6."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)
    self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS)

  def run(self, run_options, stats_keeper):
    Log().quiet("Sorting symbolic name source revisions...")

    sort_file(
        artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS),
        artifact_manager.get_temp_file(
            config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
        options='-k 1,1 -k 2,2n -k 3')
    Log().quiet("Done")


class IndexSymbolsPass(Pass):
  """This pass was formerly known as pass7."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_OFFSETS_DB)
    self._register_temp_file_needed(config.PROJECTS)
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

    f.close()

    offsets_db = file(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB), 'wb')
    cPickle.dump(offsets, offsets_db, -1)
    offsets_db.close()

  def run(self, run_options, stats_keeper):
    Log().quiet("Determining offsets for all symbolic names...")
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._symbol_db = SymbolDatabase()
    self.generate_offsets_for_symbolings()
    Ctx()._symbol_db.close()
    Log().quiet("Done.")


class OutputPass(Pass):
  """This pass was formerly known as pass8."""

  def register_artifacts(self):
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.CVS_FILES_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_DB)
    self._register_temp_file_needed(config.SVN_COMMITS_INDEX_TABLE)
    self._register_temp_file_needed(config.SVN_COMMITS_STORE)
    self._register_temp_file_needed(config.CVS_REVS_TO_SVN_REVNUMS)
    Ctx().output_option.register_artifacts(self)

  def get_svn_commits(self):
    """Generate the SVNCommits in commit order."""

    persistence_manager = PersistenceManager(DB_OPEN_READ)

    svn_revnum = 1 # The first non-trivial commit

    # Peek at the first revision to find the date to use to initialize
    # the repository:
    svn_commit = persistence_manager.get_svn_commit(svn_revnum)

    while svn_commit:
      yield svn_commit
      svn_revnum += 1
      svn_commit = persistence_manager.get_svn_commit(svn_revnum)

    persistence_manager.close()

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
    Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()

    Ctx().output_option.setup(stats_keeper.svn_rev_count())

    for svn_commit in self.get_svn_commits():
      svn_commit.output(Ctx().output_option)

    Ctx().output_option.cleanup()

    Ctx()._symbol_db.close()
    Ctx()._cvs_items_db.close()
    Ctx()._metadata_db.close()
    Ctx()._cvs_file_db.close()


# The list of passes constituting a run of cvs2svn:
passes = [
    CollectRevsPass(),
    CollateSymbolsPass(),
    #CheckItemStoreDependenciesPass(config.CVS_ITEMS_STORE),
    FilterSymbolsPass(),
    #CheckIndexedItemStoreDependenciesPass(
    #    config.CVS_ITEMS_FILTERED_STORE,
    #    config.CVS_ITEMS_FILTERED_INDEX_TABLE),
    SortRevisionSummaryPass(),
    SortSymbolSummaryPass(),
    InitializeChangesetsPass(),
    #CheckIndexedItemStoreDependenciesPass(
    #    config.CVS_ITEMS_SORTED_STORE,
    #    config.CVS_ITEMS_SORTED_INDEX_TABLE),
    BreakRevisionChangesetCyclesPass(),
    RevisionTopologicalSortPass(),
    BreakSymbolChangesetCyclesPass(),
    BreakAllChangesetCyclesPass(),
    TopologicalSortPass(),
    CreateRevsPass(),
    SortSymbolsPass(),
    IndexSymbolsPass(),
    OutputPass(),
    ]


