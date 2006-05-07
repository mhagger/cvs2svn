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
import config
from context import Ctx
from artifact_manager import artifact_manager
import cvs_revision
import database


class CVSRevisionDatabase:
  """A Database to store CVSRevision objects and retrieve them by their
  unique_key()."""

  def __init__(self, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open())."""

    self.cvs_revs_db = database.SDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_DB), mode)

  def log_revision(self, c_rev):
    """Add C_REV, a CVSRevision, to the database."""

    self.cvs_revs_db[c_rev.unique_key()] = c_rev.__getstate__()

  def get_revision(self, unique_key):
    """Return the CVSRevision stored under UNIQUE_KEY."""

    return cvs_revision.parse_cvs_revision(self.cvs_revs_db[unique_key])


