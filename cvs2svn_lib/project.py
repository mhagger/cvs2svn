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

"""This module contains database facilities used by cvs2svn."""


import re
import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.common import IllegalSVNPathError
from cvs2svn_lib.common import normalize_svn_path
from cvs2svn_lib.common import verify_paths_disjoint
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol_transform import CompoundSymbolTransform


class FileInAndOutOfAtticException(Exception):
  def __init__(self, non_attic_path, attic_path):
    Exception.__init__(
        self,
        "A CVS repository cannot contain both %s and %s"
        % (non_attic_path, attic_path))

    self.non_attic_path = non_attic_path
    self.attic_path = attic_path


def normalize_ttb_path(opt, path, allow_empty=False):
  try:
    return normalize_svn_path(path, allow_empty)
  except IllegalSVNPathError, e:
    raise FatalError('Problem with %s: %s' % (opt, e,))


class Project(object):
  """A project within a CVS repository."""

  def __init__(self, project_cvs_repos_path,
               trunk_path, branches_path=None, tags_path=None,
               symbol_transforms=None):
    """Create a new Project record.

    PROJECT_CVS_REPOS_PATH is the main CVS directory for this project
    (within the filesystem).  TRUNK_PATH, BRANCHES_PATH, and TAGS_PATH
    are the full, normalized directory names in svn for the
    corresponding part of the repository.  (BRANCHES_PATH and
    TAGS_PATH do not have to be specified for a --trunk-only
    conversion.)

    SYMBOL_TRANSFORMS is a list of SymbolTransform instances which
    will be used to transform any symbol names within this project."""

    # A unique id for this project.  This field is filled in by
    # RunOptions.add_project().
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
    self.trunk_path = normalize_ttb_path(
        '--trunk', trunk_path, allow_empty=Ctx().trunk_only
        )
    if not Ctx().trunk_only:
      self.branches_path = normalize_ttb_path('--branches', branches_path)
      self.tags_path = normalize_ttb_path('--tags', tags_path)
      verify_paths_disjoint(
          self.trunk_path, self.branches_path, self.tags_path
          )

    # A list of transformation rules (regexp, replacement) applied to
    # symbol names in this project.
    if symbol_transforms is None:
      symbol_transforms = []

    self.symbol_transform = CompoundSymbolTransform(symbol_transforms)

    # The ID of the Trunk instance for this Project.  This member is
    # filled in during CollectRevsPass.
    self.trunk_id = None

    # The ID of the CVSDirectory representing the root directory of
    # this project.  This member is filled in during CollectRevsPass.
    self.root_cvs_directory_id = None

  def __eq__(self, other):
    return self.id == other.id

  def __cmp__(self, other):
    return cmp(self.cvs_module, other.cvs_module) \
           or cmp(self.id, other.id)

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

  def get_trunk_path(self):
    """Return the trunk path for this project."""

    return self.trunk_path

  def get_branch_path(self, branch_symbol):
    """Return the svnpath for BRANCH_SYMBOL.

    This routine must not be called during --trunk-only conversions."""

    return path_join(self.branches_path, branch_symbol.get_clean_name())

  def get_tag_path(self, tag_symbol):
    """Return the svnpath for TAG_SYMBOL.

    This routine must not be called during --trunk-only conversions."""

    return path_join(self.tags_path, tag_symbol.get_clean_name())

  def transform_symbol(self, cvs_file, symbol_name, revision):
    """Transform the symbol SYMBOL_NAME.

    SYMBOL_NAME refers to revision number REVISION in CVS_FILE.
    REVISION is the CVS revision number as a string, with zeros
    removed (e.g., '1.7' or '1.7.2').  Use the renaming rules
    specified with --symbol-transform to possibly rename the symbol.
    Return the transformed symbol name, or the original name if it
    should not be transformed."""

    newname = self.symbol_transform.transform(cvs_file, symbol_name, revision)
    if newname is None:
      Log().warn(
          "   symbol '%s'=%s ignored in %s"
          % (symbol_name, revision, cvs_file.filename,)
          )
    elif newname != symbol_name:
      Log().warn(
          "   symbol '%s'=%s transformed to '%s' in %s"
          % (symbol_name, revision, newname, cvs_file.filename,)
          )

    return newname

  def __str__(self):
    return self.trunk_path


