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
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import TypedSymbol
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol


class StrategyRule:
  """A single rule that might determine how to convert a symbol."""

  def start(self, symbol_statistics):
    """This method is called once before get_symbol() is ever called.

    The StrategyRule can override this method to do whatever it wants
    to prepare itself for work.  SYMBOL_STATISTICS is an instance of
    SymbolStatistics containing the statistics for all symbols in all
    projects."""

    pass

  def get_symbol(self, symbol, stats):
    """Return an object describing what to do with the symbol in STATS.

    SYMBOL holds a Symbol object as it has been determined so far.
    Initially it is a naked Symbol instance, but hopefully one of
    these method calls will turn it into a TypedSymbol.

    If this rule applies to the symbol (whose statistics are collected
    in STATS), then return the appropriate TypedSymbol object.  If
    this rule doesn't apply, return SYMBOL unchanged."""

    raise NotImplementedError()

  def finish(self):
    """This method is called once after get_symbol() is done being called.

    The StrategyRule can override this method do whatever it wants to
    release resources, etc."""

    pass


class _RegexpStrategyRule(StrategyRule):
  """A Strategy rule that bases its decisions on regexp matches.

  If self.regexp matches a symbol name, return self.action(symbol);
  otherwise, return the symbol unchanged."""

  def __init__(self, pattern, action):
    """Initialize a _RegexpStrategyRule.

    PATTERN is a string that will be treated as a regexp pattern.
    PATTERN must match a full symbol name for the rule to apply (i.e.,
    it is anchored at the beginning and end of the symbol name).

    ACTION is the class representing how the symbol should be
    converted.  It should be one of the classes Branch, Tag, or
    ExcludedSymbol.

    If PATTERN matches a symbol name, then get_symbol() returns
    ACTION(name, id); otherwise it returns SYMBOL unchanged."""

    try:
      self.regexp = re.compile('^' + pattern + '$')
    except re.error:
      raise FatalError("%r is not a valid regexp." % (pattern,))

    self.action = action

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    elif self.regexp.match(symbol.name):
      return self.action(symbol)
    else:
      return symbol


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

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    is_tag = stats.tag_create_count > 0
    is_branch = stats.branch_create_count > 0 or stats.branch_commit_count > 0
    if is_tag and is_branch:
      # Can't decide
      return symbol
    elif is_branch:
      return Branch(symbol)
    elif is_tag:
      return Tag(symbol)
    else:
      # The symbol didn't appear at all:
      return symbol


class BranchIfCommitsRule(StrategyRule):
  """If there was ever a commit on the symbol, convert it as a branch."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    elif stats.branch_commit_count > 0:
      return Branch(symbol)
    else:
      return symbol


class HeuristicStrategyRule(StrategyRule):
  """Convert symbol based on how often it was used as a branch/tag.

  Whichever happened more often determines how the symbol is
  converted."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    elif stats.tag_create_count >= stats.branch_create_count:
      return Tag(symbol)
    else:
      return Branch(symbol)


class AllBranchRule(StrategyRule):
  """Convert all symbols as branches.

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    else:
      return Branch(symbol)


class AllTagRule(StrategyRule):
  """Convert all symbols as tags.

  We don't worry about conflicts here; they will be caught later by
  SymbolStatistics.check_consistency().

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol):
      return symbol
    else:
      return Tag(symbol)


class HeuristicPreferredParentRule(StrategyRule):
  """Use a heuristic rule to pick preferred parents.

  Pick the parent that should be preferred for any TypedSymbols.  As
  parent, use the symbol that appeared most often as a possible parent
  of the symbol in question.  If multiple symbols are tied, choose the
  one that comes first according to the Symbol class's natural sort
  order."""

  def _get_preferred_parent(self, stats):
    """Return the LODs that are most often possible parents in STATS.

    Return the set of LinesOfDevelopment that appeared most often as
    possible parents.  The return value might contain multiple symbols
    if multiple LinesOfDevelopment appeared the same number of times."""

    best_count = -1
    best_symbol = None
    for (symbol, count) in stats.possible_parents.items():
      if count > best_count or (count == best_count and symbol < best_symbol):
        best_count = count
        best_symbol = symbol

    if best_symbol is None:
      return None
    else:
      return best_symbol

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, TypedSymbol) and symbol.preferred_parent_id is None:
      preferred_parent = self._get_preferred_parent(stats)
      if preferred_parent is None:
        Log().debug('%s has no preferred parent' % (symbol,))
      else:
        symbol.preferred_parent_id = preferred_parent.id
        Log().debug(
            'The preferred parent of %s is %s' % (symbol, preferred_parent,)
            )

    return symbol


class ManualRule(StrategyRule):
  """Use manual symbol configurations read from a file.

  The input file is line-oriented with the following format:

      <project-id> <symbol-name> <conversion> [<parent-lod-name>]

  Where the fields are separated by whitespace and

      project-id -- the numerical id of the Project to which the
          symbol belongs (numbered starting with 0).  This field can
          be '.' if the rule is not project-specific.

      symbol-name -- the name of the symbol being specified.

      conversion -- how the symbol should be treated in the
          conversion.  This is one of the following values: 'branch',
          'tag', or 'exclude'.  This field can be '.' if the rule
          shouldn't affect how the symbol is treated in the
          conversion.

      parent-lod-name -- the name of the LOD that should serve as this
          symbol's parent.  This field can be omitted or '.'  if the
          rule shouldn't affect the symbol's parent, or it can be
          '.trunk.' to indicate that the symbol should sprout from the
          project's trunk."""

  comment_re = re.compile(r'^(\#|$)')

  conversion_map = {
      'branch' : Branch,
      'tag' : Tag,
      'exclude' : ExcludedSymbol,
      '.' : None,
      }

  def __init__(self, filename):
    self._hints = []

    f = open(filename, 'r')
    for l in f:
      s = l.strip()
      if self.comment_re.match(s):
        continue
      fields = s.split()
      if len(fields) == 3:
        [project_id, symbol_name, conversion] = fields
        parent_lod_name = None
      elif len(fields) == 4:
        [project_id, symbol_name, conversion, parent_lod_name] = fields
        if parent_lod_name == '.':
          parent_lod_name = None
      else:
        raise FatalError(
            'The following line in "%s" cannot be parsed:\n    "%s"' % (l,)
            )

      if project_id == '.':
        project_id = None
      else:
        try:
          project_id = int(project_id)
        except ValueError:
          raise FatalError(
              'Illegal project_id in the following line:\n    "%s"' % (l,)
              )

      try:
        conversion = self.conversion_map[conversion]
      except KeyError:
        raise FatalError(
            'Illegal conversion in the following line:\n    "%s"' % (l,)
            )

      self._hints.append(
          (project_id, symbol_name, conversion, parent_lod_name)
          )

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, Trunk):
      return symbol

    for (project_id, name, conversion, parent_lod_name) in self._hints:
      if (project_id is None or project_id == stats.lod.project.id) \
             and (name == stats.lod.name):
        if conversion is not None:
          symbol = conversion(symbol)

        if parent_lod_name is None:
          pass
        elif parent_lod_name == '.trunk.':
          symbol.preferred_parent_id = stats.lod.project.trunk_id
        else:
          # We only have the parent symbol's name; we have to find its
          # id:
          for pp in stats.possible_parents.keys():
            if isinstance(pp, Trunk):
              pass
            elif pp.name == parent_lod_name:
              symbol.preferred_parent_id = pp.id
              break
          else:
            raise FatalError(
                'Symbol named %s not among possible parents'
                % (parent_lod_name,)
                )

    return symbol


