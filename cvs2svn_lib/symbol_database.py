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


from boolean import *
import config
from artifact_manager import artifact_manager


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
    self.tags = { }
    # A hash that maps branch names to lists of the format
    # [ create_count, commit_count, blockers ], where blockers
    # is a hash that lists the symbols that depend on the
    # the branch.  The blockers hash is used as a set, so the
    # values are not used.
    self.branches = { }

  def register_tag_creation(self, name):
    """Register the creation of the tag NAME."""

    self.tags[name] = self.tags.get(name, 0) + 1

  def _branch(self, name):
    """Helper function to get a branch node that will create and
    initialize the node if it does not exist."""

    if not self.branches.has_key(name):
      self.branches[name] = [ 0, 0, { } ]
    return self.branches[name]

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

    return self.branches.has_key(name) and self.branches[name][1]

  def find_excluded_symbols(self, regexp_list):
    """Returns a hash of all symbols that match the regexps in
    REGEXP_LIST.  The hash is used as a set so the values are
    not used."""

    excludes = { }
    for tag in self.tags:
      if match_regexp_list(regexp_list, tag):
        excludes[tag] = None
    for branch in self.branches:
      if match_regexp_list(regexp_list, branch):
        excludes[branch] = None
    return excludes

  def find_branch_exclude_blockers(self, branch, excludes):
    """Find all blockers of BRANCH, excluding the ones in the hash
    EXCLUDES."""

    blockers = { }
    if excludes.has_key(branch):
      for blocker in self.branches[branch][2]:
        if not excludes.has_key(blocker):
          blockers[blocker] = None
    return blockers

  def find_blocked_excludes(self, excludes):
    """Find all branches not in EXCLUDES that have blocking symbols that
    are not themselves excluded.  Return a hash that maps branch names
    to a hash of blockers.  The hash of blockes is used as a set so the
    values are not used."""

    blocked_branches = { }
    for branch in self.branches:
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
    for branch in self.branches:
      if not excludes.has_key(branch) and self.tags.has_key(branch):
        mismatches.append((branch,                    # name
                           self.tags[branch],         # tag count
                           self.branches[branch][0],  # branch count
                           self.branches[branch][1])) # commit count
    return mismatches

  def read(self):
    """Read the symbol database from files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      tag, count = line.split()
      self.tags[tag] = int(count)

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST))
    while 1:
      line = f.readline()
      if not line:
        break
      words = line.split()
      self.branches[words[0]] = [ int(words[1]), int(words[2]), { } ]
      for blocker in words[3:]:
        self.branches[words[0]][2][blocker] = None

  def write(self):
    """Store the symbol database to files."""

    f = open(artifact_manager.get_temp_file(config.TAGS_LIST), "w")
    for tag, count in self.tags.items():
      f.write("%s %d\n" % (tag, count))

    f = open(artifact_manager.get_temp_file(config.BRANCHES_LIST), "w")
    for branch, info in self.branches.items():
      f.write("%s %d %d" % (branch, info[0], info[1]))
      if info[2]:
        f.write(" ")
        f.write(" ".join(info[2].keys()))
      f.write("\n")


