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

"""This module contains the CVSRevisionCreator class."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.log import Log
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.line_of_development import Branch
from cvs2svn_lib.database import Database
from cvs2svn_lib.database import SDatabase
from cvs2svn_lib.cvs_commit import CVSCommit
from cvs2svn_lib.svn_commit import SVNSymbolCloseCommit


class CVSRevisionCreator:
  """This class coordinates the committing of changesets and symbols."""

  def __init__(self):
    if not Ctx().trunk_only:
      self.last_revs_db = Database(
          artifact_manager.get_temp_file(config.SYMBOL_LAST_CVS_REVS_DB),
          DB_OPEN_READ)

    # A set containing the closed symbols.  That is, we've already
    # encountered the last CVSRevision that is a source for that
    # symbol, the final fill for this symbol has been done, and we
    # never need to fill it again.
    self._done_symbols = set()

  def _commit_symbols(self, symbols, timestamp):
    """Generate one SVNCommit for each symbol in SYMBOLS."""

    # Sort the closeable symbols so that we will always process the
    # symbols in the same order, regardless of the order in which the
    # dict hashing algorithm hands them back to us.  We do this so
    # that our tests will get the same results on all platforms.
    symbols = list(symbols)
    symbols.sort(lambda a, b: cmp(a.name, b.name))

    for symbol in symbols:
      Ctx()._persistence_manager.put_svn_commit(
          SVNSymbolCloseCommit(symbol, timestamp))
      self._done_symbols.add(symbol)

  def process_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP for all of its entries.

    The changesets must be fed to this function in proper dependency
    order."""

    cvs_revs = list(changeset.get_cvs_items())

    if not cvs_revs:
      Log().warn('Changeset has no items: %r' % changeset)
      return

    metadata_id = cvs_revs[0].metadata_id

    author, log = Ctx()._metadata_db[metadata_id]
    cvs_commit = CVSCommit(metadata_id, author, log, timestamp)

    # A set of symbols for which the last source CVSRevision has been
    # processed and is therefore ready to be closed.
    symbols = set()

    for cvs_rev in cvs_revs:
      if Ctx().trunk_only and isinstance(cvs_rev.lod, Branch):
        continue

      cvs_commit.add_revision(cvs_rev)

      # Add to symbols any symbols from CVS_REV for which CVS_REV is
      # the last CVSRevision.
      if not Ctx().trunk_only:
        for symbol_id in self.last_revs_db.get('%x' % (cvs_rev.id,), []):
          symbols.add(Ctx()._symbol_db.get_symbol(symbol_id))

    cvs_commit.process_revisions(self._done_symbols)
    self._commit_symbols(symbols, timestamp)


