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

"""This module contains classes that represent trunk, branches, and tags.

The classes in this module represent several concepts related to
symbols and lines of development in the abstract; that is, not within
a particular file, but across all files in a project.

The classes in this module are organized into the following class
hierarchy:

AbstractSymbol
  |
  +--LineOfDevelopment
  |    |
  |    +--Trunk
  |    |
  |    +--IncludedSymbol (also inherits from TypedSymbol)
  |         |
  |         +--Branch
  |         |
  |         +--Tag
  |
  +--Symbol
       |
       +--TypedSymbol
            |
            +--IncludedSymbol (also inherits from LineOfDevelopment)
            |    |
            |    +--Branch
            |    |
            |    +--Tag
            |
            +--ExcludedSymbol

Please note the use of multiple inheritance.

All AbstractSymbols contain an id that is globally unique across all
AbstractSymbols.  Moreover, the id of an AbstractSymbol remains the
same even if the symbol is mutated (as described below), and two
AbstractSymbols are considered equal iff their ids are the same, even
if the two instances have different types.  Symbols in different
projects always have different ids and are therefore always distinct.
(Indeed, this is pretty much the defining characteristic of a
project.)  Even if, for example, two projects each have branches with
the same name, the Symbols representing the branches are distinct and
have distinct ids.  (This is important to avoid having to rewrite
databases with new symbol ids in CollateSymbolsPass.)

AbstractSymbols are all initially created in CollectRevsPass as either
Trunk or Symbol instances.  A Symbol instance is essentially an
undifferentiated Symbol.

In CollateSymbolsPass, it is decided which symbols will be converted
as branches, which as tags, and which excluded altogether.  At the
beginning of this pass, the symbols are all represented by instances
of the non-specific Symbol class.  During CollateSymbolsPass, each
Symbol instance is replaced by an instance of Branch, Tag, or
ExcludedSymbol with the same id.  (Trunk instances are left
unchanged.)  At the end of CollateSymbolsPass, all ExcludedSymbols are
discarded and processing continues with only Trunk, Branch, and Tag
instances.  These three classes inherit from LineOfDevelopment;
therefore, in later passes the term LineOfDevelopment (abbreviated to
LOD) is used to refer to such objects."""


from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import path_join


class AbstractSymbol:
  """Base class for all other classes in this file."""

  def __init__(self, id, project):
    self.id = id
    self.project = project

  def __hash__(self):
    return self.id

  def __eq__(self, other):
    return self.id == other.id


class LineOfDevelopment(AbstractSymbol):
  """Base class for Trunk, Branch, and Tag.

  This is basically the abstraction for what will be a root tree in
  the Subversion repository."""

  def __init__(self, id, project):
    AbstractSymbol.__init__(self, id, project)
    self.base_path = None

  def get_path(self, *components):
    """Return the svn path for this LineOfDevelopment."""

    return path_join(self.base_path, *components)


class Trunk(LineOfDevelopment):
  """Represent the main line of development."""

  def __getstate__(self):
    return (self.id, self.project.id, self.base_path,)

  def __setstate__(self, state):
    (self.id, project_id, self.base_path,) = state
    self.project = Ctx()._projects[project_id]

  def __cmp__(self, other):
    if isinstance(other, Trunk):
      return cmp(self.project, other.project)
    elif isinstance(other, Symbol):
      # Allow Trunk to compare less than Symbols:
      return -1
    else:
      raise NotImplementedError()

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Trunk'

  def __repr__(self):
    return '%s<%x>' % (self, self.id,)


class Symbol(AbstractSymbol):
  """Represents a symbol within one project in the CVS repository.

  Instance of the Symbol class itself are used to represent symbols
  from the CVS repository.  CVS, of course, distinguishes between
  normal tags and branch tags, but we allow symbol types to be changed
  in CollateSymbolsPass.  Therefore, we store all CVS symbols as
  Symbol instances at the beginning of the conversion.

  In CollateSymbolsPass, Symbols are replaced by Branches, Tags, and
  ExcludedSymbols (the latter being discarded at the end of that
  pass)."""

  def __init__(self, id, project, name, preferred_parent_id=None):
    AbstractSymbol.__init__(self, id, project)
    self.name = name

    # If this symbol has a preferred parent, this member is the id of
    # the LineOfDevelopment instance representing it.  If the symbol
    # never appeared in a CVSTag or CVSBranch (for example, because
    # all of the branches on this LOD have been detached from the
    # dependency tree), then this field is set to None.  This field is
    # set during FilterSymbolsPass.
    self.preferred_parent_id = preferred_parent_id

  def __getstate__(self):
    return (self.id, self.project.id, self.name, self.preferred_parent_id,)

  def __setstate__(self, state):
    (self.id, project_id, self.name, self.preferred_parent_id,) = state
    self.project = Ctx()._projects[project_id]

  def __cmp__(self, other):
    if isinstance(other, Symbol):
      return cmp(self.project, other.project) \
             or cmp(self.name, other.name) \
             or cmp(self.id, other.id)
    elif isinstance(other, Trunk):
      # Allow Symbols to compare greater than Trunk:
      return +1
    else:
      raise NotImplementedError()

  def __str__(self):
    return self.name

  def __repr__(self):
    return '%s<%x>' % (self, self.id,)


class TypedSymbol(Symbol):
  """A Symbol whose type (branch, tag, or excluded) has been decided."""

  def __init__(self, symbol):
    Symbol.__init__(
        self, symbol.id, symbol.project, symbol.name,
        symbol.preferred_parent_id,
        )


class IncludedSymbol(TypedSymbol, LineOfDevelopment):
  """A TypedSymbol that will be included in the conversion."""

  def __init__(self, symbol):
    TypedSymbol.__init__(self, symbol)
    # We can't call the LineOfDevelopment constructor, so initialize
    # its extra member explicitly:
    try:
      # If the old symbol had a base_path set, then use it:
      self.base_path = symbol.base_path
    except AttributeError:
      self.base_path = None

  def __getstate__(self):
    return (TypedSymbol.__getstate__(self), self.base_path,)

  def __setstate__(self, state):
    (super_state, self.base_path,) = state
    TypedSymbol.__setstate__(self, super_state)


class Branch(IncludedSymbol):
  """An object that describes a CVS branch."""

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Branch(%r)' % (self.name,)


class Tag(IncludedSymbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Tag(%r)' % (self.name,)


class ExcludedSymbol(TypedSymbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'ExcludedSymbol(%r)' % (self.name,)


