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


class _Tag:
  def __init__(self, id, name, create_count=0):
    self.id = id
    self.name = name
    self.create_count = create_count


class _Branch:
  """A summary of information about a branch.

  Members:

    create_count -- the number of files on which this branches is created

    commit_count -- the number of commits on this branch

    blockers -- a set { symbol : None } of the symbols that depend on
        the the branch.  The set is stored as a map whose values are
        not used."""

  def __init__(self, id, name, create_count=0, commit_count=0, blockers=[]):
    self.id = id
    self.name = name
    self.create_count = create_count
    self.commit_count = commit_count
    self.blockers = {}
    for blocker in blockers:
      self.blockers[blocker] = None


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

  The data contained in this class can be written to text files
  (config.TAGS_LIST and config.BRANCHES_LIST) and re-read."""

  def __init__(self):
    # A hash that maps tag names to _Tag instances
    self._tags = { }

    # A hash that maps branch names to _Branch instances
    self._branches = { }

    # A map { id -> record } for all symbols (branches and tags)
    self._symbols = { }

    self._key_generator = KeyGenerator(1)

  def register_tag_creation(self, name):
    """Register the creation of the tag NAME.

    Return the tag record's id."""

    tag = self._tags.get(name)
    if tag is None:
      tag = _Tag(self._key_generator.gen_id(), name)
      self._tags[name] = tag
      self._symbols[tag.id] = tag
    tag.create_count += 1
    return tag.id

  def _branch(self, name):
    """Helper function to get a branch node that will create and
    initialize the node if it does not exist."""

    branch = self._branches.get(name)
    if branch is None:
      branch = _Branch(self._key_generator.gen_id(), name)
      self._branches[name] = branch
      self._symbols[branch.id] = branch
    return branch

  def register_branch_creation(self, name):
    """Register the creation of the branch NAME.

    Return the branch record's id."""

    branch = self._branch(name)
    branch.create_count += 1
    return branch.id

  def register_branch_commit(self, name):
    """Register a commit on the branch NAME."""

    self._branch(name).commit_count += 1

  def register_branch_blocker(self, name, blocker):
    """Register BLOCKER as a blocker on the branch NAME."""

    self._branch(name).blockers[blocker] = None

  def _branch_has_commit(self, name):
    """Return True iff NAME has commits.  Returns False if name is not
    a branch or if it has no commits."""

    branch = self._branches.get(name)
    return branch and branch.commit_count > 0

  def find_excluded_symbols(self, regexp_list):
    """Returns a hash of all symbols that match the regexps in
    REGEXP_LIST.  The hash is used as a set so the values are
    not used."""

    excludes = { }
    for tag in self._tags:
      if match_regexp_list(regexp_list, tag):
        excludes[tag] = None
    for branch in self._branches:
      if match_regexp_list(regexp_list, branch):
        excludes[branch] = None
    return excludes

  def _find_branch_exclude_blockers(self, branch, excludes):
    """Find all blockers of BRANCH, excluding the ones in the hash
    EXCLUDES."""

    blockers = { }
    if branch in excludes:
      for blocker in self._branches[branch].blockers:
        if blocker not in excludes:
          blockers[blocker] = None
    return blockers

  def _find_blocked_excludes(self, excludes):
    """Find all branches not in EXCLUDES that have blocking symbols that
    are not themselves excluded.  Return a hash that maps branch names
    to a hash of blockers.  The hash of blockes is used as a set so the
    values are not used."""

    blocked_branches = { }
    for branch in self._branches:
      blockers = self._find_branch_exclude_blockers(branch, excludes)
      if blockers:
        blocked_branches[branch] = blockers
    return blocked_branches

  def _find_mismatches(self, excludes=None):
    """Find all symbols that are defined as both tags and branches,
    excluding the ones in EXCLUDES.  Returns a list of 4-tuples with
    the symbol name, tag count, branch count and commit count."""

    if excludes is None:
      excludes = { }
    mismatches = [ ]
    for branch in self._branches:
      if branch not in excludes and branch in self._tags:
        mismatches.append((branch,
                           self._tags[branch].create_count,
                           self._branches[branch].create_count,
                           self._branches[branch].commit_count))
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

    for branch, blockers in blocked_excludes.items():
      sys.stderr.write(error_prefix + ": The branch '%s' cannot be "
                       "excluded because the following symbols depend "
                       "on it:\n" % (branch))
      for blocker in blockers:
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

    sys.stderr.write(error_prefix + ": The following symbols are tags "
                     "in some files and branches in others.\nUse "
                     "--force-tag, --force-branch and/or --exclude to "
                     "resolve the symbols.\n")
    for name, tag_count, branch_count, commit_count in mismatches:
      sys.stderr.write("    '%s' is a tag in %d files, a branch in "
                       "%d files and has commits in %d files.\n"
                       % (name, tag_count, branch_count, commit_count))

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
    for symbol in self._tags.values():
      if symbol.name in Ctx().forced_branches:
        symbol_db.add(BranchSymbol(symbol.id, symbol.name))
      else:
        symbol_db.add(TagSymbol(symbol.id, symbol.name))
    for symbol in self._branches.values():
      if symbol.name in Ctx().forced_tags:
        symbol_db.add(TagSymbol(symbol.id, symbol.name))
      else:
        symbol_db.add(BranchSymbol(symbol.id, symbol.name))

  def read(self):
    """Read the symbol database from files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      id, name, create_count = line.split()
      id = int(id)
      create_count = int(create_count)
      tag = _Tag(id, name, create_count)
      self._tags[name] = tag
      self._symbols[tag.id] = tag

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      words = line.split()
      [id, name, create_count, commit_count] = words[:4]
      blockers = words[4:]
      id = int(id)
      create_count = int(create_count)
      commit_count = int(commit_count)
      branch = _Branch(id, name, create_count, commit_count, blockers)
      self._branches[name] = branch
      self._symbols[branch.id] = branch

  def write(self):
    """Store the symbol database to files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST), "w")
    for tag in self._tags.values():
      f.write("%d %s %d\n" % (tag.id, tag.name, tag.create_count))
    f.close()

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST), "w")
    for branch in self._branches.values():
      f.write(
          "%d %s %d %d"
          % (branch.id, branch.name, branch.create_count, branch.commit_count)
          )
      if branch.blockers:
        f.write(' ')
        f.write(' '.join(branch.blockers.keys()))
      f.write('\n')
    f.close()


