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

"""This module contains a class to store information about a CVS file."""

import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import path_join
from cvs2svn_lib.context import Ctx


class CVSPath(object):
  """Represent a CVS file or directory.

  Members:
    ID -- (int) unique ID for this CVSPath.
    PROJECT -- (Project) the project containing this CVSPath.
    PARENT_DIRECTORY -- (CVSDirectory or None) the CVSDirectory
        containing this CVSPath.
    BASENAME -- (string) the base name of this CVSPath (no ',v').
    FILENAME -- (string) the filesystem path to this CVSPath in the
        CVS repository.
    ORDINAL -- (int) the order that this instance should be sorted
        relative to other CVSPath instances.  This member is set based
        on the ordering imposed by slow_compare() by CollectData after
        all CVSFiles have been processed.  Comparisons of CVSPath
        using __cmp__() simply compare the ordinals.

  """

  __slots__ = [
      'id',
      'project',
      'parent_directory',
      'basename',
      'filename',
      'ordinal',
      ]

  def __init__(self, id, project, parent_directory, basename, filename):
    self.id = id
    self.project = project
    self.parent_directory = parent_directory
    self.basename = basename
    self.filename = filename

  def __getstate__(self):
    """This method must only be called after ordinal has been set."""

    return (
        self.id, self.project.id, self.parent_directory,
        self.basename, self.filename, self.ordinal,
        )

  def __setstate__(self, state):
    (
        self.id, project_id, self.parent_directory,
        self.basename, self.filename, self.ordinal,
        ) = state
    self.project = Ctx()._projects[project_id]

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

    if self.parent_directory is None:
      return self.basename
    else:
      return path_join(self.parent_directory.cvs_path, self.basename)

  cvs_path = property(get_cvs_path)

  def _get_dir_components(self):
    if self.parent_directory is None:
      return [self.basename]
    else:
      retval = self.parent_directory._get_dir_components()
      retval.extend(self.basename)
      return retval

  def slow_compare(a, b):
    return (
        # Sort first by project:
        cmp(a.project, b.project)
        # Then by directory components:
        or cmp(a._get_dir_components(), b._get_dir_components())
        )

  def __cmp__(a, b):
    """This method must only be called after ordinal has been set."""

    return cmp(a.ordinal, b.ordinal)


class CVSDirectory(CVSPath):
  """Represent a CVS directory.

  Members:

    ID -- (int or None) unique id for this file.  If None, a new id is
        generated.
    PROJECT -- (Project) the project containing this file.
    PARENT_DIRECTORY -- (CVSDirectory or None) the CVSDirectory containing
        this CVSDirectory.
    BASENAME -- (string) the base name of this CVSDirectory (no ',v').
    FILENAME -- (string) the filesystem path to this CVSDirectory in the
        CVS repository.

  """

  __slots__ = []

  def __init__(self, id, project, parent_directory, basename, filename):
    """Initialize a new CVSDirectory object."""

    CVSPath.__init__(self, id, project, parent_directory, basename, filename)

  def __getstate__(self):
    return CVSPath.__getstate__(self)

  def __setstate__(self, state):
    CVSPath.__setstate__(self, state)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path + '/'

  def __repr__(self):
    return 'CVSDirectory<%d>(%r)' % (self.id, str(self),)


class CVSFile(CVSPath):
  """Represent a CVS file.

  Members:

    ID -- (int) unique id for this file.
    PROJECT -- (Project) the project containing this file.
    PARENT_DIRECTORY -- (CVSDirectory or None) the CVSDirectory containing
        this CVSFile.
    BASENAME -- (string) the base name of this CVSFile (no ',v').
    FILENAME -- (string) the filesystem path to this CVSFile in the
        CVS repository.
    EXECUTABLE -- (bool) True iff RCS file has executable bit set.
    FILE_SIZE -- (long) size of the RCS file in bytes.
    MODE -- (string or None) 'kkv', 'kb', etc.

  PARENT_DIRECTORY might contain an 'Attic' component if it should be
  retained in the SVN repository; i.e., if the same filename exists out
  of Attic and the --retain-conflicting-attic-files option was specified.

  """

  __slots__ = ['executable', 'file_size', 'mode']

  def __init__(
        self, id, project, parent_directory, basename, filename,
        executable, file_size, mode
        ):
    """Initialize a new CVSFile object."""

    CVSPath.__init__(self, id, project, parent_directory, basename, filename)
    self.executable = executable
    self.file_size = file_size
    self.mode = mode

  def __getstate__(self):
    return (
        CVSPath.__getstate__(self),
        self.executable, self.file_size, self.mode,
        )

  def __setstate__(self, state):
    (
        cvs_path_state,
        self.executable, self.file_size, self.mode,
        ) = state
    CVSPath.__setstate__(self, cvs_path_state)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path

  def __repr__(self):
    return 'CVSFile<%d>(%r)' % (self.id, str(self),)


