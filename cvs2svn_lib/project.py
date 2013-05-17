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

"""This module contains database facilities used by cvs2svn."""


import os
import cPickle

from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import IllegalSVNPathError
from cvs2svn_lib.common import normalize_svn_path
from cvs2svn_lib.common import verify_paths_disjoint
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

  def __init__(
        self, id, project_cvs_repos_path,
        initial_directories=[],
        symbol_transforms=None,
        exclude_paths=[],
        ):
    """Create a new Project record.

    ID is a unique id for this project.  PROJECT_CVS_REPOS_PATH is the
    main CVS directory for this project (within the filesystem).

    INITIAL_DIRECTORIES is an iterable of all SVN directories that
    should be created when the project is first created.  Normally,
    this should include the trunk, branches, and tags directory.

    SYMBOL_TRANSFORMS is an iterable of SymbolTransform instances
    which will be used to transform any symbol names within this
    project.

    EXCLUDE_PATHS is an iterable of paths that should be excluded from
    the conversion.  The paths should be relative to
    PROJECT_CVS_REPOS_PATH and use slashes ('/').  Paths for
    individual files should include the ',v' extension.
    """

    self.id = id

    self.project_cvs_repos_path = os.path.normpath(project_cvs_repos_path)
    if not os.path.isdir(self.project_cvs_repos_path):
      raise FatalError("The specified CVS repository path '%s' is not an "
                       "existing directory." % self.project_cvs_repos_path)

    self.cvs_repository_root, self.cvs_module = \
        self.determine_repository_root(
            os.path.abspath(self.project_cvs_repos_path))

    # The SVN directories to add when the project is first created:
    self._initial_directories = []

    for path in initial_directories:
      try:
        path = normalize_svn_path(path, False)
      except IllegalSVNPathError, e:
        raise FatalError(
            'Initial directory %r is not a legal SVN path: %s'
            % (path, e,)
            )
      self._initial_directories.append(path)

    verify_paths_disjoint(*self._initial_directories)

    # A list of transformation rules (regexp, replacement) applied to
    # symbol names in this project.
    if symbol_transforms is None:
      symbol_transforms = []

    self.symbol_transform = CompoundSymbolTransform(symbol_transforms)

    self.exclude_paths = set(exclude_paths)

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

  @staticmethod
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

  def transform_symbol(self, cvs_file, symbol_name, revision):
    """Transform the symbol SYMBOL_NAME.

    SYMBOL_NAME refers to revision number REVISION in CVS_FILE.
    REVISION is the CVS revision number as a string, with zeros
    removed (e.g., '1.7' or '1.7.2').  Use the renaming rules
    specified with --symbol-transform to possibly rename the symbol.
    Return the transformed symbol name, the original name if it should
    not be transformed, or None if the symbol should be omitted from
    the conversion."""

    return self.symbol_transform.transform(cvs_file, symbol_name, revision)

  def get_trunk(self):
    """Return the Trunk instance for this project.

    This method can only be called after self.trunk_id has been
    initialized in CollectRevsPass."""

    return Ctx()._symbol_db.get_symbol(self.trunk_id)

  def get_root_cvs_directory(self):
    """Return the root CVSDirectory instance for this project.

    This method can only be called after self.root_cvs_directory_id
    has been initialized in CollectRevsPass."""

    return Ctx()._cvs_path_db.get_path(self.root_cvs_directory_id)

  def get_initial_directories(self):
    """Generate the project's initial SVN directories.

    Yield as strings the SVN paths of directories that should be
    created when the project is first created."""

    # Yield the path of the Trunk symbol for this project (which might
    # differ from the one passed to the --trunk option because of
    # SymbolStrategyRules).  The trunk path might be '' during a
    # trunk-only conversion, but that is OK because DumpstreamDelegate
    # considers that directory to exist already and will therefore
    # ignore it:
    yield self.get_trunk().base_path

    for path in self._initial_directories:
      yield path

  def __str__(self):
    return self.project_cvs_repos_path


def read_projects(filename):
  retval = {}
  f = open(filename, 'rb')
  for project in cPickle.load(f):
    retval[project.id] = project
  f.close()
  return retval


def write_projects(filename):
  f = open(filename, 'wb')
  cPickle.dump(Ctx()._projects.values(), f, -1)
  f.close()


