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


import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager


class Symbol:
  def __init__(self, id, name):
    self.id = id
    self.name = name

  def __cmp__(self, other):
    return cmp(self.id, other.id)

  def __hash__(self):
    return self.id

  def __str__(self):
    return self.name

  def __repr__(self):
    return '%s <%x>' % (self, self.id,)

  def get_clean_name(self):
    """Return self.name, translating characters that Subversion does
    not allow in a pathname.

    Since the unofficial set also includes [/\] we need to translate
    those into ones that don't conflict with Subversion
    limitations."""

    name = self.name
    name = name.replace('/','++')
    name = name.replace('\\','--')
    return name


class BranchSymbol(Symbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Branch %r' % (self.name,)


class TagSymbol(Symbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Tag %r' % (self.name,)


class ExcludedSymbol(Symbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'ExcludedSymbol %r' % (self.name, self.id,)


class SymbolDatabase:
  """Read-only access to symbol database.

  The primary lookup mechanism is name -> symbol, where symbol is a
  Symbol instance.  The whole database is read into memory upon
  construction."""

  def __init__(self):
    # A map { id : Symbol }
    self._symbols = {}

    # A map { name : Symbol }
    self._symbols_by_name = {}

    f = open(artifact_manager.get_temp_file(config.SYMBOL_DB), 'rb')
    symbols = cPickle.load(f)
    f.close()
    for symbol in symbols:
      self._symbols[symbol.id] = symbol
      self._symbols_by_name[symbol.name] = symbol

  def get_symbol(self, id):
    """Return the symbol instance with id ID.

    Raise KeyError if the symbol is not known."""

    return self._symbols[id]

  def get_symbol_by_name(self, name):
    """Return the symbol instance with name NAME.

    Return None if there is no such instance (for example, if NAME is
    being excluded from the conversion)."""

    return self._symbols_by_name.get(name)

  def get_id(self, name):
    """Return the id of the symbol with the specified NAME.

    Raise a KeyError if there is no such symbol."""

    return self._symbols_by_name[name].id

  def get_name(self, id):
    """Return the name of the symbol with the specified ID.

    Raise a KeyError if there is no such symbol."""

    return self._symbols[id].name

  def collate_symbols(self, ids):
    """Given an iterable of symbol ids, divide them into branches and tags.

    Return a tuple of two lists (branches, tags), containing the
    Symbol objects of symbols that should be converted as branches and
    tags respectively.  Symbols that we do not know about are not
    included in either output list."""

    branches = []
    tags = []
    for id in ids:
      symbol = self.get_symbol(id)
      if isinstance(symbol, BranchSymbol):
        branches.append(symbol)
      elif isinstance(symbol, TagSymbol):
        tags.append(symbol)

    return (branches, tags,)


def create_symbol_database(symbols):
  """Create and fill a symbol database.

  Record each symbol that is listed in SYMBOLS, which is an iterable
  containing Symbol objects."""

  f = open(artifact_manager.get_temp_file(config.SYMBOL_DB), 'wb')
  cPickle.dump(symbols, f, -1)
  f.close()

