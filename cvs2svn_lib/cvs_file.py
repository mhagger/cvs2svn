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

"""This module contains a class to store information about a CVS file."""

import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.key_generator import KeyGenerator


class CVSFile(object):
  """Represent a CVS file."""

  key_generator = KeyGenerator(1)

  def __init__(self, id, project, filename, cvs_path,
               in_attic, executable, file_size, mode):
    """Initialize a new CVSFile object.

    Arguments:

      ID                 --> (int or None) unique id for this file.  If None,
                             a new id is generated.
      PROJECT            --> (Project) the project containing this file
      FILENAME           --> (string) the filesystem path to the CVS file
      CVS_PATH           --> (string) the canonical path within the CVS
                             project (no 'Attic', no ',v', forward slashes)
      IN_ATTIC           --> (bool) True iff RCS file is in Attic
      EXECUTABLE         --> (bool) True iff RCS file has executable bit set
      FILE_SIZE          --> (long) size of the RCS file in bytes
      MODE               --> (string or None) 'kkv', 'kb', etc."""

    if id is None:
      self.id = self.key_generator.gen_id()
    else:
      self.id = id

    self.project = project
    self.filename = filename
    self.cvs_path = cvs_path
    self.in_attic = in_attic
    self.executable = executable
    self.file_size = file_size
    self.mode = mode

  def get_basename(self):
    """Return the last path component of self.filename, minus the ',v'."""

    return os.path.basename(self.filename)[:-2]

  basename = property(get_basename)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return self.cvs_path


