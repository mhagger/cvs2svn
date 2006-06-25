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


class ExcludeSymbol:
  """An indication that a symbol should be excluded from the conversion."""

  def __init__(self, id, name):
    self.id = id
    self.name = name


class StrategyRule:
  """A single rule that might determine how to convert a symbol."""

  def get_symbol(self, stats):
    """Return an object describing what to do with the symbol in STATS.

    If this rule applies to the symbol whose statistics are collected
    in STATS, then return an object of type BranchSymbol, TagSymbol,
    or ExcludeSymbol as appropriate.  If this rule doesn't apply,
    return None."""

    raise NotImplementedError


class RegexpStrategyRule(StrategyRule):
  """A Strategy rule that bases its decisions on regexp matches.

  If self.regexp matches a symbol name, return self.action(id, name);
  otherwise, return None."""

  def __init__(self, pattern, action):
    """Initialize a RegexpStrategyRule.

    PATTERN is a string that will be treated as a regexp pattern.
    PATTERN must match a full symbol name for the rule to apply (i.e.,
    it is anchored at the beginning and end of the symbol name).

    ACTION is the class representing how the symbol should be
    converted.  It should be one of the classes BranchSymbol,
    TagSymbol, or ExcludeSymbol.

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


class SymbolStrategy:
  """A strategy class, used to decide how to convert CVS symbols."""

  def get_symbols(self, symbol_stats):
    """Return a map { name : Symbol } of symbols to convert.

    The values of the map are either BranchSymbol or TagSymbol
    objects, indicating how the symbol should be converted.  Symbols
    to be excluded should be left out of the output.  Return None if
    there was an error."""

    raise NotImplementedError


class StrictSymbolStrategy:
  """A strategy class implementing the old, strict strategy.

  To determine how a symbol is to be converted, first the
  StrategyRules in self._rules are checked.  The first rule that
  applies determines how the symbol is to be converted.  If no rule
  applies but the symbol was used unambiguously (only as a branch or
  only as a tag), then it is converted accordingly.  It is an error if
  there are any symbols that are not covered by the rules and are used
  ambiguously.

  The user can specify explicit rules on the command line via the
  --exclude, --force-branch, and --force-tag options.  These cause
  respectively add_exclude(), add_forced_branch(), or add_forced_tag()
  to be called, which adds a corresponding rule to self._rules."""

  def __init__(self):
    """Initialize an instance."""

    # A list of StrategyRule objects, applied in order to determine
    # how symbols should be converted.
    self._rules = []

  def add_rule(self, rule):
    self._rules.append(rule)

  def add_exclude(self, pattern):
    self.add_rule(RegexpStrategyRule(pattern, ExcludeSymbol))

  def add_forced_branch(self, pattern):
    self.add_rule(RegexpStrategyRule(pattern, BranchSymbol))

  def add_forced_tag(self, pattern):
    self.add_rule(RegexpStrategyRule(pattern, TagSymbol))

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
      if isinstance(symbol, ExcludeSymbol):
        # Don't write it to the database at all.
        pass
      elif symbol is not None:
        symbols[stats.name] = symbol
      else:
        # None of the rules covered this symbol; if the situation is
        # unambiguous, then decide here:
        is_tag = stats.tag_create_count > 0
        is_branch = stats.branch_create_count > 0
        if is_tag and is_branch:
          mismatches.append(stats)
        elif is_branch:
          symbols[stats.name] = BranchSymbol(stats.id, stats.name)
        else:
          symbols[stats.name] = TagSymbol(stats.id, stats.name)

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


