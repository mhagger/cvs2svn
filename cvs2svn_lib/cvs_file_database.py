# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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


import cPickle

from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.artifact_manager import artifact_manager


class CVSFileDatabase:
  """A database to store CVSFile objects and retrieve them by their id."""

  def __init__(self, mode):
    """Initialize an instance, opening database in MODE (where MODE is
    either DB_OPEN_NEW or DB_OPEN_READ)."""

    self.mode = mode

    # A map { id : CVSFile }
    self._cvs_files = {}

    if self.mode == DB_OPEN_NEW:
      pass
    elif self.mode == DB_OPEN_READ:
      f = open(artifact_manager.get_temp_file(config.CVS_FILES_DB), 'rb')
      cvs_files = cPickle.load(f)
      for cvs_file in cvs_files:
        self._cvs_files[cvs_file.id] = cvs_file
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

  def log_file(self, cvs_file):
    """Add CVS_FILE, a CVSFile instance, to the database."""

    if self.mode == DB_OPEN_READ:
      raise RuntimeError('Cannot write items in mode %r' % self.mode)

    self._cvs_files[cvs_file.id] = cvs_file

  def itervalues(self):
    for value in self._cvs_files.itervalues():
      yield value

  def get_file(self, id):
    """Return the CVSFile with the specified ID."""

    return self._cvs_files[id]

  def close(self):
    if self.mode == DB_OPEN_NEW:
      f = open(artifact_manager.get_temp_file(config.CVS_FILES_DB), 'wb')
      cPickle.dump(self._cvs_files.values(), f, -1)
      f.close()

    self._cvs_files = None


