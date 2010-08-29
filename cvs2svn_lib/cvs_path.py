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

"""Classes that represent files and directories within CVS repositories."""

import os

from cvs2svn_lib.common import path_join
from cvs2svn_lib.context import Ctx


class CVSPath(object):
  """Represent a CVS file or directory.

  Members:

    id -- (int) unique ID for this CVSPath.  At any moment, there is
        at most one CVSPath instance with a particular ID.  (This
        means that object identity is the same as object equality, and
        objects can be used as map keys even though they don't have a
        __hash__() method).

    project -- (Project) the project containing this CVSPath.

    parent_directory -- (CVSDirectory or None) the CVSDirectory
        containing this CVSPath.

    basename -- (string) the base name of this CVSPath (no ',v').  The
        basename of the root directory of a project is ''.

    ordinal -- (int) the order that this instance should be sorted
        relative to other CVSPath instances.  This member is set based
        on the ordering imposed by sort_key() by CVSPathDatabase after
        all CVSFiles have been processed.  Comparisons of CVSPath
        using __cmp__() simply compare the ordinals.

  """

  __slots__ = [
      'id',
      'project',
      'parent_directory',
      'basename',
      'ordinal',
      'filename',
      ]

  def __init__(self, id, project, parent_directory, basename):
    self.id = id
    self.project = project
    self.parent_directory = parent_directory
    self.basename = basename

    self.filename = os.path.normpath(self._calculate_filename())

  def __getstate__(self):
    """This method must only be called after ordinal has been set."""

    return (
        self.id, self.project.id,
        self.parent_directory, self.basename,
        self.ordinal,
        )

  def __setstate__(self, state):
    (
        self.id, project_id,
        self.parent_directory, self.basename,
        self.ordinal,
        ) = state
    self.project = Ctx()._projects[project_id]
    self.filename = os.path.normpath(self._calculate_filename())

  def get_filename(self):
    """Return the filesystem path to this CVSPath in the CVS repository.

    This is in native format, and already normalised the way
    os.path.normpath() normalises paths.

    It starts with the repository path passed to run_options.add_project()
    in the options.py file."""

    # This turns out to be a hot path through the code.
    # It's used by SubtreeSymbolTransform and similar transforms, so it's
    # called at least:
    #   (num_files * num_symbols_per_file * num_subtree_symbol_transforms)
    # times.  On a large repository with several subtree symbol transforms,
    # that can exceed 100,000,000 calls.  And _calculate_filename() is quite
    # complex, so doing that every time could add about 10 minutes to the
    # cvs2svn runtime.
    #
    # So now we precalculate this and just return it.

    return self.filename

  def get_ancestry(self):
    """Return a list of the CVSPaths leading from the root path to SELF.

    Return the CVSPaths in a list, starting with
    self.project.get_root_cvs_directory() and ending with self."""

    ancestry = []
    p = self
    while p is not None:
      ancestry.append(p)
      p = p.parent_directory

    ancestry.reverse()
    return ancestry

  def get_cvs_path(self):
    """Return the canonical path within the Project.

    The canonical path:

    - Uses forward slashes

    - Doesn't include ',v' for files

    - This doesn't include the 'Attic' segment of the path unless the
      file is to be left in an Attic directory in the SVN repository;
      i.e., if a filename exists in and out of Attic and the
      --retain-conflicting-attic-files option was specified.

    """

    return path_join(*[p.basename for p in self.get_ancestry()[1:]])

  cvs_path = property(get_cvs_path)

  def _get_dir_components(self):
    """Return a list containing the components of the path leading to SELF.

    The return value contains the base names of all of the parent
    directories (except for the root directory) and SELF."""

    return [p.basename for p in self.get_ancestry()[1:]]

  def __eq__(a, b):
    """Compare two CVSPath instances for equality.

    This method is supplied to avoid using __cmp__() for comparing for
    equality."""

    return a is b

  def sort_key(self):
    """Return the key that should be used for sorting CVSPath instances.

    This is a relatively expensive computation, so it is only used
    once, the the results are used to set the ordinal member."""

    return (
        # Sort first by project:
        self.project,
        # Then by directory components:
        self._get_dir_components(),
        )

  def __cmp__(a, b):
    """This method must only be called after ordinal has been set."""

    return cmp(a.ordinal, b.ordinal)


class CVSDirectory(CVSPath):
  """Represent a CVS directory.

  Members:

    id -- (int or None) unique id for this file.  If None, a new id is
        generated.

    project -- (Project) the project containing this file.

    parent_directory -- (CVSDirectory or None) the CVSDirectory
        containing this CVSDirectory.

    basename -- (string) the base name of this CVSDirectory (no ',v').

    ordinal -- (int) the order that this instance should be sorted
        relative to other CVSPath instances.  See CVSPath.ordinal.

    empty_subdirectory_ids -- (list of int) a list of the ids of any
        direct subdirectories that are empty.  (An empty directory is
        defined to be a directory that doesn't contain any RCS files
        or non-empty subdirectories.

  """

  __slots__ = ['empty_subdirectory_ids']

  def __init__(self, id, project, parent_directory, basename):
    """Initialize a new CVSDirectory object."""

    CVSPath.__init__(self, id, project, parent_directory, basename)

    # This member is filled in by CollectData.close():
    self.empty_subdirectory_ids = []

  def _calculate_filename(self):
    """Return the filesystem path to this CVSPath in the CVS repository."""

    if self.parent_directory is None:
      return self.project.project_cvs_repos_path
    else:
      return os.path.join(
          self.parent_directory.filename, self.basename
          )

  def __getstate__(self):
    return (
        CVSPath.__getstate__(self),
        self.empty_subdirectory_ids,
        )

  def __setstate__(self, state):
    (
        cvs_path_state,
        self.empty_subdirectory_ids,
        ) = state
    CVSPath.__setstate__(self, cvs_path_state)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path + '/'

  def __repr__(self):
    return 'CVSDirectory<%x>(%r)' % (self.id, str(self),)


class CVSFile(CVSPath):
  """Represent a CVS file.

  Members:

    id -- (int) unique id for this file.

    project -- (Project) the project containing this file.

    parent_directory -- (CVSDirectory) the CVSDirectory containing
        this CVSFile.

    basename -- (string) the base name of this CVSFile (no ',v').

    ordinal -- (int) the order that this instance should be sorted
        relative to other CVSPath instances.  See CVSPath.ordinal.

    _in_attic -- (bool) True if RCS file is in an Attic subdirectory
        that is not considered the parent directory.  (If a file is
        in-and-out-of-attic and one copy is to be left in Attic after
        the conversion, then the Attic directory is that file's
        PARENT_DIRECTORY and _IN_ATTIC is False.)

    executable -- (bool) True iff RCS file has executable bit set.

    file_size -- (long) size of the RCS file in bytes.

    mode -- (string or None) 'kkv', 'kb', etc., as read from the CVS
        file.

    description -- (string or None) the file description as read from
        the RCS file.

    properties -- (dict) file properties that are preserved across
        this history of this file.  Keys are strings; values are
        strings (indicating the property value) or None (indicating
        that the property should be left unset).  These properties can
        be overridden by CVSRevision.properties.  Different backends
        can use these properties for different purposes; for cvs2svn
        they become SVN versioned properties.  Properties whose names
        start with underscore are reserved for internal cvs2svn
        purposes.

  PARENT_DIRECTORY might contain an 'Attic' component if it should be
  retained in the SVN repository; i.e., if the same filename exists out
  of Attic and the --retain-conflicting-attic-files option was specified.

  """

  __slots__ = [
      '_in_attic',
      'executable',
      'file_size',
      'mode',
      'description',
      'properties',
      ]

  def __init__(
        self, id, project, parent_directory, basename, in_attic,
        executable, file_size, mode, description
        ):
    """Initialize a new CVSFile object."""

    assert parent_directory is not None

    # This member is needed by _calculate_filename(), which is called
    # by CVSPath.__init__().  So initialize it before calling
    # CVSPath.__init__().
    self._in_attic = in_attic
    CVSPath.__init__(self, id, project, parent_directory, basename)

    self.executable = executable
    self.file_size = file_size
    self.mode = mode
    self.description = description
    self.properties = None

  def determine_file_properties(self, file_property_setters):
    """Determine the properties for this file from FILE_PROPERTY_SETTERS.

    This must only be called after SELF.mode and SELF.description have
    been set by CollectData."""

    self.properties = {}

    for file_property_setter in file_property_setters:
      file_property_setter.set_properties(self)

  def _calculate_filename(self):
    """Return the filesystem path to this CVSPath in the CVS repository."""

    if self._in_attic:
      return os.path.join(
          self.parent_directory.filename, 'Attic', self.basename + ',v'
          )
    else:
      return os.path.join(
          self.parent_directory.filename, self.basename + ',v'
          )

  def __getstate__(self):
    return (
        CVSPath.__getstate__(self),
        self._in_attic, self.executable, self.file_size, self.mode,
        self.description, self.properties,
        )

  def __setstate__(self, state):
    (
        cvs_path_state,
        self._in_attic, self.executable, self.file_size, self.mode,
        self.description, self.properties,
        ) = state
    CVSPath.__setstate__(self, cvs_path_state)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path

  def __repr__(self):
    return 'CVSFile<%x>(%r)' % (self.id, str(self),)


