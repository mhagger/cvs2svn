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

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol_database import Symbol
from cvs2svn_lib.symbol_database import TagSymbol
from cvs2svn_lib.symbol_database import ExcludedSymbol


class _Stats:
  """A summary of information about a symbol (tag or branch).

  Members:
    id -- a unique id (integer)

    name -- the name of the symbol

    tag_create_count -- the number of files on which this symbol
        appears as a tag

    branch_create_count -- the number of files on which this symbol
        appears as a branch

    branch_commit_count -- the number of commits on this branch

    branch_blockers -- the names of any symbols that depend on the
        branch."""

  def __init__(self, symbol, tag_create_count=0,
               branch_create_count=0, branch_commit_count=0,
               branch_blockers=[]):
    self.symbol = symbol
    self.tag_create_count = tag_create_count
    self.branch_create_count = branch_create_count
    self.branch_commit_count = branch_commit_count
    self.branch_blockers = set(branch_blockers)

  def __str__(self):
    return (
        '\'%s\' is a tag in %d files, a branch in '
        '%d files and has commits in %d files'
        % (self.symbol, self.tag_create_count,
           self.branch_create_count, self.branch_commit_count))


class SymbolStatisticsCollector:
  """Collect statistics about symbols.

  Record a brief summary of information about each symbol in the RCS
  files into a database.  The database is created in CollectRevsPass
  and it is used in CollateSymbolsPass (via the SymbolStatistics
  class).

  collect_data._SymbolDataCollector inserts information into instances
  of this class by by calling its register_*() methods.

  Its main purpose is to assist in the decisions about which symbols
  can be treated as branches and tags and which may be excluded.

  The data collected by this class can be written to a text file
  (config.SYMBOL_STATISTICS_LIST)."""

  def __init__(self):
    # A map { symbol -> record } for all symbols (branches and tags)
    self._stats = { }

  def _get_stats(self, symbol):
    """Return the _Stats record for SYMBOL.

    Create a new one if necessary."""

    try:
      return self._stats[symbol]
    except KeyError:
      stats = _Stats(symbol)
      self._stats[symbol] = stats
      return stats

  def register_tag_creation(self, symbol):
    """Register the creation of the tag SYMBOL."""

    self._get_stats(symbol).tag_create_count += 1

  def register_branch_creation(self, symbol):
    """Register the creation of the branch SYMBOL."""

    self._get_stats(symbol).branch_create_count += 1

  def register_branch_commit(self, symbol):
    """Register a commit on the branch SYMBOL."""

    self._get_stats(symbol).branch_commit_count += 1

  def register_branch_blocker(self, symbol, blocker):
    """Register BLOCKER as a blocker on the branch SYMBOL."""

    self._get_stats(symbol).branch_blockers.add(blocker.name)

  def write(self):
    """Store the stats database to file."""

    f = open(artifact_manager.get_temp_file(config.SYMBOL_STATISTICS_LIST),
             "w")
    for stats in self._stats.values():
      f.write(
          "%x %s %d %d %d"
          % (stats.symbol.id, stats.symbol.name, stats.tag_create_count,
             stats.branch_create_count, stats.branch_commit_count)
          )
      if stats.branch_blockers:
        f.write(' ')
        f.write(' '.join(list(stats.branch_blockers)))
      f.write('\n')
    f.close()


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

  The data in this class is read from a text file
  (config.SYMBOL_STATISTICS_LIST)."""

  def __init__(self):
    """Read the stats database from the SYMBOL_STATISTICS_LIST file."""

    # A hash that maps symbol names to _Stats instances
    self._stats_by_name = { }

    # A map { Symbol -> _Stats } for all symbols (branches and tags)
    self._stats = { }

    for line in open(artifact_manager.get_temp_file(
          config.SYMBOL_STATISTICS_LIST)):
      words = line.split()
      [id, name, tag_create_count,
       branch_create_count, branch_commit_count] = words[:5]
      branch_blockers = words[5:]
      symbol = Symbol(int(id, 16), name)
      tag_create_count = int(tag_create_count)
      branch_create_count = int(branch_create_count)
      branch_commit_count = int(branch_commit_count)
      stats = _Stats(
          symbol, tag_create_count,
          branch_create_count, branch_commit_count, branch_blockers)
      self._stats_by_name[symbol.name] = stats
      self._stats[symbol] = stats

  def get_stats(self, name):
    """Return the _Stats object for the symbol named NAME.

    Raise KeyError if no such name exists."""

    return self._stats_by_name[name]

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
        blockers = [ blocker for blocker in stats.branch_blockers
                     if blocker in symbols ]
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
      if isinstance(symbol, TagSymbol):
        stats = self.get_stats(symbol.name)
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

    SYMBOLS is an iterable of Symbol objects indicating how each name
    is to be converted.  Return True iff any problems were detected."""

    # Create a map { symbol_name : Symbol } including only
    # non-excluded symbols:
    symbols_by_name = {}
    for symbol in symbols:
      if not isinstance(symbol, ExcludedSymbol):
        symbols_by_name[symbol.name] = symbol

    # It is important that we not short-circuit here:
    return (
      self._check_blocked_excludes(symbols_by_name)
      | self._check_invalid_tags(symbols_by_name)
      )


