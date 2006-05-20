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


import os

from boolean import *
from context import Ctx
import common
from common import error_prefix
from common import FatalError


def verify_paths_disjoint(*paths):
  """Verify that all of the paths in the argument list are disjoint.

  If any of the paths is nested in another one (i.e., in the sense
  that 'a/b/c/d' is nested in 'a/b'), or any two paths are identical,
  write an error message and exit."""

  paths = [(path.split('/'), path) for path in paths]
  # If all overlapping elements are equal, a shorter list is
  # considered "less than" a longer one.  Therefore if any paths are
  # nested, this sort will leave at least one such pair adjacent, in
  # the order [nest,nestling].
  paths.sort()
  for i in range(1, len(paths)):
    split_path1, path1 = paths[i - 1]
    split_path2, path2 = paths[i]
    if len(split_path1) <= len(split_path2) \
       and split_path2[:len(split_path1)] == split_path1:
      raise FatalError("paths %s and %s are not disjoint." % (path1, path2,))


def normalize_ttb_path(opt, path):
  """Normalize a path to be used for --trunk, --tags, or --branches.

  1. Strip leading, trailing, and duplicated '/'.
  2. Verify that the path is not empty.

  Return the normalized path.

  If the path is invalid, write an error message and exit."""

  norm_path = common.path_join(*path.split('/'))
  if not norm_path:
    raise FatalError("cannot pass an empty path to %s." % (opt,))
  return norm_path


class Project:
  """A project within a CVS repository."""

  def __init__(self, project_cvs_repos_path,
               trunk_path, branches_path, tags_path):
    """Create a new Project record.

    PROJECT_CVS_REPOS_PATH is the main CVS directory for this project
    (within the filesystem).  TRUNK_PATH, BRANCHES_PATH, and TAGS_PATH
    are the full, normalized directory names in svn for the
    corresponding part of the repository."""

    self.project_cvs_repos_path = project_cvs_repos_path
    prefix = Ctx().cvs_repository.cvs_repos_path
    if not self.project_cvs_repos_path.startswith(prefix):
      raise FatalError("Project '%s' must start with '%s'"
                       % (self.project_cvs_repos_path, prefix,))
    # The project's main directory as a cvs_path:
    self.project_cvs_path = self.project_cvs_repos_path[len(prefix):]
    if self.project_cvs_path.startswith(os.sep):
      self.project_cvs_path = self.project_cvs_path[1:]
    self.trunk_path = trunk_path
    self.branches_path = branches_path
    self.tags_path = tags_path
    verify_paths_disjoint(self.trunk_path, self.branches_path,
                          self.tags_path)

  def is_source(self, svn_path):
    """Return True iff SVN_PATH is a legitimate source for this project.

    Legitimate paths are self.trunk_path or any directory directly
    under self.branches_path."""

    if svn_path == self.trunk_path:
      return True

    (head, tail,) = common.path_split(svn_path)
    if head == self.branches_path:
      return True

    return False

  def is_unremovable(self, svn_path):
    """Return True iff the specified path must not be removed."""

    return svn_path in [self.trunk_path, self.branches_path, self.tags_path]

  def get_branch_path(self, branch_name):
    """Return the svnpath for the branch named BRANCH_NAME."""

    return common.path_join(self.branches_path,
                            common.clean_symbolic_name(branch_name))

  def get_tag_path(self, tag_name):
    """Return the svnpath for the tag named TAG_NAME."""

    return common.path_join(self.tags_path,
                            common.clean_symbolic_name(tag_name))

  def _relative_name(self, cvs_path):
    """Convert CVS_PATH into a name relative to this project's root directory.

    CVS_PATH has to begin (textually) with self.project_cvs_path.
    Remove prefix and optional '/'."""

    if not cvs_path.startswith(self.project_cvs_path):
      raise FatalError(
          "_relative_name: '%s' is not a sub-path of '%s'"
          % (cvs_path, self.project_cvs_path,))
    l = len(self.project_cvs_path)
    if cvs_path[l] == os.sep:
      l += 1
    return cvs_path[l:]

  def make_trunk_path(self, cvs_path):
    """Return the trunk path for CVS_PATH.

    Return the svn path for this file on trunk."""

    return common.path_join(self.trunk_path, self._relative_name(cvs_path))

  def make_branch_path(self, branch_name, cvs_path):
    """Return the svn path for CVS_PATH on branch BRANCH_NAME."""

    return common.path_join(self.get_branch_path(branch_name),
                            self._relative_name(cvs_path))


