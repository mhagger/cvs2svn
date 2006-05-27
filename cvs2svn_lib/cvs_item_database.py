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

"""This module contains a database that can store arbitrary CVSItems."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.database import PrimedPDatabase
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag


class CVSItemDatabase:
  """A Database to store CVSItem objects and retrieve them by their id."""

  def __init__(self, filename, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.db = PrimedPDatabase(
        filename, mode, (CVSRevision, CVSBranch, CVSTag,))

  def add(self, cvs_item):
    """Add CVS_ITEM, a CVSItem, to the database."""

    self.db['%x' % cvs_item.id] = cvs_item

  def __getitem__(self, id):
    """Return the CVSItem stored under ID."""

    return self.db['%x' % (id,)]


