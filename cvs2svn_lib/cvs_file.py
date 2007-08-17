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
from cvs2svn_lib.common import path_split
from cvs2svn_lib.context import Ctx


class CVSPath(object):
  """Represent a CVS file or directory.

  Members:
    ID -- (int) unique ID for this CVSPath.
    PROJECT -- (Project) the project containing this CVSPath.
    FILENAME -- (string) the filesystem path to this CVSPath.
    CVS_PATH -- (string) the canonical path within the Project (no
        'Attic', no ',v', forward slashes).

  """

  def __init__(self, id, project, filename, cvs_path):
    self.id = id
    self.project = project
    self.filename = filename
    self.cvs_path = cvs_path

  def get_basename(self):
    """Return the last path component of self.cvs_path."""

    return path_split(self.cvs_path)[1]

  basename = property(get_basename)


class CVSDirectory(CVSPath):
  """Represent a CVS directory.

  Members:

    ID -- (int or None) unique id for this file.  If None, a new id is
        generated.
    PROJECT -- (Project) the project containing this file.
    FILENAME -- (string) the filesystem path to the CVS file.
    CVS_PATH -- (string) the canonical path within the CVS project (no
        'Attic', no ',v', forward slashes).

  CVS_PATH might contain an 'Attic' component if it should be retained
  as an Attic directory in the SVN repository; i.e., if a filename
  exists in and out of Attic and the --retain-conflicting-attic-files
  option was specified.

  """

  def __init__(self, id, project, filename, cvs_path):
    """Initialize a new CVSDirectory object."""

    CVSPath.__init__(self, id, project, filename, cvs_path)

  def __getstate__(self):
    return (self.id, self.project.id, self.filename, self.cvs_path,)

  def __setstate__(self, state):
    (self.id, project_id, self.filename, self.cvs_path,) = state
    self.project = Ctx().projects[project_id]

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path + '/'


class CVSFile(CVSPath):
  """Represent a CVS file.

  Members:

    ID -- (int) unique id for this file.
    PROJECT -- (Project) the project containing this file.
    FILENAME -- (string) the filesystem path to the CVS file.
    CVS_PATH -- (string) the canonical path within the CVS project (no
        'Attic', no ',v', forward slashes).
    EXECUTABLE -- (bool) True iff RCS file has executable bit set.
    FILE_SIZE -- (long) size of the RCS file in bytes.
    MODE -- (string or None) 'kkv', 'kb', etc.

  CVS_PATH might contain an 'Attic' component if it should be retained
  in the SVN repository; i.e., if the same filename exists out of
  Attic and the --retain-conflicting-attic-files option was specified.

  """

  def __init__(
        self, id, project, filename, cvs_path, executable, file_size, mode
        ):
    """Initialize a new CVSFile object."""

    CVSPath.__init__(self, id, project, filename, cvs_path)
    self.executable = executable
    self.file_size = file_size
    self.mode = mode

  def __getstate__(self):
    return (
        self.id, self.project.id, self.filename, self.cvs_path,
        self.executable, self.file_size, self.mode,
        )

  def __setstate__(self, state):
    (
        self.id, project_id, self.filename, self.cvs_path,
        self.executable, self.file_size, self.mode,
        ) = state
    self.project = Ctx().projects[project_id]

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path


