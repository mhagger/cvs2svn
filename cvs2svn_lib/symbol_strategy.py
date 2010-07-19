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

"""SymbolStrategy classes determine how to convert symbols."""

import re

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import normalize_svn_path
from cvs2svn_lib.log import logger
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import TypedSymbol
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.symbol_statistics import SymbolPlanError


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

    SYMBOL holds a Trunk or Symbol object as it has been determined so
    far.  Hopefully one of these method calls will turn any naked
    Symbol instances into TypedSymbols.

    If this rule applies to the SYMBOL (whose statistics are collected
    in STATS), then return a new or modified AbstractSymbol object.
    If this rule doesn't apply, return SYMBOL unchanged."""

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

  def log(self, symbol):
    raise NotImplementedError()

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    elif self.regexp.match(symbol.name):
      self.log(symbol)
      return self.action(symbol)
    else:
      return symbol


class ForceBranchRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be branches."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, Branch)

  def log(self, symbol):
    logger.verbose(
        'Converting symbol %s as a branch because it matches regexp "%s".'
        % (symbol, self.regexp.pattern,)
        )


class ForceTagRegexpStrategyRule(_RegexpStrategyRule):
  """Force symbols matching pattern to be tags."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, Tag)

  def log(self, symbol):
    logger.verbose(
        'Converting symbol %s as a tag because it matches regexp "%s".'
        % (symbol, self.regexp.pattern,)
        )


class ExcludeRegexpStrategyRule(_RegexpStrategyRule):
  """Exclude symbols matching pattern."""

  def __init__(self, pattern):
    _RegexpStrategyRule.__init__(self, pattern, ExcludedSymbol)

  def log(self, symbol):
    logger.verbose(
        'Excluding symbol %s because it matches regexp "%s".'
        % (symbol, self.regexp.pattern,)
        )


class ExcludeTrivialImportBranchRule(StrategyRule):
  """If a symbol is a trivial import branch, exclude it.

  A trivial import branch is defined to be a branch that only had a
  single import on it (no other kinds of commits) in every file in
  which it appeared.  In most cases these branches are worthless."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    if stats.tag_create_count == 0 \
          and stats.branch_create_count == stats.trivial_import_count:
      logger.verbose(
          'Excluding branch %s because it is a trivial import branch.'
          % (symbol,)
          )
      return ExcludedSymbol(symbol)
    else:
      return symbol


class ExcludeVendorBranchRule(StrategyRule):
  """If a symbol is a pure vendor branch, exclude it.

  A pure vendor branch is defined to be a branch that only had imports
  on it (no other kinds of commits) in every file in which it
  appeared."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    if stats.tag_create_count == 0 \
          and stats.branch_create_count == stats.pure_ntdb_count:
      logger.verbose(
          'Excluding branch %s because it is a pure vendor branch.'
          % (symbol,)
          )
      return ExcludedSymbol(symbol)
    else:
      return symbol


class UnambiguousUsageRule(StrategyRule):
  """If a symbol is used unambiguously as a tag/branch, convert it as such."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    is_tag = stats.tag_create_count > 0
    is_branch = stats.branch_create_count > 0 or stats.branch_commit_count > 0
    if is_tag and is_branch:
      # Can't decide
      return symbol
    elif is_branch:
      logger.verbose(
          'Converting symbol %s as a branch because it is always used '
          'as a branch.'
          % (symbol,)
          )
      return Branch(symbol)
    elif is_tag:
      logger.verbose(
          'Converting symbol %s as a tag because it is always used '
          'as a tag.'
          % (symbol,)
          )
      return Tag(symbol)
    else:
      # The symbol didn't appear at all:
      return symbol


class BranchIfCommitsRule(StrategyRule):
  """If there was ever a commit on the symbol, convert it as a branch."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    elif stats.branch_commit_count > 0:
      logger.verbose(
          'Converting symbol %s as a branch because there are commits on it.'
          % (symbol,)
          )
      return Branch(symbol)
    else:
      return symbol


class HeuristicStrategyRule(StrategyRule):
  """Convert symbol based on how often it was used as a branch/tag.

  Whichever happened more often determines how the symbol is
  converted."""

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    elif stats.tag_create_count >= stats.branch_create_count:
      logger.verbose(
          'Converting symbol %s as a tag because it is more often used '
          'as a tag.'
          % (symbol,)
          )
      return Tag(symbol)
    else:
      logger.verbose(
          'Converting symbol %s as a branch because it is more often used '
          'as a branch.'
          % (symbol,)
          )
      return Branch(symbol)


class _CatchAllRule(StrategyRule):
  """Base class for catch-all rules.

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def __init__(self, action):
    self._action = action

  def log(self, symbol):
    raise NotImplementedError()

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, (Trunk, TypedSymbol)):
      return symbol
    else:
      self.log(symbol)
      return self._action(symbol)


class AllBranchRule(_CatchAllRule):
  """Convert all symbols as branches.

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def __init__(self):
    _CatchAllRule.__init__(self, Branch)

  def log(self, symbol):
    logger.verbose(
        'Converting symbol %s as a branch because no other rules applied.'
        % (symbol,)
        )


class AllTagRule(_CatchAllRule):
  """Convert all symbols as tags.

  We don't worry about conflicts here; they will be caught later by
  SymbolStatistics.check_consistency().

  Usually this rule will appear after a list of more careful rules
  (including a general rule like UnambiguousUsageRule) and will
  therefore only apply to the symbols not handled earlier."""

  def __init__(self):
    _CatchAllRule.__init__(self, Tag)

  def log(self, symbol):
    logger.verbose(
        'Converting symbol %s as a tag because no other rules applied.'
        % (symbol,)
        )


class AllExcludedRule(_CatchAllRule):
  """Exclude all symbols.

  Usually this rule will appear after a list of more careful rules
  (including a SymbolHintsFileRule or several ManualSymbolRules)
  and will therefore only apply to the symbols not handled earlier."""

  def __init__(self):
    _CatchAllRule.__init__(self, ExcludedSymbol)

  def log(self, symbol):
    logger.verbose(
        'Excluding symbol %s by catch-all rule.' % (symbol,)
        )


class TrunkPathRule(StrategyRule):
  """Set the base path for Trunk."""

  def __init__(self, trunk_path):
    self.trunk_path = trunk_path

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, Trunk) and symbol.base_path is None:
      symbol.base_path = self.trunk_path

    return symbol


class SymbolPathRule(StrategyRule):
  """Set the base paths for symbol LODs."""

  def __init__(self, symbol_type, base_path):
    self.symbol_type = symbol_type
    self.base_path = base_path

  def get_symbol(self, symbol, stats):
    if isinstance(symbol, self.symbol_type) and symbol.base_path is None:
      symbol.base_path = path_join(self.base_path, symbol.name)

    return symbol


class BranchesPathRule(SymbolPathRule):
  """Set the base paths for Branch LODs."""

  def __init__(self, branch_path):
    SymbolPathRule.__init__(self, Branch, branch_path)


class TagsPathRule(SymbolPathRule):
  """Set the base paths for Tag LODs."""

  def __init__(self, tag_path):
    SymbolPathRule.__init__(self, Tag, tag_path)


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
        logger.verbose('%s has no preferred parent' % (symbol,))
      else:
        symbol.preferred_parent_id = preferred_parent.id
        logger.verbose(
            'The preferred parent of %s is %s' % (symbol, preferred_parent,)
            )

    return symbol


class ManualTrunkRule(StrategyRule):
  """Change the SVN path of Trunk LODs.

  Members:

    project_id -- (int or None) The id of the project whose trunk
        should be affected by this rule.  If project_id is None, then
        the rule is not project-specific.

    svn_path -- (str) The SVN path that should be used as the base
        directory for this trunk.  This member must not be None,
        though it may be the empty string for a single-project,
        trunk-only conversion.

  """

  def __init__(self, project_id, svn_path):
    self.project_id = project_id
    self.svn_path = normalize_svn_path(svn_path, allow_empty=True)

  def get_symbol(self, symbol, stats):
    if (self.project_id is not None
        and self.project_id != stats.lod.project.id):
      return symbol

    if isinstance(symbol, Trunk):
      symbol.base_path = self.svn_path

    return symbol


def convert_as_branch(symbol):
  logger.verbose(
      'Converting symbol %s as a branch because of manual setting.'
      % (symbol,)
      )
  return Branch(symbol)


def convert_as_tag(symbol):
  logger.verbose(
      'Converting symbol %s as a tag because of manual setting.'
      % (symbol,)
      )
  return Tag(symbol)


def exclude(symbol):
  logger.verbose(
      'Excluding symbol %s because of manual setting.'
      % (symbol,)
      )
  return ExcludedSymbol(symbol)


class ManualSymbolRule(StrategyRule):
  """Change how particular symbols are converted.

  Members:

    project_id -- (int or None) The id of the project whose trunk
        should be affected by this rule.  If project_id is None, then
        the rule is not project-specific.

    symbol_name -- (str) The name of the symbol that should be
        affected by this rule.

    conversion -- (callable or None) A callable that converts the
        symbol to its preferred output type.  This should normally be
        one of (convert_as_branch, convert_as_tag, exclude).  If this
        member is None, then this rule does not affect the symbol's
        output type.

    svn_path -- (str) The SVN path that should be used as the base
        directory for this trunk.  This member must not be None,
        though it may be the empty string for a single-project,
        trunk-only conversion.

    parent_lod_name -- (str or None) The name of the line of
        development that should be preferred as the parent of this
        symbol.  (The preferred parent is the line of development from
        which the symbol should sprout.)  If this member is set to the
        string '.trunk.', then the symbol will be set to sprout
        directly from trunk.  If this member is set to None, then this
        rule won't affect the symbol's parent.

  """

  def __init__(
        self, project_id, symbol_name, conversion, svn_path, parent_lod_name
        ):
    self.project_id = project_id
    self.symbol_name = symbol_name
    self.conversion = conversion
    if svn_path is None:
      self.svn_path = None
    else:
      self.svn_path = normalize_svn_path(svn_path, allow_empty=True)
    self.parent_lod_name = parent_lod_name

  def _get_parent_by_id(self, parent_lod_name, stats):
    """Return the LOD object for the parent with name PARENT_LOD_NAME.

    STATS is the _Stats object describing a symbol whose parent needs
    to be determined from its name.  If none of its possible parents
    has name PARENT_LOD_NAME, raise a SymbolPlanError."""

    for pp in stats.possible_parents.keys():
      if isinstance(pp, Trunk):
        pass
      elif pp.name == parent_lod_name:
        return pp
    else:
      parent_counts = stats.possible_parents.items()
      parent_counts.sort(lambda a,b: - cmp(a[1], b[1]))
      lines = [
          '%s is not a valid parent for %s;'
              % (parent_lod_name, stats.lod,),
          '    possible parents (with counts):'
          ]
      for (symbol, count) in parent_counts:
        if isinstance(symbol, Trunk):
          lines.append('        .trunk. : %d' % count)
        else:
          lines.append('        %s : %d' % (symbol.name, count))
      raise SymbolPlanError('\n'.join(lines))

  def get_symbol(self, symbol, stats):
    if (self.project_id is not None
        and self.project_id != stats.lod.project.id):
      return symbol

    elif isinstance(symbol, Trunk):
      return symbol

    elif self.symbol_name == stats.lod.name:
      if self.conversion is not None:
        symbol = self.conversion(symbol)

      if self.parent_lod_name is None:
        pass
      elif self.parent_lod_name == '.trunk.':
        symbol.preferred_parent_id = stats.lod.project.trunk_id
      else:
        symbol.preferred_parent_id = self._get_parent_by_id(
            self.parent_lod_name, stats
            ).id

      if self.svn_path is not None:
        symbol.base_path = self.svn_path

    return symbol


class SymbolHintsFileRule(StrategyRule):
  """Use manual symbol configurations read from a file.

  The input file is line-oriented with the following format:

      <project-id> <symbol-name> <conversion> [<svn-path> [<parent-lod-name>]]

  Where the fields are separated by whitespace and

      project-id -- the numerical id of the Project to which the
          symbol belongs (numbered starting with 0).  This field can
          be '.' if the rule is not project-specific.

      symbol-name -- the name of the symbol being specified, or
          '.trunk.' if the rule should apply to trunk.

      conversion -- how the symbol should be treated in the
          conversion.  This is one of the following values: 'branch',
          'tag', or 'exclude'.  This field can be '.' if the rule
          shouldn't affect how the symbol is treated in the
          conversion.

      svn-path -- the SVN path that should serve as the root path of
          this LOD.  The path should be expressed as a path relative
          to the SVN root directory, with or without a leading '/'.
          This field can be omitted or '.' if the rule shouldn't
          affect the LOD's SVN path.

      parent-lod-name -- the name of the LOD that should serve as this
          symbol's parent.  This field can be omitted or '.'  if the
          rule shouldn't affect the symbol's parent, or it can be
          '.trunk.' to indicate that the symbol should sprout from the
          project's trunk."""

  comment_re = re.compile(r'^(\#|$)')

  conversion_map = {
      'branch' : convert_as_branch,
      'tag' : convert_as_tag,
      'exclude' : exclude,
      '.' : None,
      }

  def __init__(self, filename):
    self.filename = filename

  def start(self, symbol_statistics):
    self._rules = []

    f = open(self.filename, 'r')
    for l in f:
      l = l.rstrip()
      s = l.lstrip()
      if self.comment_re.match(s):
        continue
      fields = s.split()

      if len(fields) < 3:
        raise FatalError(
            'The following line in "%s" cannot be parsed:\n    "%s"'
            % (self.filename, l,)
            )

      project_id = fields.pop(0)
      symbol_name = fields.pop(0)
      conversion = fields.pop(0)

      if fields:
        svn_path = fields.pop(0)
        if svn_path == '.':
          svn_path = None
        elif svn_path[0] == '/':
          svn_path = svn_path[1:]
      else:
        svn_path = None

      if fields:
        parent_lod_name = fields.pop(0)
      else:
        parent_lod_name = '.'

      if fields:
        raise FatalError(
            'The following line in "%s" cannot be parsed:\n    "%s"'
            % (self.filename, l,)
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

      if symbol_name == '.trunk.':
        if conversion not in ['.', 'trunk']:
          raise FatalError('Trunk cannot be converted as a different type')

        if parent_lod_name != '.':
          raise FatalError('Trunk\'s parent cannot be set')

        if svn_path is None:
          # This rule doesn't do anything:
          pass
        else:
          self._rules.append(ManualTrunkRule(project_id, svn_path))

      else:
        try:
          conversion = self.conversion_map[conversion]
        except KeyError:
          raise FatalError(
              'Illegal conversion in the following line:\n    "%s"' % (l,)
              )

        if parent_lod_name == '.':
          parent_lod_name = None

        if conversion is None \
               and svn_path is None \
               and parent_lod_name is None:
          # There is nothing to be done:
          pass
        else:
          self._rules.append(
              ManualSymbolRule(
                  project_id, symbol_name,
                  conversion, svn_path, parent_lod_name
                  )
              )

    for rule in self._rules:
      rule.start(symbol_statistics)

  def get_symbol(self, symbol, stats):
    for rule in self._rules:
      symbol = rule.get_symbol(symbol, stats)

    return symbol

  def finish(self):
    for rule in self._rules:
      rule.finish()

    del self._rules


