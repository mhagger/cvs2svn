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
import re

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol_database import BranchSymbol
from cvs2svn_lib.symbol_database import TagSymbol
from cvs2svn_lib.symbol_database import ExcludedSymbol


class StrategyRule:
  """A single rule that might determine how to convert a symbol."""

  def get_symbol(self, stats):
    """Return an object describing what to do with the symbol in STATS.

    If this rule applies to the symbol whose statistics are collected
    in STATS, then return an object of type BranchSymbol, TagSymbol,
    or ExcludedSymbol as appropriate.  If this rule doesn't apply,
    return None."""

    raise NotImplementedError


class _RegexpStrategyRule(StrategyRule):
  """A Strategy rule that bases its decisions on regexp matches.

  If self.regexp matches a symbol name, return self.action(id, name);
  otherwise, return None."""

  def __init__(self, pattern, action):
    """Initialize a _RegexpStrategyRule.

    PATTERN is a string that will be treated as a regexp pattern.
    PATTERN must match a full symbol name for the rule to apply (i.e.,
    it is anchored at the beginning and end of the symbol name).

    ACTION is the class representing how the symbol should be
    converted.  It should be one of the classes BranchSymbol,
    TagSymbol, or ExcludedSymbol.

    If PATTERN matches a symbol name, then get_symbol() returns
    ACTION(name, id); otherwise it returns None."""

    try:
      self.regexp = re.compile('^' + pattern + '$')
    except re.error, e:
      raise FatalError("'%s' is not a valid regexp." % (value,))

    self.action = action

  def get_symbol(self, stats):
    if self.regexp.match(stats.name):
      return self.action(stats.id, stats.name)
    else:
      return None


class ForceBranchRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be branches."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, BranchSymbol)


class ForceTagRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be tags."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, TagSymbol)


class ExcludeRegexpStrategyRule(_RegexpStrategyRule):
  """Exclude symbols matching pattern."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, ExcludedSymbol)


class UnambiguousUsageRule(StrategyRule):
  """If a symbol is used unambiguously as a tag/branch, convert it as such."""

  def get_symbol(self, stats):
    is_tag = stats.tag_create_count > 0
    is_branch = stats.branch_create_count > 0 or stats.branch_commit_count > 0
    if is_tag and is_branch:
      # Can't decide
      return None
    elif is_branch:
      return BranchSymbol(stats.id, stats.name)
    elif is_tag:
      return TagSymbol(stats.id, stats.name)
    else:
      # The symbol didn't appear at all:
      return None


class BranchIfCommitsRule(StrategyRule):
  """If there was ever a commit on the symbol, convert it as a branch."""

  def get_symbol(self, stats):
    if stats.branch_commit_count > 0:
      return BranchSymbol(stats.id, stats.name)
    else:
      return None


class HeuristicStrategyRule(StrategyRule):
  """Convert symbol based on how often it was used as a branch/tag.

  Whichever happened more often determines how the symbol is
  converted."""

  def get_symbol(self, stats):
    if stats.tag_create_count >= stats.branch_create_count:
      return TagSymbol(stats.id, stats.name)
    else:
      return BranchSymbol(stats.id, stats.name)


class AllBranchRule(StrategyRule):
  """Convert all symbols as branches.

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, stats):
    return BranchSymbol(stats.id, stats.name)


class AllTagRule(StrategyRule):
  """Convert all symbols as tags.

  We don't worry about conflicts here; they will be caught later by
  SymbolStatistics.check_consistency().

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, stats):
    return TagSymbol(stats.id, stats.name)


class SymbolStrategy:
  """A strategy class, used to decide how to convert CVS symbols."""

  def get_symbols(self, symbol_stats):
    """Return a map { name : Symbol } of symbols to convert.

    The values of the map are either BranchSymbol or TagSymbol
    objects, indicating how the symbol should be converted.  Symbols
    to be excluded should be left out of the output.  Return None if
    there was an error."""

    raise NotImplementedError


class RuleBasedSymbolStrategy:
  """A strategy that uses StrategyRules to decide what to do with a symbol.

  To determine how a symbol is to be converted, first check the
  StrategyRules in self._rules.  The first rule that applies
  determines how the symbol is to be converted.  It is an error if
  there are any symbols that are not covered by the rules."""

  def __init__(self):
    """Initialize an instance."""

    # A list of StrategyRule objects, applied in order to determine
    # how symbols should be converted.
    self._rules = []

  def add_rule(self, rule):
    self._rules.append(rule)

  def _get_symbol(self, stats):
    for rule in self._rules:
      symbol = rule.get_symbol(stats)
      if symbol is not None:
        return symbol
    else:
      return None

  def get_symbols(self, symbol_stats):
    symbols = {}
    mismatches = []
    for stats in symbol_stats:
      symbol = self._get_symbol(stats)
      if isinstance(symbol, ExcludedSymbol):
        # Don't write it to the database at all.
        pass
      elif symbol is not None:
        symbols[stats.name] = symbol
      else:
        # None of the rules covered this symbol.
        mismatches.append(stats)

    if mismatches:
      sys.stderr.write(
          error_prefix + ": It is not clear how the following symbols "
          "should be converted.\n"
          "Use --force-tag, --force-branch and/or --exclude to resolve the "
          "ambiguity.\n")
      for stats in mismatches:
        sys.stderr.write("    %s\n" % stats)
      return None
    else:
      return symbols


