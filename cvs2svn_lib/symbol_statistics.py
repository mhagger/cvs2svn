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

"""This module gathers and processes statistics about CVS symbols."""

import sys
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Symbol
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.symbol import TypedSymbol


class _Stats:
  """A summary of information about a symbol (tag or branch).

  Members:
    symbol -- the Symbol instance of the symbol being described

    tag_create_count -- the number of files on which this symbol
        appears as a tag

    branch_create_count -- the number of files on which this symbol
        appears as a branch

    branch_commit_count -- the number of commits on this branch

    branch_blockers -- a set of Symbol instances for any symbols that
        sprout from a branch with this name.

    possible_parents -- a map {LineOfDevelopment : count} indicating
        in how many files each LOD could have served as the parent of
        self.symbol."""

  def __init__(self, symbol):
    self.symbol = symbol
    self.tag_create_count = 0
    self.branch_create_count = 0
    self.branch_commit_count = 0
    self.branch_blockers = set()
    self.possible_parents = { }

  def register_tag_creation(self):
    """Register the creation of this symbol as a tag."""

    self.tag_create_count += 1

  def register_branch_creation(self):
    """Register the creation of this symbol as a branch."""

    self.branch_create_count += 1

  def register_branch_commit(self):
    """Register a commit on this symbol as a branch."""

    self.branch_commit_count += 1

  def register_branch_blocker(self, blocker):
    """Register BLOCKER as a blocker of this symbol as a branch."""

    self.branch_blockers.add(blocker)

  def register_possible_parent(self, lod):
    self.possible_parents[lod] = self.possible_parents.get(lod, 0) + 1

  def is_ghost(self):
    """Return True iff this symbol never really existed."""

    return (
        self.branch_commit_count == 0
        and not self.branch_blockers
        and not self.possible_parents
        )

  def get_preferred_parents(self):
    """Return the LineOfDevelopment preferred as parents for this symbol.

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

  def __str__(self):
    return (
        '\'%s\' is a tag in %d files, a branch in '
        '%d files and has commits in %d files'
        % (self.symbol, self.tag_create_count,
           self.branch_create_count, self.branch_commit_count))

  def __repr__(self):
    retval = ['%s; %d possible parents:\n'
              % (self, len(self.possible_parents))]
    parent_counts = self.possible_parents.items()
    parent_counts.sort(lambda a,b: - cmp(a[1], b[1]))
    for (symbol, count) in parent_counts:
      if isinstance(symbol, Trunk):
        retval.append('    trunk : %d\n' % count)
      else:
        retval.append('    \'%s\' : %d\n' % (symbol.name, count))
    return ''.join(retval)


class SymbolStatisticsCollector:
  """Collect statistics about symbols.

  Record a summary of information about each symbol in the RCS files
  into a database.  The database is created in CollectRevsPass and it
  is used in CollateSymbolsPass (via the SymbolStatistics class).

  collect_data._SymbolDataCollector inserts information into instances
  of this class by by calling its register_*() methods.

  Its main purpose is to assist in the decisions about which symbols
  can be treated as branches and tags and which may be excluded.

  The data collected by this class can be written to a file
  (config.SYMBOL_STATISTICS)."""

  def __init__(self):
    # A map { symbol -> _Stats } for all symbols (branches and tags)
    self._stats = { }

  def __del__(self):
    if self._stats is not None:
      Log().debug('%r was destroyed without being closed.' % (self,))
      self.close()

  def __getitem__(self, symbol):
    """Return the _Stats record for SYMBOL.

    Create and register a new one if necessary."""

    try:
      return self._stats[symbol]
    except KeyError:
      stats = _Stats(symbol)
      self._stats[symbol] = stats
      return stats

  def purge_ghost_symbols(self):
    """Purge any symbols that don't have any activity.

    Such ghost symbols can arise if a symbol was defined in an RCS
    file but pointed at a non-existent revision."""

    for stats in self._stats.values():
      if stats.is_ghost():
        Log().warn('Deleting ghost symbol: %s' % (stats.symbol,))
        del self._stats[stats.symbol]

  def close(self):
    """Store the stats database to the SYMBOL_STATISTICS file."""

    f = open(artifact_manager.get_temp_file(config.SYMBOL_STATISTICS),
             'wb')
    cPickle.dump(self._stats.values(), f, -1)
    f.close()
    self._stats = None


class SymbolStatistics:
  """Read and handle symbol statistics.

  The symbol statistics are read from a database created by
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

    # A map { Symbol -> _Stats } for all symbols (branches and tags)
    self._stats = { }

    stats_list = cPickle.load(open(filename, 'rb'))

    for stats in stats_list:
      self._stats[stats.symbol] = stats

  def __len__(self):
    return len(self._stats)

  def get_stats(self, symbol):
    """Return the _Stats object for Symbol instance SYMBOL.

    Raise KeyError if no such name exists."""

    return self._stats[symbol]

  def __iter__(self):
    return self._stats.itervalues()

  def _find_blocked_excludes(self, symbols):
    """Find all excluded symbols that are blocked by non-excluded symbols.

    Non-excluded symbols are by definition the symbols contained in
    SYMBOLS, which is a map { name : Symbol }.  Return a map { name :
    blocker_names } containing any problems found, where blocker_names
    is a set containing the names of blocking symbols."""

    blocked_branches = {}
    for stats in self:
      if stats.symbol.name not in symbols:
        blockers = [ blocker.name for blocker in stats.branch_blockers
                     if blocker.name in symbols ]
        if blockers:
          blocked_branches[stats.symbol.name] = set(blockers)
    return blocked_branches

  def _check_blocked_excludes(self, symbols):
    """Check whether any excluded branches are blocked.

    A branch can be blocked because it has another, non-excluded
    symbol that depends on it.  If any blocked excludes are found,
    output error messages describing the situation.  Return True if
    any errors were found."""

    Log().quiet("Checking for blocked exclusions...")

    blocked_excludes = self._find_blocked_excludes(symbols)
    if not blocked_excludes:
      return False

    for branch, branch_blockers in blocked_excludes.items():
      sys.stderr.write(error_prefix + ": The branch '%s' cannot be "
                       "excluded because the following symbols depend "
                       "on it:\n" % (branch))
      for blocker in branch_blockers:
        sys.stderr.write("    '%s'\n" % (blocker))
    sys.stderr.write("\n")
    return True

  def _check_invalid_tags(self, symbols):
    """Check for commits on any symbols that are to be converted as tags.

    In that case, they can't be converted as tags.  If any invalid
    tags are found, output error messages describing the problems.
    Return True iff any errors are found."""

    Log().quiet("Checking for forced tags with commits...")

    invalid_tags = [ ]
    for symbol in symbols.values():
      if isinstance(symbol, Tag):
        stats = self.get_stats(symbol)
        if stats.branch_commit_count > 0:
          invalid_tags.append(stats.symbol.name)

    if not invalid_tags:
      # No problems found:
      return False

    sys.stderr.write(error_prefix + ": The following branches cannot be "
                     "forced to be tags because they have commits:\n")
    for tag in invalid_tags:
      sys.stderr.write("    '%s'\n" % (tag))
    sys.stderr.write("\n")

    return True

  def check_consistency(self, symbols):
    """Check the plan for how to convert symbols for consistency.

    SYMBOLS is an iterable of TypedSymbol objects indicating how each
    symbol is to be converted.  Return True iff any problems were
    detected."""

    assert len(symbols) == len(self)

    # Create a map { symbol_name : Symbol } including only
    # non-excluded symbols:
    symbols_by_name = {}
    for symbol in symbols:
      assert isinstance(symbol, TypedSymbol)
      if not isinstance(symbol, ExcludedSymbol):
        symbols_by_name[symbol.name] = symbol

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
    appears most often as a possible parent for each symbol."""

    retval = {}
    for stats in self._stats.itervalues():
      (parents, count) = stats.get_preferred_parents()
      parents = list(parents)
      parents.sort()
      retval[stats.symbol] = parents[0]

    return retval


