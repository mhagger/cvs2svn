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
import database
from openings_closings import OpeningsClosingsMap
from symbolic_name_filling_guide import SymbolicNameFillingGuide


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
    offsets_db = database.Database(
        artifact_manager.get_temp_file(config.SYMBOL_OFFSETS_DB),
        database.DB_OPEN_READ)
    self.offsets = { }
    for key in offsets_db:
      #print " ZOO:", key, offsets_db[key]
      self.offsets[key] = offsets_db[key]

  def filling_guide_for_symbol(self, symbolic_name, svn_revnum):
    """Given SYMBOLIC_NAME and SVN_REVNUM, return a new
    SymbolicNameFillingGuide object.

    Note that if we encounter an opening rev in this fill, but the
    corresponding closing rev takes place later than SVN_REVNUM, the
    closing will not be passed to SymbolicNameFillingGuide in this
    fill (and will be discarded when encountered in a later fill).
    This is perfectly fine, because we can still do a valid fill
    without the closing--we always try to fill what we can as soon as
    we can."""

    openings_closings_map = OpeningsClosingsMap(symbolic_name)

    # It's possible to have a branch start with a file that was added
    # on a branch
    if self.offsets.has_key(symbolic_name):
      # set our read offset for self.symbolings to the offset for
      # symbolic_name
      self.symbolings.seek(self.offsets[symbolic_name])

      while 1:
        fpos = self.symbolings.tell()
        line = self.symbolings.readline().rstrip()
        if not line:
          break
        name, revnum, type, branch_name, cvs_path = line.split(" ", 4)
        if branch_name == '*':
          svn_path = Ctx().project.make_trunk_path(cvs_path)
        else:
          svn_path = Ctx().project.make_branch_path(branch_name, cvs_path)
        revnum = int(revnum)
        if revnum > svn_revnum or name != symbolic_name:
          break
        openings_closings_map.register(svn_path, revnum, type)

      # get current offset of the read marker and set it to the offset
      # for the beginning of the line we just read if we used anything
      # we read.
      if not openings_closings_map.is_empty():
        self.offsets[symbolic_name] = fpos

    return SymbolicNameFillingGuide(openings_closings_map)


