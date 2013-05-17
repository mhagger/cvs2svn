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
from cvs2svn_lib.cvs_path import CVSPath


class CVSPathDatabase:
  """A database to store CVSPath objects and retrieve them by their id.

  All RCS files within every CVS project repository are recorded here
  as CVSFile instances, and all directories within every CVS project
  repository (including empty directories) are recorded here as
  CVSDirectory instances."""

  def __init__(self, mode):
    """Initialize an instance, opening database in MODE (where MODE is
    either DB_OPEN_NEW or DB_OPEN_READ)."""

    self.mode = mode

    # A map { id : CVSPath }
    self._cvs_paths = {}

    if self.mode == DB_OPEN_NEW:
      pass
    elif self.mode == DB_OPEN_READ:
      f = open(artifact_manager.get_temp_file(config.CVS_PATHS_DB), 'rb')
      try:
        cvs_paths = cPickle.load(f)
      finally:
        f.close()
      for cvs_path in cvs_paths:
        self._cvs_paths[cvs_path.id] = cvs_path
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

  def set_cvs_path_ordinals(self):
    cvs_files = sorted(self.itervalues(), key=CVSPath.sort_key)
    for (i, cvs_file) in enumerate(cvs_files):
      cvs_file.ordinal = i

  def log_path(self, cvs_path):
    """Add CVS_PATH, a CVSPath instance, to the database."""

    if self.mode == DB_OPEN_READ:
      raise RuntimeError('Cannot write items in mode %r' % self.mode)

    self._cvs_paths[cvs_path.id] = cvs_path

  def itervalues(self):
    return self._cvs_paths.itervalues()

  def get_path(self, id):
    """Return the CVSPath with the specified ID."""

    return self._cvs_paths[id]

  def close(self):
    if self.mode == DB_OPEN_NEW:
      self.set_cvs_path_ordinals()
      f = open(artifact_manager.get_temp_file(config.CVS_PATHS_DB), 'wb')
      cPickle.dump(self._cvs_paths.values(), f, -1)
      f.close()

    self._cvs_paths = None


