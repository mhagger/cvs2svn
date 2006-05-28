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
from cvs2svn_lib.database import DB_OPEN_READ
from cvs2svn_lib.database import DB_OPEN_NEW
from cvs2svn_lib.database import PDatabase


class Symbol:
  def __init__(self, id, name):
    self.id = id
    self.name = name


class BranchSymbol(Symbol):
  pass


class TagSymbol(Symbol):
  pass


class _NewSymbolDatabase:
  """A Database to record symbolic names (tags and branches).

  Records are name -> symbol, where symbol is a Symbol instance."""

  def __init__(self):
    self.db = PDatabase(
        artifact_manager.get_temp_file(config.SYMBOL_DB), DB_OPEN_NEW)

  def add(self, symbol):
    self.db[symbol.name] = symbol


class _OldSymbolDatabase:
  """Read-only access to symbol database.

  Records are name -> symbol, where symbol is a Symbol instance.  The
  whole database is read into memory upon construction."""

  def __init__(self):
    self._names = {}
    db = PDatabase(
        artifact_manager.get_temp_file(config.SYMBOL_DB), DB_OPEN_READ)
    for name in db.keys():
      symbol = db[name]
      self._names[name] = symbol

  def get_symbol(self, name):
    return self._names[name]


def SymbolDatabase(mode):
  """Open the SymbolDatabase in either NEW or READ mode.

  The class of the instance that is returned depends on MODE."""

  if mode == DB_OPEN_NEW:
    return _NewSymbolDatabase()
  elif mode == DB_OPEN_READ:
    return _OldSymbolDatabase()
  else:
    raise NotImplemented


