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
from cvs_item import CVSRevision
from database import PDatabase


class CVSRevisionDatabase:
  """A Database to store CVSRevision objects and retrieve them by their id.

  Pickling the objects directly would be wasteful because that would
  store the class name with each object (increasing the DB size by
  about 30%).  We don't need that overhead because we only pickle
  objects of a single type.  Therefore we use the __getstate__ and
  __setstate__ methods described by the pickling protocol, but pickle
  the state ourselves (i.e., without the class information).  The only
  trick is that we have to call the __setstate__ method on a
  newly-created (but not initialized) instance, which we create using
  CVSRevision.__new__."""

  def __init__(self, filename, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.db = PDatabase(filename, mode)

  def log_revision(self, c_rev):
    """Add C_REV, a CVSRevision, to the database."""

    self.db['%x' % c_rev.id] = c_rev.__getstate__()

  def get_revision(self, c_rev_id):
    """Return the CVSRevision stored under C_REV_ID."""

    instance = CVSRevision.__new__(CVSRevision)
    instance.__setstate__(self.db['%x' % (c_rev_id,)])
    return instance


