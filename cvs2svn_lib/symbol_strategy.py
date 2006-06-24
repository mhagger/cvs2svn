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

"""SymbolStrategy classes determine how to convert symbols."""

import sys

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol_database import BranchSymbol
from cvs2svn_lib.symbol_database import TagSymbol


def match_regexp_list(regexp_list, s):
  """Test whether string S matches any of the compiled regexps in
  REGEXP_LIST."""

  for regexp in regexp_list:
    if regexp.match(s):
      return True
  return False


class SymbolStrategy:
  """A strategy class, used to decide how to handle each symbol."""

  def get_symbols(self, symbol_stats):
    """Return a map { name : Symbol } of symbols to convert.

    The values of the map are either BranchSymbol or TagSymbol
    objects, indicating how the symbol should be converted.  Symbols
    to be excluded should be left out of the output.  Return None if
    there was an error."""

    raise NotImplementedError


class StrictSymbolStrategy:
  """A strategy class implementing the old, strict strategy.

  Any symbols that were sometimes used for branches, sometimes for
  tags, have to be resolved explicitly by the user via the --exclude,
  --force-branch, and --force-tags options."""

  def __init__(self, excludes, forced_branches, forced_tags):
    """Initialize an instance.

    EXCLUDES is a list of regexps matching the names of symbols that
    should be excluded from the conversion.  FORCED_BRANCHES and
    FORCED_TAGS are lists of symbol names that should be converted as
    branches or tags, respectively.  Symbols not covered by one of
    these special cases must be unambiguous tags or branches."""

    self.excludes = excludes
    self.forced_branches = forced_branches
    self.forced_tags = forced_tags

  def _find_mismatches(self, symbol_stats, symbols):
    """Find all symbols in SYMBOLS that are defined as both tags and branches.

    Returns a set of _Stats objects, one for each mismatch."""

    mismatches = set()
    for symbol in symbols.values():
      stats = symbol_stats.get_stats(symbol.name)
      if (stats.tag_create_count > 0
          and stats.branch_create_count > 0):
        mismatches.add(stats)
    return mismatches

  def _check_symbol_mismatches(self, symbol_stats, symbols):
    """Check for symbols that are defined as both tags and branches.

    Consider the symbols in SYMBOLS.  If any mismatches are found,
    output error messages describing the problems.  Return True iff
    any problems are found."""

    Log().quiet("Checking for tag/branch mismatches...")

    mismatches = self._find_mismatches(symbol_stats, symbols)

    def is_not_forced(mismatch):
      name = mismatch.name
      return not (name in self.forced_tags or name in self.forced_branches)

    mismatches = filter(is_not_forced, mismatches)
    if not mismatches:
      # No problems found:
      return False

    sys.stderr.write(
        error_prefix + ": The following symbols are tags in some files and "
        "branches in others.\n"
        "Use --force-tag, --force-branch and/or --exclude to resolve the "
        "symbols.\n")
    for stats in mismatches:
      sys.stderr.write(
          "    '%s' is a tag in %d files, a branch in "
          "%d files and has commits in %d files.\n"
          % (stats.name, stats.tag_create_count,
             stats.branch_create_count, stats.branch_commit_count))

    return True

  def get_symbols(self, symbol_stats):
    symbols = {}
    for stats in symbol_stats:
      if match_regexp_list(self.excludes, stats.name):
        # Don't write it to the database at all.
        pass
      elif stats.name in self.forced_branches:
        symbols[stats.name] = BranchSymbol(stats.id, stats.name)
      elif stats.name in self.forced_tags:
        symbols[stats.name] = TagSymbol(stats.id, stats.name)
      elif stats.branch_create_count > 0:
        symbols[stats.name] = BranchSymbol(stats.id, stats.name)
      else:
        symbols[stats.name] = TagSymbol(stats.id, stats.name)

    if self._check_symbol_mismatches(symbol_stats, symbols):
      return None

    return symbols


