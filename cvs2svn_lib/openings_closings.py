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

"""This module contains classes to keep track of symbol openings/closings."""


from __future__ import generators

import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.svn_revision_range import SVNRevisionRange
from cvs2svn_lib.symbol_filling_guide import get_source_set


# Constants used in SYMBOL_OPENINGS_CLOSINGS
OPENING = 'O'
CLOSING = 'C'


class SymbolingsLogger:
  """Manage the file that contains lines for symbol openings and closings.

  This data will later be used to determine valid SVNRevision ranges
  from which a file can be copied when creating a branch or tag in
  Subversion.  Do this by finding "Openings" and "Closings" for each
  file copied onto a branch or tag.

  An "Opening" is the CVSRevision from which a given branch/tag
  sprouts on a path.

  The "Closing" for that branch/tag and path is the next CVSRevision
  on the same line of development as the opening.

  For example, on file 'foo.c', branch BEE has branch number 1.2.2 and
  obviously sprouts from revision 1.2.  Therefore, 1.2 is the opening
  for BEE on path 'foo.c', and 1.3 is the closing for BEE on path
  'foo.c'.  Note that there may be many revisions chronologically
  between 1.2 and 1.3, for example, revisions on branches of 'foo.c',
  perhaps even including on branch BEE itself.  But 1.3 is the next
  revision *on the same line* as 1.2, that is why it is the closing
  revision for those symbolic names of which 1.2 is the opening.

  The reason for doing all this hullabaloo is to make branch and tag
  creation as efficient as possible by minimizing the number of copies
  and deletes per creation.  For example, revisions 1.2 and 1.3 of
  foo.c might correspond to revisions 17 and 30 in Subversion.  That
  means that when creating branch BEE, there is some motivation to do
  the copy from one of 17-30.  Now if there were another file,
  'bar.c', whose opening and closing CVSRevisions for BEE corresponded
  to revisions 24 and 39 in Subversion, we would know that the ideal
  thing would be to copy the branch from somewhere between 24 and 29,
  inclusive.
  """

  def __init__(self):
    self.symbolings = open(
        artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS), 'w')

  def log_revision(self, cvs_rev, svn_revnum):
    """Log any openings and closings found in CVS_REV."""

    if isinstance(cvs_rev.lod, Branch):
      branch_id = cvs_rev.lod.id
    else:
      branch_id = None

    for (symbol_id, cvs_symbol_id,) in cvs_rev.opened_symbols:
      self._log_opening(
          symbol_id, cvs_symbol_id, svn_revnum, cvs_rev.cvs_file, branch_id
          )

    for (symbol_id, cvs_symbol_id) in cvs_rev.closed_symbols:
      self._log_closing(
          symbol_id, cvs_symbol_id, svn_revnum, cvs_rev.cvs_file, branch_id
          )

  def log_branch_revision(self, cvs_branch, svn_revnum):
    """Log any openings and closings found in CVS_BRANCH."""

    for (symbol_id, cvs_symbol_id,) in cvs_branch.opened_symbols:
      self._log_opening(
          symbol_id, cvs_symbol_id, svn_revnum,
          cvs_branch.cvs_file, cvs_branch.symbol.id
          )

  def _log(
        self, symbol_id, cvs_symbol_id, svn_revnum, cvs_file, branch_id, type
        ):
    """Log an opening or closing to self.symbolings.

    Write out a single line to the symbol_openings_closings file
    representing that SVN_REVNUM of SVN_FILE on BRANCH_ID is either
    the opening or closing (TYPE) of CVS_SYMBOL_ID for SYMBOL_ID.

    TYPE should be one of the following constants: OPENING or CLOSING.

    BRANCH_ID is the symbol id of the branch on which the opening or
    closing occurred, or None if the opening/closing occurred on the
    default branch."""

    if branch_id is None:
      branch_id = '*'
    else:
      branch_id = '%x' % branch_id
    self.symbolings.write(
        '%x %d %s %x %s %x\n'
        % (symbol_id, svn_revnum, type, cvs_symbol_id, branch_id, cvs_file.id)
        )

  def _log_opening(
        self, symbol_id, cvs_symbol_id, svn_revnum, cvs_file, branch_id
        ):
    """Log an opening to self.symbolings.

    See _log() for more information."""

    self._log(
        symbol_id, cvs_symbol_id, svn_revnum, cvs_file, branch_id, OPENING
        )

  def _log_closing(
        self, symbol_id, cvs_symbol_id, svn_revnum, cvs_file, branch_id
        ):
    """Log a closing to self.symbolings.

    See _log() for more information."""

    self._log(
        symbol_id, cvs_symbol_id, svn_revnum, cvs_file, branch_id, CLOSING
        )

  def close(self):
    self.symbolings.close()
    self.symbolings = None


class SymbolingsReader:
  """Provides an interface to retrieve symbol openings and closings.

  This class accesses the SYMBOL_OPENINGS_CLOSINGS_SORTED file and the
  SYMBOL_OFFSETS_DB.  Does the heavy lifting of finding and returning
  the correct opening and closing Subversion revision numbers for a
  given symbolic name and SVN revision number range."""

  def __init__(self):
    """Opens the SYMBOL_OPENINGS_CLOSINGS_SORTED for reading, and
    reads the offsets database into memory."""

    self.symbolings = open(
        artifact_manager.get_temp_file(
            config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
        'r')
    # The offsets_db is really small, and we need to read and write
    # from it a fair bit, so suck it into memory
    offsets_db = file(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB), 'rb')
    # A map from symbol_id to offset.  The values of this map are
    # incremented as the openings and closings for a symbol are
    # consumed.
    self.offsets = cPickle.load(offsets_db)
    offsets_db.close()

  def _generate_lines(self, symbol):
    """Generate the lines for SYMBOL.

    SYMBOL is a TypedSymbol instance.  Yield the tuple (revnum, type,
    cvs_symbol_id, branch_id, cvs_file_id) for all openings and
    closings for SYMBOL."""

    if symbol.id in self.offsets:
      # Set our read offset for self.symbolings to the offset for this
      # symbol:
      self.symbolings.seek(self.offsets[symbol.id])

      while True:
        line = self.symbolings.readline().rstrip()
        if not line:
          break
        id, revnum, type, cvs_symbol_id, branch_id, cvs_file_id = line.split()
        id = int(id, 16)
        revnum = int(revnum)
        if id != symbol.id:
          break
        cvs_symbol_id = int(cvs_symbol_id, 16)
        cvs_file_id = int(cvs_file_id, 16)

        yield (revnum, type, cvs_symbol_id, branch_id, cvs_file_id)

  def get_source_set(self, svn_symbol_commit, svn_revnum):
    """Return the list of possible sources for SVN_SYMBOL_COMMIT.

    SVN_SYMBOL_COMMIT is an SVNSymbolCommit instance and SVN_REVNUM is
    an SVN revision number.  The symbol sources will contain all
    openings and closings for CVSSymbols that occur in
    SVN_SYMBOL_COMMIT.  SVN_REVNUM is only used for an internal
    consistency check."""

    symbol = svn_symbol_commit.symbol

    # A map {svn_path : SVNRevisionRange}:
    openings_closings_map = {}

    for (revnum, type, cvs_symbol_id, branch_id, cvs_file_id) \
            in self._generate_lines(symbol):
      if cvs_symbol_id in svn_symbol_commit.cvs_symbol_ids:
        cvs_symbol = Ctx()._cvs_items_db[cvs_symbol_id]

        svn_path = cvs_symbol.source_lod.get_path(
            cvs_symbol.cvs_file.cvs_path
            )

        range = openings_closings_map.get(svn_path)
        if type == OPENING:
          if revnum >= svn_revnum:
            raise InternalError(
                'Opening in r%d not ready for %s' % (revnum, cvs_symbol,)
                )
          if svn_path in openings_closings_map:
            raise InternalError(
                'Multiple openings logged for %s' % (cvs_symbol,)
                )
          openings_closings_map[svn_path] = SVNRevisionRange(revnum)
        else:
          try:
            range = openings_closings_map[svn_path]
          except KeyError:
            raise InternalError(
                'Closing precedes opening for %s' % (cvs_symbol,)
                )
          if range.closing_revnum is not None:
            raise InternalError(
                'Multiple closings logged for %s' % (cvs_symbol,)
                )
          range.add_closing(revnum)

    return get_source_set(symbol, openings_closings_map)


