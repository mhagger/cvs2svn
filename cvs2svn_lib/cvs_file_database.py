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


from boolean import *
from database import PDatabase


class CVSFileDatabase:
  """A Database to store CVSFile objects and retrieve them by their id."""

  def __init__(self, filename, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open())."""

    self.db = PDatabase(filename, mode)

  def log_file(self, cvs_file):
    """Add CVS_FILE, a CVSFile instance, to the database."""

    self.db['%x' % cvs_file.id] = cvs_file

  def get_file(self, id):
    """Return the CVSFile with the specified ID."""

    return self.db['%x' % id]


