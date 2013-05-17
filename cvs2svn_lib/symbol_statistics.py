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

"""This module gathers and processes statistics about lines of development."""

import cPickle

from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.log import logger
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import IncludedSymbol
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol


class SymbolPlanError(FatalException):
  pass


class SymbolPlanException(SymbolPlanError):
  def __init__(self, stats, symbol, msg):
    self.stats = stats
    self.symbol = symbol
    SymbolPlanError.__init__(
        self,
        'Cannot convert the following symbol to %s: %s\n    %s'
        % (symbol, msg, self.stats,)
        )


class IndeterminateSymbolException(SymbolPlanException):
  def __init__(self, stats, symbol):
    SymbolPlanException.__init__(self, stats, symbol, 'Indeterminate type')


class _Stats:
  """A summary of information about a symbol (tag or branch).

  Members:

    lod -- the LineOfDevelopment instance of the lod being described

    tag_create_count -- the number of files in which this lod appears
        as a tag

    branch_create_count -- the number of files in which this lod
        appears as a branch

    branch_commit_count -- the number of files in which there were
        commits on this lod

    trivial_import_count -- the number of files in which this branch
        was purely a non-trunk default branch containing exactly one
        revision.

    pure_ntdb_count -- the number of files in which this branch was
        purely a non-trunk default branch (consisting only of
        non-trunk default branch revisions).

    branch_blockers -- a set of Symbol instances for any symbols that
        sprout from a branch with this name.

    possible_parents -- a map {LineOfDevelopment : count} indicating
        in how many files each LOD could have served as the parent of
        self.lod."""

  def __init__(self, lod):
    self.lod = lod
    self.tag_create_count = 0
    self.branch_create_count = 0
    self.branch_commit_count = 0
    self.branch_blockers = set()
    self.trivial_import_count = 0
    self.pure_ntdb_count = 0
    self.possible_parents = { }

  def register_tag_creation(self):
    """Register the creation of this lod as a tag."""

    self.tag_create_count += 1

  def register_branch_creation(self):
    """Register the creation of this lod as a branch."""

    self.branch_create_count += 1

  def register_branch_commit(self):
    """Register that there were commit(s) on this branch in one file."""

    self.branch_commit_count += 1

  def register_branch_blocker(self, blocker):
    """Register BLOCKER as preventing this symbol from being deleted.

    BLOCKER is a tag or a branch that springs from a revision on this
    symbol."""

    self.branch_blockers.add(blocker)

  def register_trivial_import(self):
    """Register that this branch is a trivial import branch in one file."""

    self.trivial_import_count += 1

  def register_pure_ntdb(self):
    """Register that this branch is a pure import branch in one file."""

    self.pure_ntdb_count += 1

  def register_possible_parent(self, lod):
    """Register that LOD was a possible parent for SELF.lod in a file."""

    self.possible_parents[lod] = self.possible_parents.get(lod, 0) + 1

  def register_branch_possible_parents(self, cvs_branch, cvs_file_items):
    """Register any possible parents of this symbol from CVS_BRANCH."""

    # This routine is a bottleneck.  So we define some local variables
    # to speed up access to frequently-needed variables.
    register = self.register_possible_parent
    parent_cvs_rev = cvs_file_items[cvs_branch.source_id]

    # The "obvious" parent of a branch is the branch holding the
    # revision where the branch is rooted:
    register(parent_cvs_rev.lod)

    # If the parent revision is a non-trunk default (vendor) branch
    # revision, then count trunk as a possible parent.  In particular,
    # the symbol could be grafted to the post-commit that copies the
    # vendor branch changes to trunk.  On the other hand, our vendor
    # branch handling is currently too stupid to do so.  On the other
    # other hand, when the vendor branch is being excluded from the
    # conversion, then the vendor branch revision will be moved to
    # trunk, again making trunk a possible parent--and *this* our code
    # can handle.  In the end, considering trunk a possible parent can
    # never affect the correctness of the conversion, and on balance
    # seems to improve the selection of symbol parents.
    if parent_cvs_rev.ntdbr:
      register(cvs_file_items.trunk)

    # Any other branches that are rooted at the same revision and
    # were committed earlier than the branch are also possible
    # parents:
    symbol = cvs_branch.symbol
    for branch_id in parent_cvs_rev.branch_ids:
      parent_symbol = cvs_file_items[branch_id].symbol
      # A branch cannot be its own parent, nor can a branch's
      # parent be a branch that was created after it.  So we stop
      # iterating when we reached the branch whose parents we are
      # collecting:
      if parent_symbol == symbol:
        break
      register(parent_symbol)

  def register_tag_possible_parents(self, cvs_tag, cvs_file_items):
    """Register any possible parents of this symbol from CVS_TAG."""

    # This routine is a bottleneck.  So use local variables to speed
    # up access to frequently-needed objects.
    register = self.register_possible_parent
    parent_cvs_rev = cvs_file_items[cvs_tag.source_id]

    # The "obvious" parent of a tag is the branch holding the
    # revision where the branch is rooted:
    register(parent_cvs_rev.lod)

    # If the parent revision is a non-trunk default (vendor) branch
    # revision, then count trunk as a possible parent.  See the
    # comment by the analogous code in
    # register_branch_possible_parents() for more details.
    if parent_cvs_rev.ntdbr:
      register(cvs_file_items.trunk)

    # Branches that are rooted at the same revision are also
    # possible parents:
    for branch_id in parent_cvs_rev.branch_ids:
      parent_symbol = cvs_file_items[branch_id].symbol
      register(parent_symbol)

  def is_ghost(self):
    """Return True iff this lod never really existed."""

    return (
        not isinstance(self.lod, Trunk)
        and self.branch_commit_count == 0
        and not self.branch_blockers
        and not self.possible_parents
        )

  def check_valid(self, symbol):
    """Check whether SYMBOL is a valid conversion of SELF.lod.

    It is planned to convert SELF.lod as SYMBOL.  Verify that SYMBOL
    is a TypedSymbol and that the information that it contains is
    consistent with that stored in SELF.lod.  (This routine does not
    do higher-level tests of whether the chosen conversion is actually
    sensible.)  If there are any problems, raise a
    SymbolPlanException."""

    if not isinstance(symbol, (Trunk, Branch, Tag, ExcludedSymbol)):
      raise IndeterminateSymbolException(self, symbol)

    if symbol.id != self.lod.id:
      raise SymbolPlanException(self, symbol, 'IDs must match')

    if symbol.project != self.lod.project:
      raise SymbolPlanException(self, symbol, 'Projects must match')

    if isinstance(symbol, IncludedSymbol) and symbol.name != self.lod.name:
      raise SymbolPlanException(self, symbol, 'Names must match')

  def check_preferred_parent_allowed(self, symbol):
    """Check that SYMBOL's preferred_parent_id is an allowed parent.

    SYMBOL is the planned conversion of SELF.lod.  Verify that its
    preferred_parent_id is a possible parent of SELF.lod.  If not,
    raise a SymbolPlanException describing the problem."""

    if isinstance(symbol, IncludedSymbol) \
           and symbol.preferred_parent_id is not None:
      for pp in self.possible_parents.keys():
        if pp.id == symbol.preferred_parent_id:
          return
      else:
        raise SymbolPlanException(
            self, symbol,
            'The selected parent is not among the symbol\'s '
            'possible parents.'
            )

  def __str__(self):
    return (
        '\'%s\' is '
        'a tag in %d files, '
        'a branch in %d files, '
        'a trivial import in %d files, '
        'a pure import in %d files, '
        'and has commits in %d files'
        % (self.lod, self.tag_create_count, self.branch_create_count,
           self.trivial_import_count, self.pure_ntdb_count,
           self.branch_commit_count)
        )

  def __repr__(self):
    retval = ['%s\n  possible parents:\n' % (self,)]
    parent_counts = self.possible_parents.items()
    parent_counts.sort(lambda a,b: - cmp(a[1], b[1]))
    for (symbol, count) in parent_counts:
      if isinstance(symbol, Trunk):
        retval.append('    trunk : %d\n' % count)
      else:
        retval.append('    \'%s\' : %d\n' % (symbol.name, count))
    if self.branch_blockers:
      blockers = list(self.branch_blockers)
      blockers.sort()
      retval.append('  blockers:\n')
      for blocker in blockers:
        retval.append('    \'%s\'\n' % (blocker,))
    return ''.join(retval)


class SymbolStatisticsCollector:
  """Collect statistics about lines of development.

  Record a summary of information about each line of development in
  the RCS files for later storage into a database.  The database is
  created in CollectRevsPass and it is used in CollateSymbolsPass (via
  the SymbolStatistics class).

  collect_data._SymbolDataCollector inserts information into instances
  of this class by by calling its register_*() methods.

  Its main purpose is to assist in the decisions about which symbols
  can be treated as branches and tags and which may be excluded.

  The data collected by this class can be written to the file
  config.SYMBOL_STATISTICS."""

  def __init__(self):
    # A map { lod -> _Stats } for all lines of development:
    self._stats = { }

  def __getitem__(self, lod):
    """Return the _Stats record for line of development LOD.

    Create and register a new one if necessary."""

    try:
      return self._stats[lod]
    except KeyError:
      stats = _Stats(lod)
      self._stats[lod] = stats
      return stats

  def register(self, cvs_file_items):
    """Register the statistics for each symbol in CVS_FILE_ITEMS."""

    for lod_items in cvs_file_items.iter_lods():
      if lod_items.lod is not None:
        branch_stats = self[lod_items.lod]

        branch_stats.register_branch_creation()

        if lod_items.cvs_revisions:
          branch_stats.register_branch_commit()

        if lod_items.is_trivial_import():
          branch_stats.register_trivial_import()

        if lod_items.is_pure_ntdb():
          branch_stats.register_pure_ntdb()

        for cvs_symbol in lod_items.iter_blockers():
          branch_stats.register_branch_blocker(cvs_symbol.symbol)

        if lod_items.cvs_branch is not None:
          branch_stats.register_branch_possible_parents(
              lod_items.cvs_branch, cvs_file_items
              )

      for cvs_tag in lod_items.cvs_tags:
        tag_stats = self[cvs_tag.symbol]

        tag_stats.register_tag_creation()

        tag_stats.register_tag_possible_parents(cvs_tag, cvs_file_items)

  def purge_ghost_symbols(self):
    """Purge any symbols that don't have any activity.

    Such ghost symbols can arise if a symbol was defined in an RCS
    file but pointed at a non-existent revision."""

    for stats in self._stats.values():
      if stats.is_ghost():
        logger.warn('Deleting ghost symbol: %s' % (stats.lod,))
        del self._stats[stats.lod]

  def close(self):
    """Store the stats database to the SYMBOL_STATISTICS file."""

    f = open(artifact_manager.get_temp_file(config.SYMBOL_STATISTICS), 'wb')
    cPickle.dump(self._stats.values(), f, -1)
    f.close()
    self._stats = None


class SymbolStatistics:
  """Read and handle line of development statistics.

  The statistics are read from a database created by
  SymbolStatisticsCollector.  This class has methods to process the
  statistics information and help with decisions about:

  1. What tags and branches should be processed/excluded

  2. What tags should be forced to be branches and vice versa (this
     class maintains some statistics to help the user decide)

  3. Are there inconsistencies?

     - A symbol that is sometimes a branch and sometimes a tag

     - A forced branch with commit(s) on it

     - A non-excluded branch depends on an excluded branch

  The data in this class is read from a pickle file."""

  def __init__(self, filename):
    """Read the stats database from FILENAME."""

    # A map { LineOfDevelopment -> _Stats } for all lines of
    # development:
    self._stats = { }

    # A map { LineOfDevelopment.id -> _Stats } for all lines of
    # development:
    self._stats_by_id = { }

    f = open(filename, 'rb')
    stats_list = cPickle.load(f)
    f.close()

    for stats in stats_list:
      self._stats[stats.lod] = stats
      self._stats_by_id[stats.lod.id] = stats

  def __len__(self):
    return len(self._stats)

  def __getitem__(self, lod_id):
    return self._stats_by_id[lod_id]

  def get_stats(self, lod):
    """Return the _Stats object for LineOfDevelopment instance LOD.

    Raise KeyError if no such lod exists."""

    return self._stats[lod]

  def __iter__(self):
    return self._stats.itervalues()

  def _check_blocked_excludes(self, symbol_map):
    """Check for any excluded LODs that are blocked by non-excluded symbols.

    If any are found, describe the problem to logger.error() and raise
    a FatalException."""

    # A list of (lod,[blocker,...]) tuples for excludes that are
    # blocked by the specified non-excluded blockers:
    problems = []

    for lod in symbol_map.itervalues():
      if isinstance(lod, ExcludedSymbol):
        # Symbol is excluded; make sure that its blockers are also
        # excluded:
        lod_blockers = []
        for blocker in self.get_stats(lod).branch_blockers:
          if isinstance(symbol_map.get(blocker, None), IncludedSymbol):
            lod_blockers.append(blocker)
        if lod_blockers:
          problems.append((lod, lod_blockers))

    if problems:
      s = []
      for (lod, lod_blockers) in problems:
        s.append(
            '%s: %s cannot be excluded because the following symbols '
                'depend on it:\n'
            % (error_prefix, lod,)
            )
        for blocker in lod_blockers:
          s.append('    %s\n' % (blocker,))
      s.append('\n')
      logger.error(''.join(s))

      raise FatalException()

  def _check_invalid_tags(self, symbol_map):
    """Check for commits on any symbols that are to be converted as tags.

    SYMBOL_MAP is a map {AbstractSymbol : (Trunk|TypedSymbol)}
    indicating how each AbstractSymbol is to be converted.  If there
    is a commit on a symbol, then it cannot be converted as a tag.  If
    any tags with commits are found, output error messages describing
    the problems then raise a FatalException."""

    logger.quiet("Checking for forced tags with commits...")

    invalid_tags = [ ]
    for symbol in symbol_map.itervalues():
      if isinstance(symbol, Tag):
        stats = self.get_stats(symbol)
        if stats.branch_commit_count > 0:
          invalid_tags.append(symbol)

    if not invalid_tags:
      # No problems found:
      return

    s = []
    s.append(
        '%s: The following branches cannot be forced to be tags '
        'because they have commits:\n'
        % (error_prefix,)
        )
    for tag in invalid_tags:
      s.append('    %s\n' % (tag.name))
    s.append('\n')
    logger.error(''.join(s))

    raise FatalException()

  def check_consistency(self, symbol_map):
    """Check the plan for how to convert symbols for consistency.

    SYMBOL_MAP is a map {AbstractSymbol : (Trunk|TypedSymbol)}
    indicating how each AbstractSymbol is to be converted.  If any
    problems are detected, describe the problem to logger.error() and
    raise a FatalException."""

    # We want to do all of the consistency checks even if one of them
    # fails, so that the user gets as much feedback as possible.  Set
    # this variable to True if any errors are found.
    error_found = False

    # Check that the planned preferred parents are OK for all
    # IncludedSymbols:
    for lod in symbol_map.itervalues():
      if isinstance(lod, IncludedSymbol):
        stats = self.get_stats(lod)
        try:
          stats.check_preferred_parent_allowed(lod)
        except SymbolPlanException, e:
          logger.error('%s\n' % (e,))
          error_found = True

    try:
      self._check_blocked_excludes(symbol_map)
    except FatalException:
      error_found = True

    try:
      self._check_invalid_tags(symbol_map)
    except FatalException:
      error_found = True

    if error_found:
      raise FatalException(
          'Please fix the above errors and restart CollateSymbolsPass'
          )

  def exclude_symbol(self, symbol):
    """SYMBOL has been excluded; remove it from our statistics."""

    del self._stats[symbol]
    del self._stats_by_id[symbol.id]

    # Remove references to this symbol from other statistics objects:
    for stats in self._stats.itervalues():
      stats.branch_blockers.discard(symbol)
      if symbol in stats.possible_parents:
        del stats.possible_parents[symbol]


