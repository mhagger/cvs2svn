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

"""This module contains the SymbolDatabase class."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import PDatabase


class Symbol:
  def __init__(self, id, name):
    self.id = id
    self.name = name


class BranchSymbol(Symbol):
  pass


class TagSymbol(Symbol):
  pass


class SymbolDatabase:
  """A Database to record symbolic names (tags and branches).

  Records are name -> symbol, where symbol is a Symbol instance."""

  def __init__(self, mode):
    self.db = PDatabase(
        artifact_manager.get_temp_file(config.SYMBOL_DB), mode)

  def add(self, symbol):
    self.db[symbol.name] = symbol

  def get_symbol(self, name):
    return self.db[name]


