# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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


import cPickle

from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.svn_revision_range import SVNRevisionRange


# Constants used in SYMBOL_OPENINGS_CLOSINGS
OPENING = 'O'
CLOSING = 'C'


class SymbolingsLogger:
  """Manage the file that contains lines for symbol openings and closings.

  This data will later be used to determine valid SVNRevision ranges
  from which a file can be copied when creating a branch or tag in
  Subversion.  Do this by finding 'Openings' and 'Closings' for each
  file copied onto a branch or tag.

  An 'Opening' is the beginning of the lifetime of the source
  (CVSRevision or CVSBranch) from which a given CVSSymbol sprouts.

  The 'Closing' is the SVN revision when the source is deleted or
  overwritten.

  For example, on file 'foo.c', branch BEE has branch number 1.2.2 and
  obviously sprouts from revision 1.2.  Therefore, the SVN revision
  when 1.2 is committed is the opening for BEE on path 'foo.c', and
  the SVN revision when 1.3 is committed is the closing for BEE on
  path 'foo.c'.  Note that there may be many revisions chronologically
  between 1.2 and 1.3, for example, revisions on branches of 'foo.c',
  perhaps even including on branch BEE itself.  But 1.3 is the next
  revision *on the same line* as 1.2, that is why it is the closing
  revision for those symbolic names of which 1.2 is the opening.

  The reason for doing all this hullabaloo is (1) to determine what
  range of SVN revision numbers can be used as the source of a copy of
  a particular file onto a branch/tag, and (2) to minimize the number
  of copies and deletes per creation by choosing source SVN revision
  numbers that can be used for as many files as possible.

  For example, revisions 1.2 and 1.3 of foo.c might correspond to
  revisions 17 and 30 in Subversion.  That means that when creating
  branch BEE, foo.c has to be copied from a Subversion revision number
  in the range 17 <= revnum < 30.  Now if there were another file,
  'bar.c', in the same directory, and 'bar.c's opening and closing for
  BEE correspond to revisions 24 and 39 in Subversion, then we can
  kill two birds with one stone by copying the whole directory from
  somewhere in the range 24 <= revnum < 30."""

  def __init__(self):
    self.symbolings = open(
        artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS), 'w')

  def log_revision(self, cvs_rev, svn_revnum):
    """Log any openings and closings found in CVS_REV."""

    for (symbol_id, cvs_symbol_id,) in cvs_rev.opened_symbols:
      self._log_opening(symbol_id, cvs_symbol_id, svn_revnum)

    for (symbol_id, cvs_symbol_id) in cvs_rev.closed_symbols:
      self._log_closing(symbol_id, cvs_symbol_id, svn_revnum)

  def log_branch_revision(self, cvs_branch, svn_revnum):
    """Log any openings and closings found in CVS_BRANCH."""

    for (symbol_id, cvs_symbol_id,) in cvs_branch.opened_symbols:
      self._log_opening(symbol_id, cvs_symbol_id, svn_revnum)

  def _log(self, symbol_id, cvs_symbol_id, svn_revnum, type):
    """Log an opening or closing to self.symbolings.

    Write out a single line to the symbol_openings_closings file
    representing that SVN_REVNUM is either the opening or closing
    (TYPE) of CVS_SYMBOL_ID for SYMBOL_ID.

    TYPE should be one of the following constants: OPENING or CLOSING."""

    self.symbolings.write(
        '%x %d %s %x\n' % (symbol_id, svn_revnum, type, cvs_symbol_id)
        )

  def _log_opening(self, symbol_id, cvs_symbol_id, svn_revnum):
    """Log an opening to self.symbolings.

    See _log() for more information."""

    self._log(symbol_id, cvs_symbol_id, svn_revnum, OPENING)

  def _log_closing(self, symbol_id, cvs_symbol_id, svn_revnum):
    """Log a closing to self.symbolings.

    See _log() for more information."""

    self._log(symbol_id, cvs_symbol_id, svn_revnum, CLOSING)

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

  def close(self):
    self.symbolings.close()
    del self.symbolings
    del self.offsets

  def _generate_lines(self, symbol):
    """Generate the lines for SYMBOL.

    SYMBOL is a TypedSymbol instance.  Yield the tuple (revnum, type,
    cvs_symbol_id) for all openings and closings for SYMBOL."""

    if symbol.id in self.offsets:
      # Set our read offset for self.symbolings to the offset for this
      # symbol:
      self.symbolings.seek(self.offsets[symbol.id])

      while True:
        line = self.symbolings.readline().rstrip()
        if not line:
          break
        (id, revnum, type, cvs_symbol_id) = line.split()
        id = int(id, 16)
        revnum = int(revnum)
        if id != symbol.id:
          break
        cvs_symbol_id = int(cvs_symbol_id, 16)

        yield (revnum, type, cvs_symbol_id)

  def get_range_map(self, svn_symbol_commit):
    """Return the ranges of all CVSSymbols in SVN_SYMBOL_COMMIT.

    Return a map { CVSSymbol : SVNRevisionRange }."""

    # A map { cvs_symbol_id : CVSSymbol }:
    cvs_symbol_map = {}
    for cvs_symbol in svn_symbol_commit.get_cvs_items():
      cvs_symbol_map[cvs_symbol.id] = cvs_symbol

    range_map = {}

    for (revnum, type, cvs_symbol_id) \
            in self._generate_lines(svn_symbol_commit.symbol):
      cvs_symbol = cvs_symbol_map.get(cvs_symbol_id)
      if cvs_symbol is None:
        # This CVSSymbol is not part of SVN_SYMBOL_COMMIT.
        continue
      range = range_map.get(cvs_symbol)
      if type == OPENING:
        if range is not None:
          raise InternalError(
              'Multiple openings logged for %r' % (cvs_symbol,)
              )
        range_map[cvs_symbol] = SVNRevisionRange(
            cvs_symbol.source_lod, revnum
            )
      else:
        if range is None:
          raise InternalError(
              'Closing precedes opening for %r' % (cvs_symbol,)
              )
        if range.closing_revnum is not None:
          raise InternalError(
              'Multiple closings logged for %r' % (cvs_symbol,)
              )
        range.add_closing(revnum)

    # Make sure that all CVSSymbols are accounted for, and adjust the
    # closings to be not later than svn_symbol_commit.revnum.
    for cvs_symbol in cvs_symbol_map.itervalues():
      try:
        range = range_map[cvs_symbol]
      except KeyError:
        raise InternalError('No opening for %s' % (cvs_symbol,))

      if range.opening_revnum >= svn_symbol_commit.revnum:
        raise InternalError(
            'Opening in r%d not ready for %s in r%d'
            % (range.opening_revnum, cvs_symbol, svn_symbol_commit.revnum,)
            )

      if range.closing_revnum is not None \
             and range.closing_revnum > svn_symbol_commit.revnum:
        range.closing_revnum = None

    return range_map


