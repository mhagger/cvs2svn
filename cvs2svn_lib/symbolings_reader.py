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
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import Database
from cvs2svn_lib.database import DB_OPEN_READ
from cvs2svn_lib.openings_closings import OpeningsClosingsMap
from cvs2svn_lib.symbol_filling_guide import SymbolFillingGuide


class SymbolingsReader:
  """Provides an interface to the SYMBOL_OPENINGS_CLOSINGS_SORTED file
  and the SYMBOL_OFFSETS_DB.  Does the heavy lifting of finding and
  returning the correct opening and closing Subversion revision
  numbers for a given symbolic name."""

  def __init__(self):
    """Opens the SYMBOL_OPENINGS_CLOSINGS_SORTED for reading, and
    reads the offsets database into memory."""

    self.symbolings = open(
        artifact_manager.get_temp_file(
            config.SYMBOL_OPENINGS_CLOSINGS_SORTED),
        'r')
    # The offsets_db is really small, and we need to read and write
    # from it a fair bit, so suck it into memory
    offsets_db = Database(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB),
        DB_OPEN_READ)
    # A map from symbol_id to offset.
    self.offsets = { }
    for key in offsets_db:
      symbol_id = int(key, 16)
      self.offsets[symbol_id] = offsets_db[key]

  def filling_guide_for_symbol(self, symbol, svn_revnum):
    """Given SYMBOL and SVN_REVNUM, return a new SymbolFillingGuide object.

    SYMBOL is a Symbol instance.  Note that if we encounter an opening
    rev in this fill, but the corresponding closing rev takes place
    later than SVN_REVNUM, the closing will not be passed to
    SymbolFillingGuide in this fill (and will be discarded when
    encountered in a later fill).  This is perfectly fine, because we
    can still do a valid fill without the closing--we always try to
    fill what we can as soon as we can."""

    openings_closings_map = OpeningsClosingsMap(symbol)

    # It's possible to have a branch start with a file that was added
    # on a branch
    if symbol.id in self.offsets:
      # Set our read offset for self.symbolings to the offset for this
      # symbol:
      self.symbolings.seek(self.offsets[symbol.id])

      while 1:
        fpos = self.symbolings.tell()
        line = self.symbolings.readline().rstrip()
        if not line:
          break
        id, revnum, type, branch_id, cvs_file_id = line.split()
        id = int(id, 16)
        cvs_file_id = int(cvs_file_id, 16)
        cvs_file = Ctx()._cvs_file_db.get_file(cvs_file_id)
        if branch_id == '*':
          svn_path = Ctx().project.make_trunk_path(cvs_file.cvs_path)
        else:
          branch_id = int(branch_id, 16)
          svn_path = Ctx().project.make_branch_path(
              Ctx()._symbol_db.get_name(branch_id), cvs_file.cvs_path)
        revnum = int(revnum)
        if revnum > svn_revnum or id != symbol.id:
          break
        openings_closings_map.register(svn_path, revnum, type)

      # get current offset of the read marker and set it to the offset
      # for the beginning of the line we just read if we used anything
      # we read.
      if not openings_closings_map.is_empty():
        self.offsets[symbol.id] = fpos

    return SymbolFillingGuide(openings_closings_map)


