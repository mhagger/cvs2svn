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

"""This module contains the SymbolDatabase class."""


import cPickle

from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager


class SymbolDatabase:
  """Read-only access to symbol database.

  This class allows iteration and lookups id -> symbol, where symbol
  is a TypedSymbol instance.  The whole database is read into memory
  upon construction."""

  def __init__(self):
    # A map { id : TypedSymbol }
    self._symbols = {}

    f = open(artifact_manager.get_temp_file(config.SYMBOL_DB), 'rb')
    symbols = cPickle.load(f)
    f.close()
    for symbol in symbols:
      self._symbols[symbol.id] = symbol

  def get_symbol(self, id):
    """Return the symbol instance with id ID.

    Raise KeyError if the symbol is not known."""

    return self._symbols[id]

  def __iter__(self):
    """Iterate over the Symbol instances within this database."""

    return self._symbols.itervalues()

  def close(self):
    self._symbols = None


def create_symbol_database(symbols):
  """Create and fill a symbol database.

  Record each symbol that is listed in SYMBOLS, which is an iterable
  containing Trunk and TypedSymbol objects."""

  f = open(artifact_manager.get_temp_file(config.SYMBOL_DB), 'wb')
  cPickle.dump(symbols, f, -1)
  f.close()

