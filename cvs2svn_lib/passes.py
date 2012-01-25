# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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


import sys
import shutil
import cPickle

from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import Timestamper
from cvs2svn_lib.sort import sort_file
from cvs2svn_lib.log import logger
from cvs2svn_lib.pass_manager import Pass
from cvs2svn_lib.serializer import PrimedPickleSerializer
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_path_database import CVSPathDatabase
from cvs2svn_lib.metadata_database import MetadataDatabase
from cvs2svn_lib.project import read_projects
from cvs2svn_lib.project import write_projects
from cvs2svn_lib.symbol import LineOfDevelopment
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Symbol
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.symbol_database import create_symbol_database
from cvs2svn_lib.symbol_statistics import SymbolPlanError
from cvs2svn_lib.symbol_statistics import IndeterminateSymbolException
from cvs2svn_lib.symbol_statistics import SymbolStatistics
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.cvs_item_database import OldCVSItemStore
from cvs2svn_lib.cvs_item_database import IndexedCVSItemStore
from cvs2svn_lib.cvs_item_database import cvs_item_primer
from cvs2svn_lib.cvs_item_database import NewSortableCVSRevisionDatabase
from cvs2svn_lib.cvs_item_database import OldSortableCVSRevisionDatabase
from cvs2svn_lib.cvs_item_database import NewSortableCVSSymbolDatabase
from cvs2svn_lib.cvs_item_database import OldSortableCVSSymbolDatabase
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
from cvs2svn_lib.svn_commit import SVNRevisionCommit
from cvs2svn_lib.openings_closings import SymbolingsLogger
from cvs2svn_lib.svn_commit_creator import SVNCommitCreator
from cvs2svn_lib.persistence_manager import PersistenceManager
from cvs2svn_lib.repository_walker import walk_repository
from cvs2svn_lib.collect_data import CollectData
from cvs2svn_lib.check_dependencies_pass \
    import CheckItemStoreDependenciesPass
from cvs2svn_lib.check_dependencies_pass \
    import CheckIndexedItemStoreDependenciesPass


class CollectRevsPass(Pass):
  """This pass was formerly known as pass1."""

  def register_artifacts(self):
    self._register_temp_file(config.PROJECTS)
    self._register_temp_file(config.SYMBOL_STATISTICS)
    self._register_temp_file(config.METADATA_INDEX_TABLE)
    self._register_temp_file(config.METADATA_STORE)
    self._register_temp_file(config.CVS_PATHS_DB)
    self._register_temp_file(config.CVS_ITEMS_STORE)

  def run(self, run_options, stats_keeper):
    logger.quiet("Examining all CVS ',v' files...")
    Ctx()._projects = {}
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_NEW)
    cd = CollectData(stats_keeper)

    # Key generator for CVSFiles:
    file_key_generator = KeyGenerator()

    for project in run_options.projects:
      Ctx()._projects[project.id] = project
      cd.process_project(
          project,
          walk_repository(project, file_key_generator, cd.record_fatal_error),
          )
    run_options.projects = None

    fatal_errors = cd.close()

    if fatal_errors:
      raise FatalException("Pass 1 complete.\n"
                           + "=" * 75 + "\n"
                           + "Error summary:\n"
                           + "\n".join(fatal_errors) + "\n"
                           + "Exited due to fatal error(s).")

    Ctx()._cvs_path_db.close()
    write_projects(artifact_manager.get_temp_file(config.PROJECTS))
    logger.quiet("Done")


class CleanMetadataPass(Pass):
  """Clean up CVS revision metadata and write it to a new database."""

  def register_artifacts(self):
    self._register_temp_file(config.METADATA_CLEAN_INDEX_TABLE)
    self._register_temp_file(config.METADATA_CLEAN_STORE)
    self._register_temp_file_needed(config.METADATA_INDEX_TABLE)
    self._register_temp_file_needed(config.METADATA_STORE)

  def _get_clean_author(self, author):
    """Return AUTHOR, converted appropriately to UTF8.

    Raise a UnicodeException if it cannot be converted using the
    configured cvs_author_decoder."""

    try:
      return self._authors[author]
    except KeyError:
      pass

    try:
      clean_author = Ctx().cvs_author_decoder(author)
    except UnicodeError:
      self._authors[author] = author
      raise UnicodeError('Problem decoding author \'%s\'' % (author,))

    try:
      clean_author = clean_author.encode('utf8')
    except UnicodeError:
      self._authors[author] = author
      raise UnicodeError('Problem encoding author \'%s\'' % (author,))

    self._authors[author] = clean_author
    return clean_author

  def _get_clean_log_msg(self, log_msg):
    """Return LOG_MSG, converted appropriately to UTF8.

    Raise a UnicodeException if it cannot be converted using the
    configured cvs_log_decoder."""

    try:
      clean_log_msg = Ctx().cvs_log_decoder(log_msg)
    except UnicodeError:
      raise UnicodeError(
          'Problem decoding log message:\n'
          '%s\n'
          '%s\n'
          '%s'
          % ('-' * 75, log_msg, '-' * 75,)
          )

    try:
      return clean_log_msg.encode('utf8')
    except UnicodeError:
      raise UnicodeError(
          'Problem encoding log message:\n'
          '%s\n'
          '%s\n'
          '%s'
          % ('-' * 75, log_msg, '-' * 75,)
          )

  def _clean_metadata(self, metadata):
    """Clean up METADATA by overwriting its members as necessary."""

    try:
      metadata.author = self._get_clean_author(metadata.author)
    except UnicodeError, e:
      logger.warn('%s: %s' % (warning_prefix, e,))
      self.warnings = True

    try:
      metadata.log_msg = self._get_clean_log_msg(metadata.log_msg)
    except UnicodeError, e:
      logger.warn('%s: %s' % (warning_prefix, e,))
      self.warnings = True

  def run(self, run_options, stats_keeper):
    logger.quiet("Converting metadata to UTF8...")
    metadata_db = MetadataDatabase(
        artifact_manager.get_temp_file(config.METADATA_STORE),
        artifact_manager.get_temp_file(config.METADATA_INDEX_TABLE),
        DB_OPEN_READ,
        )
    metadata_clean_db = MetadataDatabase(
        artifact_manager.get_temp_file(config.METADATA_CLEAN_STORE),
        artifact_manager.get_temp_file(config.METADATA_CLEAN_INDEX_TABLE),
        DB_OPEN_NEW,
        )

    self.warnings = False

    # A map {author : clean_author} for those known (to avoid
    # repeating warnings):
    self._authors = {}

    for id in metadata_db.iterkeys():
      metadata = metadata_db[id]

      # Record the original author name because it might be needed for
      # expanding CVS keywords:
      metadata.original_author = metadata.author

      self._clean_metadata(metadata)

      metadata_clean_db[id] = metadata

    if self.warnings:
      raise FatalError(
          'There were warnings converting author names and/or log messages\n'
          'to Unicode (see messages above).  Please restart this pass\n'
          'with one or more \'--encoding\' parameters or with\n'
          '\'--fallback-encoding\'.'
          )

    metadata_clean_db.close()
    metadata_db.close()
    logger.quiet("Done")


class CollateSymbolsPass(Pass):
  """Divide symbols into branches, tags, and excludes."""

  conversion_names = {
      Trunk : 'trunk',
      Branch : 'branch',
      Tag : 'tag',
      ExcludedSymbol : 'exclude',
      Symbol : '.',
      }

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_DB)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_STATISTICS)

  def get_symbol(self, run_options, stats):
    """Use StrategyRules to decide what to do with a symbol.

    STATS is an instance of symbol_statistics._Stats describing an
    instance of Symbol or Trunk.  To determine how the symbol is to be
    converted, consult the StrategyRules in the project's
    symbol_strategy_rules.  Each rule is allowed a chance to change
    the way the symbol will be converted.  If the symbol is not a
    Trunk or TypedSymbol after all rules have run, raise
    IndeterminateSymbolException."""

    symbol = stats.lod
    rules = run_options.project_symbol_strategy_rules[symbol.project.id]
    for rule in rules:
      symbol = rule.get_symbol(symbol, stats)
      assert symbol is not None

    stats.check_valid(symbol)

    return symbol

  def log_symbol_summary(self, stats, symbol):
    if not self.symbol_info_file:
      return

    if isinstance(symbol, Trunk):
      name = '.trunk.'
      preferred_parent_name = '.'
    else:
      name = stats.lod.name
      if symbol.preferred_parent_id is None:
        preferred_parent_name = '.'
      else:
        preferred_parent = self.symbol_stats[symbol.preferred_parent_id].lod
        if isinstance(preferred_parent, Trunk):
          preferred_parent_name = '.trunk.'
        else:
          preferred_parent_name = preferred_parent.name

    if isinstance(symbol, LineOfDevelopment) and symbol.base_path:
      symbol_path = symbol.base_path
    else:
      symbol_path = '.'

    self.symbol_info_file.write(
        '%-5d %-30s %-10s %s %s\n' % (
            stats.lod.project.id,
            name,
            self.conversion_names[symbol.__class__],
            symbol_path,
            preferred_parent_name,
            )
        )
    self.symbol_info_file.write('      # %s\n' % (stats,))
    parent_counts = stats.possible_parents.items()
    if parent_counts:
      self.symbol_info_file.write('      # Possible parents:\n')
      parent_counts.sort(lambda a,b: cmp((b[1], a[0]), (a[1], b[0])))
      for (pp, count) in parent_counts:
        if isinstance(pp, Trunk):
          self.symbol_info_file.write(
              '      #     .trunk. : %d\n' % (count,)
              )
        else:
          self.symbol_info_file.write(
              '      #     %s : %d\n' % (pp.name, count,)
              )

  def get_symbols(self, run_options):
    """Return a map telling how to convert symbols.

    The return value is a map {AbstractSymbol : (Trunk|TypedSymbol)},
    indicating how each symbol should be converted.  Trunk objects in
    SYMBOL_STATS are passed through unchanged.  One object is included
    in the return value for each line of development described in
    SYMBOL_STATS.

    Raise FatalError if there was an error."""

    errors = []
    mismatches = []

    if Ctx().symbol_info_filename is not None:
      self.symbol_info_file = open(Ctx().symbol_info_filename, 'w')
      self.symbol_info_file.write(
          '# Columns: project_id symbol_name conversion symbol_path '
          'preferred_parent_name\n'
          )
    else:
      self.symbol_info_file = None

    # Initialize each symbol strategy rule a single time, even if it
    # is used in more than one project.  First define a map from
    # object id to symbol strategy rule:
    rules = {}
    for rule_list in run_options.project_symbol_strategy_rules:
      for rule in rule_list:
        rules[id(rule)] = rule

    for rule in rules.itervalues():
      rule.start(self.symbol_stats)

    retval = {}

    for stats in self.symbol_stats:
      try:
        symbol = self.get_symbol(run_options, stats)
      except IndeterminateSymbolException, e:
        self.log_symbol_summary(stats, stats.lod)
        mismatches.append(e.stats)
      except SymbolPlanError, e:
        self.log_symbol_summary(stats, stats.lod)
        errors.append(e)
      else:
        self.log_symbol_summary(stats, symbol)
        retval[stats.lod] = symbol

    for rule in rules.itervalues():
      rule.finish()

    if self.symbol_info_file:
      self.symbol_info_file.close()

    del self.symbol_info_file

    if errors or mismatches:
      s = ['Problems determining how symbols should be converted:\n']
      for e in errors:
        s.append('%s\n' % (e,))
      if mismatches:
        s.append(
            'It is not clear how the following symbols '
            'should be converted.\n'
            'Use --symbol-hints, --force-tag, --force-branch, --exclude, '
            'and/or\n'
            '--symbol-default to resolve the ambiguity.\n'
            )
        for stats in mismatches:
          s.append('    %s\n' % (stats,))
      raise FatalError(''.join(s))
    else:
      return retval

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    self.symbol_stats = SymbolStatistics(
        artifact_manager.get_temp_file(config.SYMBOL_STATISTICS)
        )

    symbol_map = self.get_symbols(run_options)

    # Check the symbols for consistency and bail out if there were errors:
    self.symbol_stats.check_consistency(symbol_map)

    # Check that the symbols all have SVN paths set and that the paths
    # are disjoint:
    Ctx().output_option.check_symbols(symbol_map)

    for symbol in symbol_map.itervalues():
      if isinstance(symbol, ExcludedSymbol):
        self.symbol_stats.exclude_symbol(symbol)

    create_symbol_database(symbol_map.values())

    del self.symbol_stats

    logger.quiet("Done")


class FilterSymbolsPass(Pass):
  """Delete any branches/tags that are to be excluded.

  Also delete revisions on excluded branches, and delete other
  references to the excluded symbols."""

  def register_artifacts(self):
    self._register_temp_file(config.ITEM_SERIALIZER)
    self._register_temp_file(config.CVS_REVS_DATAFILE)
    self._register_temp_file(config.CVS_SYMBOLS_DATAFILE)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_CLEAN_STORE)
    self._register_temp_file_needed(config.METADATA_CLEAN_INDEX_TABLE)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_STORE)
    Ctx().revision_collector.register_artifacts(self)

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
    Ctx()._metadata_db = MetadataDatabase(
        artifact_manager.get_temp_file(config.METADATA_CLEAN_STORE),
        artifact_manager.get_temp_file(config.METADATA_CLEAN_INDEX_TABLE),
        DB_OPEN_READ,
        )
    Ctx()._symbol_db = SymbolDatabase()
    cvs_item_store = OldCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_STORE))

    cvs_item_serializer = PrimedPickleSerializer(cvs_item_primer)
    f = open(artifact_manager.get_temp_file(config.ITEM_SERIALIZER), 'wb')
    cPickle.dump(cvs_item_serializer, f, -1)
    f.close()

    rev_db = NewSortableCVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_DATAFILE),
        cvs_item_serializer,
        )

    symbol_db = NewSortableCVSSymbolDatabase(
        artifact_manager.get_temp_file(config.CVS_SYMBOLS_DATAFILE),
        cvs_item_serializer,
        )

    revision_collector = Ctx().revision_collector

    logger.quiet("Filtering out excluded symbols and summarizing items...")

    stats_keeper.reset_cvs_rev_info()
    revision_collector.start()

    # Process the cvs items store one file at a time:
    for cvs_file_items in cvs_item_store.iter_cvs_file_items():
      logger.verbose(cvs_file_items.cvs_file.rcs_path)
      cvs_file_items.filter_excluded_symbols()
      cvs_file_items.mutate_symbols()
      cvs_file_items.adjust_parents()
      cvs_file_items.refine_symbols()
      cvs_file_items.determine_revision_properties(
          Ctx().revision_property_setters
          )
      cvs_file_items.record_opened_symbols()
      cvs_file_items.record_closed_symbols()
      cvs_file_items.check_link_consistency()

      # Give the revision collector a chance to collect data about the
      # file:
      revision_collector.process_file(cvs_file_items)

      # Store whatever is left to the new file and update statistics:
      stats_keeper.record_cvs_file(cvs_file_items.cvs_file)
      for cvs_item in cvs_file_items.values():
        stats_keeper.record_cvs_item(cvs_item)

        if isinstance(cvs_item, CVSRevision):
          rev_db.add(cvs_item)
        elif isinstance(cvs_item, CVSSymbol):
          symbol_db.add(cvs_item)

    stats_keeper.set_stats_reflect_exclude(True)

    rev_db.close()
    symbol_db.close()
    revision_collector.finish()
    cvs_item_store.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


class SortRevisionsPass(Pass):
  """Sort the revisions file."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_REVS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_REVS_DATAFILE)

  def run(self, run_options, stats_keeper):
    logger.quiet("Sorting CVS revision summaries...")
    sort_file(
        artifact_manager.get_temp_file(config.CVS_REVS_DATAFILE),
        artifact_manager.get_temp_file(
            config.CVS_REVS_SORTED_DATAFILE
            ),
        tempdirs=[Ctx().tmpdir],
        )
    logger.quiet("Done")


class SortSymbolsPass(Pass):
  """Sort the symbols file."""

  def register_artifacts(self):
    self._register_temp_file(config.CVS_SYMBOLS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.CVS_SYMBOLS_DATAFILE)

  def run(self, run_options, stats_keeper):
    logger.quiet("Sorting CVS symbol summaries...")
    sort_file(
        artifact_manager.get_temp_file(config.CVS_SYMBOLS_DATAFILE),
        artifact_manager.get_temp_file(
            config.CVS_SYMBOLS_SORTED_DATAFILE
            ),
        tempdirs=[Ctx().tmpdir],
        )
    logger.quiet("Done")


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
    self._register_temp_file_needed(config.CVS_PATHS_DB)
    self._register_temp_file_needed(config.ITEM_SERIALIZER)
    self._register_temp_file_needed(config.CVS_REVS_SORTED_DATAFILE)
    self._register_temp_file_needed(
        config.CVS_SYMBOLS_SORTED_DATAFILE)

  def get_revision_changesets(self):
    """Generate revision changesets, one at a time.

    Each time, yield a list of CVSRevisions that might potentially
    consititute a changeset."""

    # Create changesets for CVSRevisions:
    old_metadata_id = None
    old_timestamp = None
    changeset_items = []

    db = OldSortableCVSRevisionDatabase(
        artifact_manager.get_temp_file(
            config.CVS_REVS_SORTED_DATAFILE
            ),
        self.cvs_item_serializer,
        )

    for cvs_rev in db:
      if cvs_rev.metadata_id != old_metadata_id \
         or cvs_rev.timestamp > old_timestamp + config.COMMIT_THRESHOLD:
        # Start a new changeset.  First finish up the old changeset,
        # if any:
        if changeset_items:
          yield changeset_items
          changeset_items = []
        old_metadata_id = cvs_rev.metadata_id
      changeset_items.append(cvs_rev)
      old_timestamp = cvs_rev.timestamp

    # Finish up the last changeset, if any:
    if changeset_items:
      yield changeset_items

  def get_symbol_changesets(self):
    """Generate symbol changesets, one at a time.

    Each time, yield a list of CVSSymbols that might potentially
    consititute a changeset."""

    old_symbol_id = None
    changeset_items = []

    db = OldSortableCVSSymbolDatabase(
        artifact_manager.get_temp_file(
            config.CVS_SYMBOLS_SORTED_DATAFILE
            ),
        self.cvs_item_serializer,
        )

    for cvs_symbol in db:
      if cvs_symbol.symbol.id != old_symbol_id:
        # Start a new changeset.  First finish up the old changeset,
        # if any:
        if changeset_items:
          yield changeset_items
          changeset_items = []
        old_symbol_id = cvs_symbol.symbol.id
      changeset_items.append(cvs_symbol)

    # Finish up the last changeset, if any:
    if changeset_items:
      yield changeset_items

  @staticmethod
  def compare_items(a, b):
      return (
          cmp(a.timestamp, b.timestamp)
          or cmp(a.cvs_file.cvs_path, b.cvs_file.cvs_path)
          or cmp([int(x) for x in a.rev.split('.')],
                 [int(x) for x in b.rev.split('.')])
          or cmp(a.id, b.id))

  def break_internal_dependencies(self, changeset_items):
    """Split up CHANGESET_ITEMS if necessary to break internal dependencies.

    CHANGESET_ITEMS is a list of CVSRevisions that could possibly
    belong in a single RevisionChangeset, but there might be internal
    dependencies among the items.  Return a list of lists, where each
    sublist is a list of CVSRevisions and at least one internal
    dependency has been eliminated.  Iff CHANGESET_ITEMS does not have
    to be split, then the return value will contain a single value,
    namely the original value of CHANGESET_ITEMS.  Split
    CHANGESET_ITEMS at most once, even though the resulting changesets
    might themselves have internal dependencies."""

    # We only look for succ dependencies, since by doing so we
    # automatically cover pred dependencies as well.  First create a
    # list of tuples (pred, succ) of id pairs for CVSItems that depend
    # on each other.
    dependencies = []
    changeset_cvs_item_ids = set([cvs_rev.id for cvs_rev in changeset_items])
    for cvs_item in changeset_items:
      for next_id in cvs_item.get_succ_ids():
        if next_id in changeset_cvs_item_ids:
          # Sanity check: a CVSItem should never depend on itself:
          if next_id == cvs_item.id:
            raise InternalError('Item depends on itself: %s' % (cvs_item,))

          dependencies.append((cvs_item.id, next_id,))

    if dependencies:
      # Sort the changeset_items in a defined order (chronological to the
      # extent that the timestamps are correct and unique).
      changeset_items.sort(self.compare_items)
      indexes = {}
      for (i, changeset_item) in enumerate(changeset_items):
        indexes[changeset_item.id] = i
      # How many internal dependencies would be broken by breaking the
      # Changeset after a particular index?
      breaks = [0] * len(changeset_items)
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
          best_time = (changeset_items[i + 1].timestamp
                       - changeset_items[i].timestamp)
        elif breaks[i] == best_count \
             and (changeset_items[i + 1].timestamp
                  - changeset_items[i].timestamp) < best_time:
          best_i = i
          best_count = breaks[i]
          best_time = (changeset_items[i + 1].timestamp
                       - changeset_items[i].timestamp)
      # Reuse the old changeset.id for the first of the split changesets.
      return [changeset_items[:best_i + 1], changeset_items[best_i + 1:]]
    else:
      return [changeset_items]

  def break_all_internal_dependencies(self, changeset_items):
    """Keep breaking CHANGESET_ITEMS up to break all internal dependencies.

    CHANGESET_ITEMS is a list of CVSRevisions that could conceivably
    be part of a single changeset.  Break this list into sublists,
    where the CVSRevisions in each sublist are free of mutual
    dependencies."""

    # This method is written non-recursively to avoid any possible
    # problems with recursion depth.

    changesets_to_split = [changeset_items]
    while changesets_to_split:
      changesets = self.break_internal_dependencies(changesets_to_split.pop())
      if len(changesets) == 1:
        [changeset_items] = changesets
        yield changeset_items
      else:
        # The changeset had to be split; see if either of the
        # fragments have to be split:
        changesets.reverse()
        changesets_to_split.extend(changesets)

  def get_changesets(self):
    """Generate (Changeset, [CVSItem,...]) for all changesets.

    The Changesets already have their internal dependencies broken.
    The [CVSItem,...] list is the list of CVSItems in the
    corresponding Changeset."""

    for changeset_items in self.get_revision_changesets():
      for split_changeset_items \
              in self.break_all_internal_dependencies(changeset_items):
        yield (
            RevisionChangeset(
                self.changeset_key_generator.gen_id(),
                [cvs_rev.id for cvs_rev in split_changeset_items]
                ),
            split_changeset_items,
            )

    for changeset_items in self.get_symbol_changesets():
      yield (
          create_symbol_changeset(
              self.changeset_key_generator.gen_id(),
              changeset_items[0].symbol,
              [cvs_symbol.id for cvs_symbol in changeset_items]
              ),
          changeset_items,
          )

  def run(self, run_options, stats_keeper):
    logger.quiet("Creating preliminary commit sets...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()

    f = open(artifact_manager.get_temp_file(config.ITEM_SERIALIZER), 'rb')
    self.cvs_item_serializer = cPickle.load(f)
    f.close()

    changeset_db = ChangesetDatabase(
        artifact_manager.get_temp_file(config.CHANGESETS_STORE),
        artifact_manager.get_temp_file(config.CHANGESETS_INDEX),
        DB_OPEN_NEW,
        )
    cvs_item_to_changeset_id = CVSItemToChangesetTable(
        artifact_manager.get_temp_file(config.CVS_ITEM_TO_CHANGESET),
        DB_OPEN_NEW,
        )

    self.sorted_cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_NEW)

    self.changeset_key_generator = KeyGenerator()

    for (changeset, changeset_items) in self.get_changesets():
      if logger.is_on(logger.DEBUG):
        logger.debug(repr(changeset))
      changeset_db.store(changeset)
      for cvs_item in changeset_items:
        self.sorted_cvs_items_db.add(cvs_item)
        cvs_item_to_changeset_id[cvs_item.id] = changeset.id

    self.sorted_cvs_items_db.close()
    cvs_item_to_changeset_id.close()
    changeset_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_path_db.close()

    del self.cvs_item_serializer

    logger.quiet("Done")


class ProcessedChangesetLogger:
  def __init__(self):
    self.processed_changeset_ids = []

  def log(self, changeset_id):
    if logger.is_on(logger.DEBUG):
      self.processed_changeset_ids.append(changeset_id)

  def flush(self):
    if self.processed_changeset_ids:
      logger.debug(
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
    self._register_temp_file_needed(config.CVS_PATHS_DB)
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

    if logger.is_on(logger.DEBUG):
      logger.debug(
          'Breaking cycle %s by breaking node %x' % (
          ' -> '.join(['%x' % node.id for node in (cycle + [cycle[0]])]),
          best_link.changeset.id,))

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    self.changeset_graph.delete_changeset(best_link.changeset)

    for changeset in new_changesets:
      self.changeset_graph.add_new_changeset(changeset)

  def run(self, run_options, stats_keeper):
    logger.quiet("Breaking revision changeset dependency cycles...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
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
    for (changeset, time_range) in self.changeset_graph.consume_graph(
          cycle_breaker=self.break_cycle
          ):
      self.processed_changeset_logger.log(changeset.id)

    self.processed_changeset_logger.flush()
    del self.processed_changeset_logger

    self.changeset_graph.close()
    self.changeset_graph = None
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


class RevisionTopologicalSortPass(Pass):
  """Sort RevisionChangesets into commit order.

  Also convert them to OrderedChangesets, without changing their ids."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_REVSORTED_STORE)
    self._register_temp_file(config.CHANGESETS_REVSORTED_INDEX)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
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

    for (changeset, time_range) in changeset_graph.consume_graph():
      changeset_ids.append(changeset.id)

    # Sentry:
    changeset_ids.append(None)

    for i in range(1, len(changeset_ids) - 1):
      changeset = changeset_db[changeset_ids[i]]
      yield OrderedChangeset(
          changeset.id, changeset.cvs_item_ids, i - 1,
          changeset_ids[i - 1], changeset_ids[i + 1])

    changeset_graph.close()

  def run(self, run_options, stats_keeper):
    logger.quiet("Generating CVSRevisions in commit order...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
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
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


class BreakSymbolChangesetCyclesPass(Pass):
  """Break up any dependency cycles involving only SymbolChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_SYMBROKEN_STORE)
    self._register_temp_file(config.CHANGESETS_SYMBROKEN_INDEX)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_SYMBROKEN)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
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

    if logger.is_on(logger.DEBUG):
      logger.debug(
          'Breaking cycle %s by breaking node %x' % (
          ' -> '.join(['%x' % node.id for node in (cycle + [cycle[0]])]),
          best_link.changeset.id,))

    new_changesets = best_link.break_changeset(self.changeset_key_generator)

    self.changeset_graph.delete_changeset(best_link.changeset)

    for changeset in new_changesets:
      self.changeset_graph.add_new_changeset(changeset)

  def run(self, run_options, stats_keeper):
    logger.quiet("Breaking symbol changeset dependency cycles...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
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
    for (changeset, time_range) in self.changeset_graph.consume_graph(
          cycle_breaker=self.break_cycle
          ):
      self.processed_changeset_logger.log(changeset.id)

    self.processed_changeset_logger.flush()
    del self.processed_changeset_logger

    self.changeset_graph.close()
    self.changeset_graph = None
    Ctx()._cvs_items_db.close()
    Ctx()._symbol_db.close()
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


class BreakAllChangesetCyclesPass(Pass):
  """Break up any dependency cycles that are closed by SymbolChangesets."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_ALLBROKEN_STORE)
    self._register_temp_file(config.CHANGESETS_ALLBROKEN_INDEX)
    self._register_temp_file(config.CVS_ITEM_TO_CHANGESET_ALLBROKEN)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
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

    logger.debug('Breaking retrograde changeset %x' % (changeset.id,))

    self.changeset_graph.delete_changeset(changeset)

    # A map { cvs_branch_id : (max_pred_ordinal, min_succ_ordinal) }
    ordinal_limits = {}
    for cvs_branch in changeset.iter_cvs_items():
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

    if logger.is_on(logger.DEBUG):
      logger.debug(
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

    if logger.is_on(logger.DEBUG):
      logger.debug(
          'Breaking cycle %s' % (
          ' -> '.join(['%x' % changeset.id
                       for changeset in cycle + [cycle[0]]]),))

    # Unwrap the cycle into a segment then break the segment:
    self.break_segment([cycle[-1]] + cycle + [cycle[0]])

  def run(self, run_options, stats_keeper):
    logger.quiet("Breaking CVSSymbol dependency loops...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
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
      for (changeset, time_range) \
              in self.changeset_graph.consume_nopred_nodes():
        self.processed_changeset_logger.log(changeset.id)
        if changeset.id in ordered_changeset_ids:
          next_ordered_changeset += 1
          ordered_changeset_ids.remove(changeset.id)

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
        if logger.is_on(logger.DEBUG):
          logger.debug('Breaking path from %s to %s' % (path[0], path[-1],))
        self.break_segment(path)
      else:
        # There were no ordered changesets among the reachable
        # predecessors, so do generic cycle-breaking:
        if logger.is_on(logger.DEBUG):
          logger.debug(
              'Breaking generic cycle found from %s'
              % (self.changeset_db[id],)
              )
        self.break_cycle(self.changeset_graph.find_cycle(id))

    del self.processed_changeset_logger
    self.changeset_graph.close()
    self.changeset_graph = None
    self.cvs_item_to_changeset_id = None
    self.changeset_db = None

    logger.quiet("Done")


class TopologicalSortPass(Pass):
  """Sort changesets into commit order."""

  def register_artifacts(self):
    self._register_temp_file(config.CHANGESETS_SORTED_DATAFILE)
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
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

    for (changeset, time_range) in changeset_graph.consume_graph():
      timestamp = timestamper.get(
          time_range.t_max, changeset.id in symbol_changeset_ids
          )
      yield (changeset, timestamp)

    changeset_graph.close()

  def run(self, run_options, stats_keeper):
    logger.quiet("Generating CVSRevisions in commit order...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
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
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


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
    self._register_temp_file_needed(config.CVS_PATHS_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.SYMBOL_DB)
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

    logger.normal(
        'Creating Subversion r%d (%s)'
        % (svn_commit.revnum, svn_commit.get_description(),)
        )

    if isinstance(svn_commit, SVNRevisionCommit):
      for cvs_rev in svn_commit.cvs_revs:
        logger.verbose(' %s %s' % (cvs_rev.cvs_path, cvs_rev.rev,))

  def run(self, run_options, stats_keeper):
    logger.quiet("Mapping CVS revisions to Subversion commits...")

    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
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
    Ctx()._symbol_db.close()
    Ctx()._cvs_path_db.close()

    logger.quiet("Done")


class SortSymbolOpeningsClosingsPass(Pass):
  """This pass was formerly known as pass6."""

  def register_artifacts(self):
    self._register_temp_file(config.SYMBOL_OPENINGS_CLOSINGS_SORTED)
    self._register_temp_file_needed(config.SYMBOL_OPENINGS_CLOSINGS)

  def run(self, run_options, stats_keeper):
    logger.quiet("Sorting symbolic name source revisions...")

    def sort_key(line):
      line = line.split(' ', 2)
      return (int(line[0], 16), int(line[1]), line[2],)

    sort_file(
        artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS),
        artifact_manager.get_temp_file(
            config.SYMBOL_OPENINGS_CLOSINGS_SORTED
            ),
        key=sort_key,
        tempdirs=[Ctx().tmpdir],
        )
    logger.quiet("Done")


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
        logger.verbose(' ', Ctx()._symbol_db.get_symbol(id).name)
        old_id = id
        offsets[id] = fpos

    f.close()

    offsets_db = file(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB), 'wb')
    cPickle.dump(offsets, offsets_db, -1)
    offsets_db.close()

  def run(self, run_options, stats_keeper):
    logger.quiet("Determining offsets for all symbolic names...")
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._symbol_db = SymbolDatabase()
    self.generate_offsets_for_symbolings()
    Ctx()._symbol_db.close()
    logger.quiet("Done.")


class OutputPass(Pass):
  """This pass was formerly known as pass8."""

  def register_artifacts(self):
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.CVS_PATHS_DB)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_STORE)
    self._register_temp_file_needed(config.CVS_ITEMS_SORTED_INDEX_TABLE)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.METADATA_CLEAN_INDEX_TABLE)
    self._register_temp_file_needed(config.METADATA_CLEAN_STORE)
    self._register_temp_file_needed(config.SVN_COMMITS_INDEX_TABLE)
    self._register_temp_file_needed(config.SVN_COMMITS_STORE)
    self._register_temp_file_needed(config.CVS_REVS_TO_SVN_REVNUMS)
    Ctx().output_option.register_artifacts(self)

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
    Ctx()._metadata_db = MetadataDatabase(
        artifact_manager.get_temp_file(config.METADATA_CLEAN_STORE),
        artifact_manager.get_temp_file(config.METADATA_CLEAN_INDEX_TABLE),
        DB_OPEN_READ,
        )
    Ctx()._cvs_items_db = IndexedCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_STORE),
        artifact_manager.get_temp_file(config.CVS_ITEMS_SORTED_INDEX_TABLE),
        DB_OPEN_READ)
    Ctx()._symbol_db = SymbolDatabase()
    Ctx()._persistence_manager = PersistenceManager(DB_OPEN_READ)

    Ctx().output_option.setup(stats_keeper.svn_rev_count())

    svn_revnum = 1
    svn_commit = Ctx()._persistence_manager.get_svn_commit(svn_revnum)
    while svn_commit:
      svn_commit.output(Ctx().output_option)
      svn_revnum += 1
      svn_commit = Ctx()._persistence_manager.get_svn_commit(svn_revnum)

    Ctx().output_option.cleanup()
    Ctx()._persistence_manager.close()

    Ctx()._symbol_db.close()
    Ctx()._cvs_items_db.close()
    Ctx()._metadata_db.close()
    Ctx()._cvs_path_db.close()


# The list of passes constituting a run of cvs2svn:
passes = [
    CollectRevsPass(),
    CleanMetadataPass(),
    CollateSymbolsPass(),
    #CheckItemStoreDependenciesPass(config.CVS_ITEMS_STORE),
    FilterSymbolsPass(),
    SortRevisionsPass(),
    SortSymbolsPass(),
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
    SortSymbolOpeningsClosingsPass(),
    IndexSymbolsPass(),
    OutputPass(),
    ]


