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

from boolean import *


class CVSFile(object):
  """Represent a CVS file."""

  def __init__(self, id, filename, canonical_filename, cvs_path,
               in_attic, executable, file_size, mode):
    """Initialize a new CVSFile object.

    Arguments:

      ID                 --> (long) unique id for this file
      FILENAME           --> (string) the filesystem path to the CVS file
      CANONICAL_FILENAME --> (string) FILENAME, with 'Attic' stripped out
      CVS_PATH           --> (string) the canonical path within the CVS
                             repository (no 'Attic', no ',v', forward slashes)
      IN_ATTIC           --> (bool) True iff RCS file is in Attic
      EXECUTABLE         --> (bool) True iff RCS file has executable bit set
      FILE_SIZE          --> (long) size of the RCS file in bytes
      MODE               --> (string or None) 'kkv', 'kb', etc."""

    self.id = id
    self.filename = filename
    self.canonical_filename = canonical_filename
    self.cvs_path = cvs_path
    self.in_attic = in_attic
    self.executable = executable
    self.file_size = file_size
    self.mode = mode

  def get_basename(self):
    """Return the last path component of self.filename, minus the ',v'."""

    return os.path.basename(self.filename)[:-2]

  basename = property(get_basename)


