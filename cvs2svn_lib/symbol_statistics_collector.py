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

"""This module contains a class that gathers statistics about symbols."""

import sys

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import DB_OPEN_NEW
from cvs2svn_lib.symbol_database import BranchSymbol
from cvs2svn_lib.symbol_database import TagSymbol
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.key_generator import KeyGenerator


def match_regexp_list(regexp_list, s):
  """Test whether string S matches any of the compiled regexps in
  REGEXP_LIST."""

  for regexp in regexp_list:
    if regexp.match(s):
      return True
  return False


class _Symbol:
  """A summary of information about a branch.

  Members:
    id -- a unique id (integer)

    name -- the name of the symbol

    tag_create_count -- the number of files on which this symbol
        appears as a tag

    branch_create_count -- the number of files on which this symbol
        appears as a branch

    branch_commit_count -- the number of commits on this branch

    branch_blockers -- a set of the symbols that depend on the branch."""

  def __init__(self, id, name, tag_create_count=0,
               branch_create_count=0, branch_commit_count=0,
               branch_blockers=[]):
    self.id = id
    self.name = name
    self.tag_create_count = tag_create_count
    self.branch_create_count = branch_create_count
    self.branch_commit_count = branch_commit_count
    self.branch_blockers = set(branch_blockers)


class SymbolStatisticsCollector:
  """This database records a brief summary of information about all
  symbols in the RCS files.  It is created in CollectRevsPass (pass1)
  and it is used in ResyncRevsPass (pass2).

  collect_data._SymbolDataCollector inserts information into instances
  of this class by by calling its register_*() methods.

  Its main purpose is to assist in the decisions about:

  1. What tags and branches should be processed/excluded

  2. What tags should be forced to be branches and vice versa (this
     class maintains some statistics to help the user decide)

  3. Are there inconsistencies?

     - A symbol that is sometimes a branch and sometimes a tag

     - A forced branch with commit(s) on it

     - A non-excluded branch depends on an excluded branch

  The data contained in this class can be written to and read from a
  text file (config.SYMBOL_STATISTICS_LIST)."""

  def __init__(self):
    # A hash that maps symbol names to _Symbol instances
    self._symbols_by_name = { }

    # A map { id -> record } for all symbols (branches and tags)
    self._symbols = { }

    self._key_generator = KeyGenerator(1)

  def _get_symbol(self, name):
    """Return the _Symbol record for NAME, creating a new one if necessary."""

    try:
      return self._symbols_by_name[name]
    except KeyError:
      symbol = _Symbol(self._key_generator.gen_id(), name)
      self._symbols_by_name[name] = symbol
      self._symbols[symbol.id] = symbol
      return symbol

  def register_tag_creation(self, name):
    """Register the creation of the tag NAME.

    Return the tag record's id."""

    symbol = self._get_symbol(name)
    symbol.tag_create_count += 1
    return symbol.id

  def register_branch_creation(self, name):
    """Register the creation of the branch NAME.

    Return the branch record's id."""

    symbol = self._get_symbol(name)
    symbol.branch_create_count += 1
    return symbol.id

  def register_branch_commit(self, name):
    """Register a commit on the branch NAME."""

    self._get_symbol(name).branch_commit_count += 1

  def register_branch_blocker(self, name, blocker):
    """Register BLOCKER as a blocker on the branch NAME."""

    self._get_symbol(name).branch_blockers.add(blocker)

  def _branch_has_commit(self, name):
    """Return True iff NAME has commits.  Returns False if NAME was
    never seen as a branch or if it has no commits."""

    symbol = self._symbols_by_name.get(name)
    return (symbol
            and symbol.branch_create_count > 0
            and symbol.branch_commit_count > 0)

  def find_excluded_symbols(self, regexp_list):
    """Returns a hash of all symbols that match the regexps in
    REGEXP_LIST.  The hash is used as a set so the values are
    not used."""

    excludes = { }
    for symbol in self._symbols.values():
      if match_regexp_list(regexp_list, symbol.name):
        excludes[symbol.name] = None
    return excludes

  def _find_branch_exclude_blockers(self, symbol, excludes):
    """Find all blockers of SYMBOL, excluding the ones in the hash
    EXCLUDES."""

    branch_blockers = { }
    if symbol in excludes:
      for blocker in self._symbols_by_name[symbol].branch_blockers:
        if blocker not in excludes:
          branch_blockers[blocker] = None
    return branch_blockers

  def _find_blocked_excludes(self, excludes):
    """Find all branches not in EXCLUDES that have blocking symbols
    that are not themselves excluded.  Return a hash that maps branch
    names to a hash of branch_blockers.  The hash of blockers is used
    as a set so the values are not used."""

    blocked_branches = { }
    for symbol in self._symbols_by_name:
      branch_blockers = self._find_branch_exclude_blockers(symbol, excludes)
      if branch_blockers:
        blocked_branches[symbol] = branch_blockers
    return blocked_branches

  def _find_mismatches(self, excludes=None):
    """Find all symbols that are defined as both tags and branches,
    excluding the ones in EXCLUDES.  Returns a list of 4-tuples with
    the symbol name, tag count, branch count and commit count."""

    if excludes is None:
      excludes = { }
    mismatches = [ ]
    for symbol in self._symbols.values():
      if (symbol.name not in excludes
          and symbol.tag_create_count > 0
          and symbol.branch_create_count > 0):
        mismatches.append((symbol.name,
                           symbol.tag_create_count,
                           symbol.branch_create_count,
                           symbol.branch_commit_count))
    return mismatches

  def _check_blocked_excludes(self, excludes):
    """Check whether any excluded branches are blocked.

    A branch can be blocked because it has another, non-excluded
    symbol that depends on it.  If any blocked excludes are found,
    output error messages describing the situation.  Return True if
    any errors were found."""

    Log().quiet("Checking for blocked exclusions...")

    blocked_excludes = self._find_blocked_excludes(excludes)
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

  def _check_invalid_forced_tags(self, excludes):
    """Check for commits on any branches that were forced to be tags.

    In that case, they can't be converted into tags.  If any invalid
    forced tags are found, output error messages describing the
    problems.  Return True iff any errors are found."""

    Log().quiet("Checking for forced tags with commits...")

    invalid_forced_tags = [ ]
    for forced_tag in Ctx().forced_tags:
      if forced_tag in excludes:
        continue
      if self._branch_has_commit(forced_tag):
        invalid_forced_tags.append(forced_tag)

    if not invalid_forced_tags:
      # No problems found:
      return False

    sys.stderr.write(error_prefix + ": The following branches cannot be "
                     "forced to be tags because they have commits:\n")
    for tag in invalid_forced_tags:
      sys.stderr.write("    '%s'\n" % (tag))
    sys.stderr.write("\n")

    return True

  def _check_symbol_mismatches(self, excludes):
    """Check for symbols that are defined as both tags and branches.

    Exclude the symbols in EXCLUDES.  If any are found, output error
    messages describing the problems.  Return True iff any problems
    are found."""

    Log().quiet("Checking for tag/branch mismatches...")

    mismatches = self._find_mismatches(excludes)

    def is_not_forced(mismatch):
      name = mismatch[0]
      return not (name in Ctx().forced_tags or name in Ctx().forced_branches)

    mismatches = filter(is_not_forced, mismatches)
    if not mismatches:
      # No problems found:
      return False

    sys.stderr.write(
        error_prefix + ": The following symbols are tags in some files and "
        "branches in others.\n"
        "Use --force-tag, --force-branch and/or --exclude to resolve the "
        "symbols.\n")
    for name, tag_count, branch_count, branch_commit_count in mismatches:
      sys.stderr.write("    '%s' is a tag in %d files, a branch in "
                       "%d files and has commits in %d files.\n"
                       % (name, tag_count, branch_count, branch_commit_count))

    return True

  def check_consistency(self, excludes):
    """Check the non-excluded symbols for consistency.  Return True
    iff any problems were detected."""

    # It is important that we not short-circuit here:
    return (
      self._check_blocked_excludes(excludes)
      | self._check_invalid_forced_tags(excludes)
      | self._check_symbol_mismatches(excludes)
      )

  def create_symbol_database(self):
    # Create the tags database
    symbol_db = SymbolDatabase(DB_OPEN_NEW)
    for symbol in self._symbols.values():
      if symbol.name in Ctx().forced_branches:
        symbol_db.add(BranchSymbol(symbol.id, symbol.name))
      elif symbol.name in Ctx().forced_tags:
        symbol_db.add(TagSymbol(symbol.id, symbol.name))
      elif symbol.branch_create_count > 0:
        symbol_db.add(BranchSymbol(symbol.id, symbol.name))
      else:
        symbol_db.add(TagSymbol(symbol.id, symbol.name))

  def read(self):
    """Read the symbol database from files."""

    f = open(artifact_manager.get_temp_file(config.SYMBOL_STATISTICS_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      words = line.split()
      [id, name, tag_create_count,
       branch_create_count, branch_commit_count] = words[:5]
      branch_blockers = words[5:]
      id = int(id)
      tag_create_count = int(tag_create_count)
      branch_create_count = int(branch_create_count)
      branch_commit_count = int(branch_commit_count)
      symbol = _Symbol(
          id, name, tag_create_count,
          branch_create_count, branch_commit_count, branch_blockers)
      self._symbols_by_name[name] = symbol
      self._symbols[symbol.id] = symbol

  def write(self):
    """Store the symbol database to file."""

    f = open(artifact_manager.get_temp_file(config.SYMBOL_STATISTICS_LIST),
             "w")
    for symbol in self._symbols.values():
      f.write(
          "%d %s %d %d %d"
          % (symbol.id, symbol.name, symbol.tag_create_count,
             symbol.branch_create_count, symbol.branch_commit_count)
          )
      if symbol.branch_blockers:
        f.write(' ')
        f.write(' '.join(list(symbol.branch_blockers)))
      f.write('\n')
    f.close()


