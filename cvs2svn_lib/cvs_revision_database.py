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
from context import Ctx
from cvs_branch import CVSBranch
from cvs_revision import CVSRevision
from database import PDatabase


class CVSRevisionDatabase:
  """A Database to store CVSRevision objects and retrieve them by their id."""

  def __init__(self, filename, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.db = PDatabase(filename, mode)

  def log_revision(self, c_rev):
    """Add C_REV, a CVSRevision, to the database."""

    args = list(c_rev.__getinitargs__())
    args[1] = args[1].id
    args[9] = args[9] and args[9].name
    self.db['%x' % c_rev.id] = args

  def get_revision(self, c_rev_id):
    """Return the CVSRevision stored under C_REV_ID."""

    args = self.db['%x' % (c_rev_id,)]
    args[1] = Ctx()._cvs_file_db.get_file(args[1])
    args[9] = args[9] and CVSBranch(args[1], args[9])
    return CVSRevision(*args)


