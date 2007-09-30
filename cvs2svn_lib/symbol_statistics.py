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

"""This module gathers and processes statistics about lines of development."""

import sys
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Symbol
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import TypedSymbol
from cvs2svn_lib.symbol import IncludedSymbol
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag


class SymbolPlanException(Exception):
  def __init__(self, stats, symbol):
    self.stats = stats
    self.symbol = symbol


class IndeterminateSymbolException(SymbolPlanException):
  def __init__(self, stats, symbol):
    SymbolPlanException.__init__(self, stats, symbol)


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

  def get_preferred_parents(self):
    """Return the LinesOfDevelopment preferred as parents for this lod.

    Return the tuple (BEST_SYMBOLS, BEST_COUNT), where BEST_SYMBOLS is
    the set of LinesOfDevelopment that appeared most often as possible
    parents, and BEST_COUNT is the number of times those symbols
    appeared.  BEST_SYMBOLS might contain multiple symbols if multiple
    LinesOfDevelopment have the same count."""

    best_count = -1
    best_symbols = set()
    for (symbol, count) in self.possible_parents.items():
      if count > best_count:
        best_count = count
        best_symbols.clear()
        best_symbols.add(symbol)
      elif count == best_count:
        best_symbols.add(symbol)

    return (best_symbols, best_count)

  def check_consistency(self, symbol):
    """Check whether the symbol described by SELF can be converted as SYMBOL.

    It is planned to convert SELF.lod as SYMBOL.  If there are any
    problems with that plan, raise a SymbolPlanException."""

    if not isinstance(symbol, TypedSymbol):
      raise self.IndeterminateSymbolException(stats, symbol)

  def __str__(self):
    return (
        '\'%s\' is a tag in %d files, a branch in %d files, '
        'a pure import in %d files, and has commits in %d files'
        % (self.lod, self.tag_create_count, self.branch_create_count,
           self.pure_ntdb_count, self.branch_commit_count))

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

        for cvs_tag in lod_items.cvs_tags:
          branch_stats.register_branch_blocker(cvs_tag.symbol)

        for cvs_branch in lod_items.cvs_branches:
          branch_stats.register_branch_blocker(cvs_branch.symbol)

        if lod_items.cvs_branch is not None:
          branch_stats.register_branch_possible_parents(
              lod_items.cvs_branch, cvs_file_items)

        if lod_items.is_pure_ntdb():
          branch_stats.register_pure_ntdb()

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
        Log().warn('Deleting ghost symbol: %s' % (stats.lod,))
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

    stats_list = cPickle.load(open(filename, 'rb'))

    for stats in stats_list:
      self._stats[stats.lod] = stats

  def __len__(self):
    return len(self._stats)

  def get_stats(self, lod):
    """Return the _Stats object for LineOfDevelopment instance LOD.

    Raise KeyError if no such lod exists."""

    return self._stats[lod]

  def __iter__(self):
    return self._stats.itervalues()

  def _find_blocked_excludes(self, symbols):
    """Find all excluded symbols that are blocked by non-excluded symbols.

    Non-excluded symbols are by definition the symbols contained in
    SYMBOLS, which is a map { name : Symbol } not including Trunk
    entries.  Return a map { name : blocker_names } containing any
    problems found, where blocker_names is a set containing the names
    of blocking symbols."""

    blocked_branches = {}
    for stats in self:
      if isinstance(stats.lod, Trunk):
        # Trunk is never excluded
        pass
      elif stats.lod.name not in symbols:
        blockers = [ blocker.name for blocker in stats.branch_blockers
                     if blocker.name in symbols ]
        if blockers:
          blocked_branches[stats.lod.name] = set(blockers)
    return blocked_branches

  def _check_blocked_excludes(self, symbols):
    """Check whether any excluded branches are blocked.

    SYMBOLS is a map { name : Symbol } not including Trunk entries.  A
    branch can be blocked because it has another, non-excluded symbol
    that depends on it.  If any blocked excludes are found in SYMBOLS,
    output error messages describing the situation.  Return True if
    any errors were found."""

    Log().quiet("Checking for blocked exclusions...")

    blocked_excludes = self._find_blocked_excludes(symbols)
    if not blocked_excludes:
      return False

    s = []
    for branch, branch_blockers in blocked_excludes.items():
      s.append(
          error_prefix + ": The branch '%s' cannot be "
          "excluded because the following symbols depend "
          "on it:\n" % (branch)
          )
      for blocker in branch_blockers:
        s.append("    '%s'\n" % (blocker,))
    s.append('\n')
    Log().error(''.join(s))

    return True

  def _check_invalid_tags(self, symbols):
    """Check for commits on any symbols that are to be converted as tags.

    SYMBOLS is a map { name : Symbol } not including Trunk entries.
    If there is a commit on a symbol, then it cannot be converted as a
    tag.  If any tags with commits are found, output error messages
    describing the problems.  Return True iff any errors are found."""

    Log().quiet("Checking for forced tags with commits...")

    invalid_tags = [ ]
    for symbol in symbols.values():
      if isinstance(symbol, Tag):
        stats = self.get_stats(symbol)
        if stats.branch_commit_count > 0:
          invalid_tags.append(stats.lod.name)

    if not invalid_tags:
      # No problems found:
      return False

    s = []
    s.append(
        error_prefix + ": The following branches cannot be "
        "forced to be tags because they have commits:\n"
        )
    for tag in invalid_tags:
      s.append("    '%s'\n" % (tag))
    s.append('\n')
    Log().error(''.join(s))

    return True

  def check_consistency(self, lods):
    """Check the plan for how to convert symbols for consistency.

    LODS is an iterable of Trunk and TypedSymbol objects indicating
    how each line of development is to be converted.  Return True iff
    any problems were detected."""

    # Keep track of which symbols have not yet been processed:
    unprocessed_lods = set(self._stats.keys())

    # Create a map { symbol_name : Symbol } including only
    # non-excluded symbols:
    symbols_by_name = {}
    for lod in lods:
      try:
        unprocessed_lods.remove(lod)
      except KeyError:
        if lod in self._stats:
          raise InternalError(
              'Symbol %s appeared twice in the symbol conversion table'
              % (lod,)
              )
        else:
          raise InternalError('Symbol %s is unknown' % (lod,))

      if isinstance(lod, Trunk):
        # Trunk is not processed any further.
        pass
      elif isinstance(lod, IncludedSymbol):
        # Symbol included; include it in the symbol check.
        symbols_by_name[lod.name] = lod
      elif isinstance(lod, ExcludedSymbol):
        # Symbol excluded; don't process it any further.
        pass
      else:
        raise InternalError('Symbol %s is of unexpected type' % (lod,))

    # Make sure that all symbols were processed:
    if unprocessed_lods:
        raise InternalError(
            'The following symbols did not appear in the symbol conversion '
            'table: %s'
            % (', '.join([str(s) for s in unprocessed_lods]),))

    # It is important that we not short-circuit here:
    return (
        self._check_blocked_excludes(symbols_by_name)
        | self._check_invalid_tags(symbols_by_name)
        )

  def exclude_symbol(self, symbol):
    """SYMBOL has been excluded; remove it from our statistics."""

    del self._stats[symbol]

    # Remove references to this symbol from other statistics objects:
    for stats in self._stats.itervalues():
      stats.branch_blockers.discard(symbol)
      if symbol in stats.possible_parents:
        del stats.possible_parents[symbol]

  def get_preferred_parents(self):
    """Return the LinesOfDevelopment preferred as parents for each symbol.

    Return a map {Symbol : LineOfDevelopment} giving the LOD that
    appears most often as a possible parent for each symbol.  Do not
    include entries for Trunk objects.  If a symbol has no possible
    parents (because it never exists as a CVSBranch or a CVSTag, which
    can happen if it has been severed from its parent), then the
    associated value is None."""

    retval = {}
    for stats in self._stats.itervalues():
      if isinstance(stats.lod, Trunk):
        # Trunk entries don't have any parents.
        pass
      else:
        (parents, count) = stats.get_preferred_parents()
        if not parents:
          retval[stats.lod] = None
        else:
          parents = list(parents)
          parents.sort()
          retval[stats.lod] = parents[0]

    return retval


