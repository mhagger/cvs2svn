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


import re
import os
import stat

from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.cvs_file import CVSFile


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

  norm_path = path_join(*path.split('/'))
  if not norm_path:
    raise FatalError("cannot pass an empty path to %s." % (opt,))
  return norm_path


class Project(object):
  """A project within a CVS repository."""

  def __init__(self, project_cvs_repos_path,
               trunk_path, branches_path, tags_path,
               symbol_transforms=None):
    """Create a new Project record.

    PROJECT_CVS_REPOS_PATH is the main CVS directory for this project
    (within the filesystem).  TRUNK_PATH, BRANCHES_PATH, and TAGS_PATH
    are the full, normalized directory names in svn for the
    corresponding part of the repository.

    SYMBOL_TRANSFORMS is a list of SymbolTransform instances which
    will be used to transform any symbol names within this project."""

    # A unique id for this project, also used as its index in
    # Ctx().projects.  This field is filled in by Ctx.add_project().
    self.id = None

    self.project_cvs_repos_path = os.path.normpath(project_cvs_repos_path)
    if not os.path.isdir(self.project_cvs_repos_path):
      raise FatalError("The specified CVS repository path '%s' is not an "
                       "existing directory." % self.project_cvs_repos_path)

    self.cvs_repository_root, self.cvs_module = \
        self.determine_repository_root(
            os.path.abspath(self.project_cvs_repos_path))

    # A regexp matching project_cvs_repos_path plus an optional separator:
    self.project_prefix_re = re.compile(
        r'^' + re.escape(self.project_cvs_repos_path)
        + r'(' + re.escape(os.sep) + r'|$)')
    self.trunk_path = normalize_ttb_path('--trunk', trunk_path)
    self.branches_path = normalize_ttb_path('--branches', branches_path)
    self.tags_path = normalize_ttb_path('--tags', tags_path)
    verify_paths_disjoint(self.trunk_path, self.branches_path, self.tags_path)
    self._unremovable_paths = [
        self.trunk_path, self.branches_path, self.tags_path]

    # A list of transformation rules (regexp, replacement) applied to
    # symbol names in this project.
    if symbol_transforms is None:
      self.symbol_transforms = []
    else:
      self.symbol_transforms = symbol_transforms

  def __cmp__(self, other):
    return cmp(self.id, other.id)

  def __hash__(self):
    return self.id

  def determine_repository_root(path):
    """Ascend above the specified PATH if necessary to find the
    cvs_repository_root (a directory containing a CVSROOT directory)
    and the cvs_module (the path of the conversion root within the cvs
    repository).  Return the root path and the module path of this
    project relative to the root.

    NB: cvs_module must be seperated by '/', *not* by os.sep."""

    def is_cvs_repository_root(path):
      return os.path.isdir(os.path.join(path, 'CVSROOT'))

    original_path = path
    cvs_module = ''
    while not is_cvs_repository_root(path):
      # Step up one directory:
      prev_path = path
      path, module_component = os.path.split(path)
      if path == prev_path:
        # Hit the root (of the drive, on Windows) without finding a
        # CVSROOT dir.
        raise FatalError(
            "the path '%s' is not a CVS repository, nor a path "
            "within a CVS repository.  A CVS repository contains "
            "a CVSROOT directory within its root directory."
            % (original_path,))

      cvs_module = module_component + "/" + cvs_module

    return path, cvs_module

  determine_repository_root = staticmethod(determine_repository_root)

  def _get_cvs_path(self, filename):
    """Return the path to FILENAME relative to project_cvs_repos_path.

    FILENAME is a filesystem name that has to be within
    self.project_cvs_repos_path.  Return the filename relative to
    self.project_cvs_repos_path, with ',v' striped off if present, and
    with os.sep converted to '/'."""

    (tail, n) = self.project_prefix_re.subn('', filename, 1)
    if n != 1:
      raise FatalError(
          "Project._get_cvs_path: '%s' is not a sub-path of '%s'"
          % (filename, self.project_cvs_repos_path,))
    if tail.endswith(',v'):
      tail = tail[:-2]
    return tail.replace(os.sep, '/')

  def is_file_in_attic(self, filename):
    """Return True iff FILENAME is in an Attic subdirectory.

    FILENAME is the filesystem path to a '*,v' file."""

    dirname = os.path.dirname(filename)
    (dirname2, basename2,) = os.path.split(dirname)
    return basename2 == 'Attic' and self.project_prefix_re.match(dirname2)

  def get_cvs_file(self, filename):
    """Return a CVSFile describing the file with name FILENAME.

    FILENAME must be a *,v file within this project.  The CVSFile is
    assigned a new unique id.  All of the CVSFile information is
    filled in except mode (which can only be determined by parsing the
    file)."""

    if self.is_file_in_attic(filename):
      (dirname, basename,) = os.path.split(filename)
      # drop the 'Attic' portion from the filename for the canonical name:
      canonical_filename = os.path.join(os.path.dirname(dirname), basename)
    else:
      canonical_filename = filename

    file_stat = os.stat(filename)

    # The size of the file in bytes:
    file_size = file_stat[stat.ST_SIZE]

    # Whether or not the executable bit is set:
    file_executable = bool(file_stat[0] & stat.S_IXUSR)

    # mode is not known, so we temporarily set it to None.
    return CVSFile(
        None, self, filename, self._get_cvs_path(canonical_filename),
        file_executable, file_size, None
        )

  def is_source(self, svn_path):
    """Return True iff SVN_PATH is a legitimate source for this project.

    Legitimate paths are self.trunk_path or any directory directly
    under self.branches_path."""

    if svn_path == self.trunk_path:
      return True

    (head, tail,) = path_split(svn_path)
    if head == self.branches_path:
      return True

    return False

  def is_unremovable(self, svn_path):
    """Return True iff the specified path must not be removed."""

    return svn_path in self._unremovable_paths

  def get_branch_path(self, branch_symbol):
    """Return the svnpath for BRANCH_SYMBOL."""

    return path_join(self.branches_path, branch_symbol.get_clean_name())

  def get_tag_path(self, tag_symbol):
    """Return the svnpath for TAG_SYMBOL."""

    return path_join(self.tags_path, tag_symbol.get_clean_name())

  def make_trunk_path(self, cvs_path):
    """Return the trunk path for CVS_PATH.

    Return the svn path for this file on trunk."""

    return path_join(self.trunk_path, cvs_path)

  def make_branch_path(self, branch_symbol, cvs_path):
    """Return the svn path for CVS_PATH on branch BRANCH_SYMBOL."""

    return path_join(self.get_branch_path(branch_symbol), cvs_path)

  def transform_symbol(self, cvs_file, name):
    """Transform the symbol NAME using the renaming rules specified
    with --symbol-transform.  Return the transformed symbol name."""

    for symbol_transform in self.symbol_transforms:
      newname = symbol_transform.transform(cvs_file, name)
      if newname != name:
        Log().warn("   symbol '%s' transformed to '%s'" % (name, newname))
        name = newname

    return name


