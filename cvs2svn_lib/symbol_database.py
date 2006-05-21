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

"""This module contains database facilities used by cvs2svn."""

import sys

from boolean import *
import config
from common import error_prefix
from context import Ctx
from log import Log
from artifact_manager import artifact_manager
from database import DB_OPEN_NEW
from tags_database import TagsDatabase


def match_regexp_list(regexp_list, s):
  """Test whether string S matches any of the compiled regexps in
  REGEXP_LIST."""

  for regexp in regexp_list:
    if regexp.match(s):
      return True
  return False


class SymbolDatabase:
  """This database records information on all symbols in the RCS
  files.  It is created in pass 1 and it is used in pass 2."""

  def __init__(self):
    # A hash that maps tag names to commit counts
    self._tags = { }
    # A hash that maps branch names to lists of the format
    # [ create_count, commit_count, blockers ], where blockers
    # is a hash that lists the symbols that depend on the
    # the branch.  The blockers hash is used as a set, so the
    # values are not used.
    self._branches = { }

  def register_tag_creation(self, name):
    """Register the creation of the tag NAME."""

    self._tags[name] = self._tags.get(name, 0) + 1

  def _branch(self, name):
    """Helper function to get a branch node that will create and
    initialize the node if it does not exist."""

    if not self._branches.has_key(name):
      self._branches[name] = [ 0, 0, { } ]
    return self._branches[name]

  def register_branch_creation(self, name):
    """Register the creation of the branch NAME."""

    self._branch(name)[0] += 1

  def register_branch_commit(self, name):
    """Register a commit on the branch NAME."""

    self._branch(name)[1] += 1

  def register_branch_blocker(self, name, blocker):
    """Register BLOCKER as a blocker on the branch NAME."""

    self._branch(name)[2][blocker] = None

  def branch_has_commit(self, name):
    """Return non-zero if NAME has commits.  Returns 0 if name
    is not a branch or if it has no commits."""

    return self._branches.has_key(name) and self._branches[name][1]

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

  def find_branch_exclude_blockers(self, branch, excludes):
    """Find all blockers of BRANCH, excluding the ones in the hash
    EXCLUDES."""

    blockers = { }
    if excludes.has_key(branch):
      for blocker in self._branches[branch][2]:
        if not excludes.has_key(blocker):
          blockers[blocker] = None
    return blockers

  def find_blocked_excludes(self, excludes):
    """Find all branches not in EXCLUDES that have blocking symbols that
    are not themselves excluded.  Return a hash that maps branch names
    to a hash of blockers.  The hash of blockes is used as a set so the
    values are not used."""

    blocked_branches = { }
    for branch in self._branches:
      blockers = self.find_branch_exclude_blockers(branch, excludes)
      if blockers:
        blocked_branches[branch] = blockers
    return blocked_branches

  def find_mismatches(self, excludes=None):
    """Find all symbols that are defined as both tags and branches,
    excluding the ones in EXCLUDES.  Returns a list of 4-tuples with
    the symbol name, tag count, branch count and commit count."""

    if excludes is None:
      excludes = { }
    mismatches = [ ]
    for branch in self._branches:
      if not excludes.has_key(branch) and self._tags.has_key(branch):
        mismatches.append((branch,                    # name
                           self._tags[branch],         # tag count
                           self._branches[branch][0],  # branch count
                           self._branches[branch][1])) # commit count
    return mismatches

  def check_blocked_excludes(self, excludes):
    """Check whether any excluded branches are blocked.

    A branch can be blocked because it has another, non-excluded
    symbol that depends on it.  If any blocked excludes are found,
    output error messages describing the situation.  Return True if
    any errors were found."""

    Log().quiet("Checking for blocked exclusions...")

    blocked_excludes = self.find_blocked_excludes(excludes)
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

  def check_invalid_forced_tags(self, excludes):
    """Check for commits on any branches that were forced to be tags.

    In that case, they can't be converted into tags.  If any invalid
    forced tags are found, output error messages describing the
    problems.  Return True iff any errors are found."""

    Log().quiet("Checking for forced tags with commits...")

    invalid_forced_tags = [ ]
    for forced_tag in Ctx().forced_tags:
      if excludes.has_key(forced_tag):
        continue
      if self.branch_has_commit(forced_tag):
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

  def check_symbol_mismatches(self, excludes):
    """Check for symbols that are defined as both tags and branches.

    Exclude the symbols in EXCLUDES.  If any are found, output error
    messages describing the problems.  Return True iff any problems
    are found."""

    Log().quiet("Checking for tag/branch mismatches...")

    mismatches = self.find_mismatches(excludes)

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
      self.check_blocked_excludes(excludes)
      | self.check_invalid_forced_tags(excludes)
      | self.check_symbol_mismatches(excludes)
      )

  def create_tags_database(self):
    # Create the tags database
    tags_db = TagsDatabase(DB_OPEN_NEW)
    for tag in self._tags:
      if tag not in Ctx().forced_branches:
        tags_db.add(tag)
    for tag in Ctx().forced_tags:
      tags_db.add(tag)

  def read(self):
    """Read the symbol database from files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      tag, count = line.split()
      self._tags[tag] = int(count)

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      words = line.split()
      self._branches[words[0]] = [ int(words[1]), int(words[2]), { } ]
      for blocker in words[3:]:
        self._branches[words[0]][2][blocker] = None

  def write(self):
    """Store the symbol database to files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST), "w")
    for tag, count in self._tags.items():
      f.write("%s %d\n" % (tag, count))

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST), "w")
    for branch, info in self._branches.items():
      f.write("%s %d %d" % (branch, info[0], info[1]))
      if info[2]:
        f.write(" ")
        f.write(" ".join(info[2].keys()))
      f.write("\n")


