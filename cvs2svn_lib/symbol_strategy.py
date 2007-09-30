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

"""SymbolStrategy classes determine how to convert symbols."""

import sys
import re

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol


class StrategyRule:
  """A single rule that might determine how to convert a symbol."""

  def get_symbol(self, stats):
    """Return an object describing what to do with the symbol in STATS.

    If this rule applies to the symbol whose statistics are collected
    in STATS, then return an object of type Branch, Tag, or
    ExcludedSymbol as appropriate.  If this rule doesn't apply, return
    None."""

    raise NotImplementedError


class _RegexpStrategyRule(StrategyRule):
  """A Strategy rule that bases its decisions on regexp matches.

  If self.regexp matches a symbol name, return self.action(symbol);
  otherwise, return None."""

  def __init__(self, pattern, action):
    """Initialize a _RegexpStrategyRule.

    PATTERN is a string that will be treated as a regexp pattern.
    PATTERN must match a full symbol name for the rule to apply (i.e.,
    it is anchored at the beginning and end of the symbol name).

    ACTION is the class representing how the symbol should be
    converted.  It should be one of the classes Branch, Tag, or
    ExcludedSymbol.

    If PATTERN matches a symbol name, then get_symbol() returns
    ACTION(name, id); otherwise it returns None."""

    try:
      self.regexp = re.compile('^' + pattern + '$')
    except re.error:
      raise FatalError("%r is not a valid regexp." % (pattern,))

    self.action = action

  def get_symbol(self, stats):
    if self.regexp.match(stats.lod.name):
      return self.action(stats.lod)
    else:
      return None


class ForceBranchRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be branches."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, Branch)


class ForceTagRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be tags."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, Tag)


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
      return Branch(stats.lod)
    elif is_tag:
      return Tag(stats.lod)
    else:
      # The symbol didn't appear at all:
      return None


class BranchIfCommitsRule(StrategyRule):
  """If there was ever a commit on the symbol, convert it as a branch."""

  def get_symbol(self, stats):
    if stats.branch_commit_count > 0:
      return Branch(stats.lod)
    else:
      return None


class HeuristicStrategyRule(StrategyRule):
  """Convert symbol based on how often it was used as a branch/tag.

  Whichever happened more often determines how the symbol is
  converted."""

  def get_symbol(self, stats):
    if stats.tag_create_count >= stats.branch_create_count:
      return Tag(stats.lod)
    else:
      return Branch(stats.lod)


class AllBranchRule(StrategyRule):
  """Convert all symbols as branches.

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, stats):
    return Branch(stats.lod)


class AllTagRule(StrategyRule):
  """Convert all symbols as tags.

  We don't worry about conflicts here; they will be caught later by
  SymbolStatistics.check_consistency().

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, stats):
    return Tag(stats.lod)


def get_symbol_for_stats(stats):
  """Use StrategyRules to decide what to do with a symbol.

  STATS is an instance of symbol_statistics._Stats describing a Symbol
  (i.e., not a Trunk instance).  To determine how the symbol is to be
  converted, consult the StrategyRules in Ctx().symbol_strategy_rules.
  The first rule that applies determines how the symbol is to be
  converted."""

  for rule in Ctx().symbol_strategy_rules:
    symbol = rule.get_symbol(stats)
    if symbol is not None:
      return symbol
  else:
    return None


