# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

The classes in this module represent lines of development, or LODs for
short.  Trunk, Branches, and Tags are all LODs.

Symbols include Branches and Tags.  Each Symbol has an identifier that
is unique across the whole conversion, and multiple instances
representing the same abstract Symbol have the same identifier.  The
Symbols in one project are distinct from those in another project, and
have non-overlapping ids.  Even if, for example, two projects each
have branches with the same name, the branches are considered
distinct.

Prior to CollateSymbolsPass, it is not known which symbols will be
converted as branches and which as tags.  In this phase, the symbols
are all represented by instances of the non-specific Symbol class.
During CollateSymbolsPass, the Symbol instances are replaced by
instances of Branch or Tag.  But the ids are preserved even when the
symbols are converted.  (This is important to avoid having to rewrite
databases with new symbol ids in CollateSymbolsPass.)  In particular,
it is possible that a Symbol, Branch, and Tag instance all have the
same id, in which case they are all considered equal.

Trunk instances do not have ids, but Trunk objects can be compared to
Symbol objects (trunks always compare less than symbols)."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import path_join


class LineOfDevelopment:
  """Base class for Trunk, Branch, and Tag."""

  def get_path(self, *components):
    """Return the svn path for this LineOfDevelopment."""

    raise NotImplementedError()


class Trunk(LineOfDevelopment):
  """Represent the main line of development."""

  def __init__(self, id, project):
    self.id = id
    self.project = project

  def __getstate__(self):
    return (self.id, self.project.id,)

  def __setstate__(self, state):
    (self.id, project_id,) = state
    self.project = Ctx().projects[project_id]

  def __eq__(self, other):
    return isinstance(other, Trunk) and self.project == other.project

  def __cmp__(self, other):
    if isinstance(other, Trunk):
      return cmp(self.project, other.project)
    else:
      # Allow Trunk to compare less than Symbols:
      return -1

  def __hash__(self):
    return hash(self.project)

  def get_path(self, *components):
    return self.project.get_trunk_path(*components)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Trunk'

  def __repr__(self):
    return '%s<%x>' % (self, self.id,)


class Symbol:
  def __init__(self, id, project, name):
    self.id = id
    self.project = project
    self.name = name

    # If this symbol has a preferred parent, this member is the id of
    # the LineOfDevelopment instance representing it.  If the symbol
    # never appeared in a CVSTag or CVSBranch (for example, because
    # all of the branches on this LOD have been detached from the
    # dependency tree), then this field is set to None.  This field is
    # set during FilterSymbolsPass.
    self.preferred_parent_id = None

  def __getstate__(self):
    return (self.id, self.project.id, self.name, self.preferred_parent_id,)

  def __setstate__(self, state):
    (self.id, project_id, self.name, self.preferred_parent_id,) = state
    self.project = Ctx().projects[project_id]

  def __eq__(self, other):
    return isinstance(other, Symbol) and self.id == other.id

  def __cmp__(self, other):
    if isinstance(other, Symbol):
      return cmp(self.project, other.project) \
             or cmp(self.name, other.name) \
             or cmp(self.id, other.id)
    else:
      # Allow Symbols to compare greater than Trunk:
      return +1

  def __hash__(self):
    return self.id

  def __str__(self):
    return self.name

  def __repr__(self):
    return '%s<%x>' % (self, self.id,)

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


class TypedSymbol(Symbol):
  """A Symbol whose type (branch, tag, or excluded) has been decided."""

  def __init__(self, symbol):
    Symbol.__init__(self, symbol.id, symbol.project, symbol.name)


class IncludedSymbol(TypedSymbol, LineOfDevelopment):
  """A TypedSymbol that will be included in the conversion."""

  pass


class Branch(IncludedSymbol):
  """An object that describes a CVS branch."""

  def get_path(self, *components):
    return self.project.get_branch_path(self, *components)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Branch(%r)' % (self.name,)


class Tag(IncludedSymbol):
  def get_path(self, *components):
    return self.project.get_tag_path(self, *components)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Tag(%r)' % (self.name,)


class ExcludedSymbol(TypedSymbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'ExcludedSymbol(%r)' % (self.name,)


