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


from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.database import Database


class LastSymbolicNameDatabase:
  """Passing every changeset in s-revs to this class will result in a
  Database whose key is the last changeset a symbolic name was seen
  in, and whose value is a list of all symbolicnames that were last
  seen in that changeset."""

  def __init__(self):
    # A map { symbol_id : changeset_id } of the id of the
    # chronologically last Changeset that had the symbol as a tag or
    # branch.  Once we've gone through all the changesets,
    # symbols.keys() will be a list of all tag and branch symbol_ids,
    # and their corresponding values will be the id of the changeset
    # containing the last CVS revision that the symbol was used in.
    self._symbols = {}

  def log_changeset(self, changeset):
    """Log all of the CVSRevisions in the changeset."""

    for cvs_item in changeset.get_cvs_items():
      if isinstance(cvs_item, CVSRevision):
        cvs_rev = cvs_item
        for tag_id in cvs_rev.tag_ids:
          cvs_tag = Ctx()._cvs_items_db[tag_id]
          self._symbols[cvs_tag.symbol.id] = changeset.id
        if cvs_rev.op != OP_DELETE:
          for branch_id in cvs_rev.branch_ids:
            cvs_branch = Ctx()._cvs_items_db[branch_id]
            self._symbols[cvs_branch.symbol.id] = changeset.id

  def create_database(self):
    """Create the SYMBOL_LAST_CHANGESETS_DB.

    The database will hold an inversion of symbols above--a map {
    changeset.id : [ symbol, ... ] of symbols that close in each
    changeset."""

    symbol_revs = {}
    for symbol_id, changeset_id in self._symbols.iteritems():
      symbol_revs.setdefault(changeset_id, []).append(symbol_id)

    symbol_revs_db = Database(
        artifact_manager.get_temp_file(config.SYMBOL_LAST_CHANGESETS_DB),
        DB_OPEN_NEW)
    for (changeset_id, symbol_ids) in symbol_revs.iteritems():
      symbol_revs_db['%x' % changeset_id] = symbol_ids
    symbol_revs_db.close()


