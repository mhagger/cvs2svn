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

  def __init__(self):
    """Initialize an instance."""

    # A list of regexps matching the names of symbols that should be
    # excluded from the conversion.
    self.excludes = []

    # A list of regexps matching symbols that should be converted as
    # branches.
    self.forced_branches = []

    # A list of regexps matching symbols that should be converted as
    # tags.
    self.forced_tags = []

  def _compile_re(self, pattern):
    try:
      return re.compile('^' + pattern + '$')
    except re.error, e:
      raise FatalError("'%s' is not a valid regexp." % (value,))

  def add_exclude(self, pattern):
    self.excludes.append(self._compile_re(pattern))

  def add_forced_branch(self, pattern):
    self.forced_branches.append(self._compile_re(pattern))

  def add_forced_tag(self, pattern):
    self.forced_tags.append(self._compile_re(pattern))

  def get_symbols(self, symbol_stats):
    symbols = {}
    mismatches = []
    for stats in symbol_stats:
      if match_regexp_list(self.excludes, stats.name):
        # Don't write it to the database at all.
        pass
      elif match_regexp_list(self.forced_branches, stats.name):
        symbols[stats.name] = BranchSymbol(stats.id, stats.name)
      elif match_regexp_list(self.forced_tags, stats.name):
        symbols[stats.name] = TagSymbol(stats.id, stats.name)
      else:
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
      return None
    else:
      return symbols


