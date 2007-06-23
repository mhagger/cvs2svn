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
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSRevisionModification
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

    # This keys of this dictionary are *source* cvs_file.ids for which
    # we've encountered an 'opening' on the default branch.  The
    # values are the ids of symbols that this path has opened.
    self._open_files_with_default_branches = { }

  def log_revision(self, cvs_rev, svn_revnum):
    """Log any openings and closings found in CVS_REV."""

    if isinstance(cvs_rev.lod, Branch):
      branch_id = cvs_rev.lod.id
    else:
      branch_id = None

    for id in cvs_rev.tag_ids + cvs_rev.branch_ids:
      symbol = Ctx()._cvs_items_db[id].symbol
      self._note_default_branch_opening(cvs_rev, symbol.id)
      if isinstance(cvs_rev, CVSRevisionModification):
        self._log_opening(symbol.id, svn_revnum, cvs_rev.cvs_file, branch_id)

    for symbol_id in cvs_rev.closed_symbol_ids:
      self._log_closing(symbol_id, svn_revnum, cvs_rev.cvs_file, branch_id)

  def log_branch_revision(self, cvs_branch, svn_revnum):
    """Log any openings and closings found in CVS_BRANCH."""

    # Determine whether the revision originally being branched was a
    # CVSRevisionDelete, because if it was then it does not count as
    # an opening:
    source = Ctx()._cvs_items_db[cvs_branch.source_id]
    while not isinstance(source, CVSRevision):
      source = Ctx()._cvs_items_db[source.source_id]

    if isinstance(source, CVSRevisionModification):
      for id in cvs_branch.tag_ids + cvs_branch.branch_ids:
        cvs_symbol = Ctx()._cvs_items_db[id]
        self._log_opening(
            cvs_symbol.symbol.id,
            svn_revnum, cvs_branch.cvs_file, cvs_branch.symbol.id)

  def _log(self, symbol_id, svn_revnum, cvs_file, branch_id, type):
    """Log an opening or closing to self.symbolings.

    Write out a single line to the symbol_openings_closings file
    representing that SVN_REVNUM of SVN_FILE on BRANCH_ID is either
    the opening or closing (TYPE) of the symbol with id SYMBOL_ID.

    TYPE should be one of the following constants: OPENING or CLOSING.

    BRANCH_ID is the symbol id of the branch on which the opening or
    closing occurred, or None if the opening/closing occurred on the
    default branch."""

    if branch_id is None:
      branch_id = '*'
    else:
      branch_id = '%x' % branch_id
    self.symbolings.write(
        '%x %d %s %s %x\n'
        % (symbol_id, svn_revnum, type, branch_id, cvs_file.id))

  def _log_opening(self, symbol_id, svn_revnum, cvs_file, branch_id):
    """Log an opening to self.symbolings.

    See _log() for more information."""

    self._log(symbol_id, svn_revnum, cvs_file, branch_id, OPENING)

  def _log_closing(self, symbol_id, svn_revnum, cvs_file, branch_id):
    """Log a closing to self.symbolings.

    See _log() for more information."""

    self._log(symbol_id, svn_revnum, cvs_file, branch_id, CLOSING)

  def close(self):
    self.symbolings.close()
    self.symbolings = None

  def _note_default_branch_opening(self, cvs_rev, symbol_id):
    """If CVS_REV is a default branch revision, log
    CVS_REV.cvs_file.id as an opening for SYMBOL_ID."""

    self._open_files_with_default_branches.setdefault(
        cvs_rev.cvs_file.id, []).append(symbol_id)

  def log_default_branch_closing(self, cvs_rev, svn_revnum):
    """If self._open_files_with_default_branches contains
    CVS_REV.cvs_file.id, then log a closing for each symbol in
    self._open_files_with_default_branches[CVS_REV.cvs_file.id] with
    SVN_REVNUM as the closing revision number."""

    cvs_file_id = cvs_rev.cvs_file.id
    if cvs_file_id in self._open_files_with_default_branches:
      # log each symbol as a closing
      for symbol_id in self._open_files_with_default_branches[cvs_file_id]:
        self._log_closing(symbol_id, svn_revnum, cvs_rev.cvs_file, None)
      # Remove them from the openings list as we're done with them.
      del self._open_files_with_default_branches[cvs_file_id]


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

  def _generate_lines(self, symbol, svn_revnum):
    """Generate the lines for SYMBOL with SVN revisions <= SVN_REVNUM.

    SYMBOL is a TypedSymbol instance and SVN_REVNUM is an SVN revision
    number.  Yield the tuple (revnum, type, branch_id, cvs_file_id)
    for all openings and closings for SYMBOL between the SVN_REVNUM
    parameter passed to the last call to this method() and the value
    of SVN_REVNUM passed to this call.

    Adjust self.offsets[SUMBOL.id] to point past the lines that are
    generated.  This generator should always be allowed to run to
    completion."""

    if symbol.id in self.offsets:
      # Set our read offset for self.symbolings to the offset for this
      # symbol:
      self.symbolings.seek(self.offsets[symbol.id])

      while True:
        fpos = self.symbolings.tell()
        line = self.symbolings.readline().rstrip()
        if not line:
          del self.offsets[symbol.id]
          break
        id, revnum, type, branch_id, cvs_file_id = line.split()
        id = int(id, 16)
        revnum = int(revnum)
        if id != symbol.id:
          del self.offsets[symbol.id]
          break
        elif revnum > svn_revnum:
          # Update offset for this symbol to the first unused line:
          self.offsets[symbol.id] = fpos
          break
        cvs_file_id = int(cvs_file_id, 16)

        yield (revnum, type, branch_id, cvs_file_id)

  def get_source_set(self, symbol, svn_revnum):
    """Return the list of possible sources for SYMBOL.

    SYMBOL is a TypedSymbol instance and SVN_REVNUM is an SVN revision
    number.  The symbol sources will contain all openings and closings
    for SYMBOL between the SVN_REVNUM parameter passed to the last
    call to this method and value of SVN_REVNUM passed to this call.

    Note that if we encounter an opening rev in this fill, but the
    corresponding closing rev takes place later than SVN_REVNUM, the
    closing will not be passed to get_source_set() in this fill (and
    will be discarded when encountered in a later fill).  This is
    perfectly fine, because we can still do a valid fill without the
    closing--we always try to fill what we can as soon as we can."""

    # A map {svn_path : SVNRevisionRange}:
    openings_closings_map = {}

    for (revnum, type, branch_id, cvs_file_id) \
            in self._generate_lines(symbol, svn_revnum):
      cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)

      if branch_id == '*':
        svn_path = cvs_file.project.get_trunk_path(cvs_file.cvs_path)
      else:
        branch_id = int(branch_id, 16)
        branch = Ctx()._symbol_db.get_symbol(branch_id)
        svn_path = cvs_file.project.get_branch_path(branch, cvs_file.cvs_path)

      if type == OPENING:
        # Always log an OPENING, even if it overwrites a previous
        # OPENING/CLOSING:
        openings_closings_map[svn_path] = SVNRevisionRange(revnum)
      else:
        # Only register a CLOSING if a corresponding OPENING has
        # already been recorded:
        range = openings_closings_map.get(svn_path)
        if range is not None:
          range.add_closing(revnum)

    return get_source_set(symbol, openings_closings_map)


