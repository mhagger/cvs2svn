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

"""This module contains classes to represent symbols."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import path_join


class Symbol:
  def __init__(self, id, project, name):
    self.id = id
    self.project = project
    self.name = name

  def __cmp__(self, other):
    return cmp(self.project, other.project) or cmp(self.id, other.id)

  def __hash__(self):
    return hash( (self.project, self.id,) )

  def __str__(self):
    return self.name

  def __repr__(self):
    return '%s <%x>' % (self, self.id,)

  def __getstate__(self):
    return (self.id, self.project.id, self.name,)

  def __setstate__(self, state):
    (self.id, project_id, self.name,) = state
    self.project = Ctx().projects[project_id]

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


class IncludedSymbol(TypedSymbol):
  """A TypedSymbol that will be included in the conversion."""

  def get_path(self, *components):
    """Return the svn path for this symbol."""

    raise NotImplementedError()


class BranchSymbol(IncludedSymbol):
  def get_path(self, *components):
    return path_join(self.project.get_branch_path(self), *components)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Branch %r' % (self.name,)


class TagSymbol(IncludedSymbol):
  def get_path(self, *components):
    return path_join(self.project.get_tag_path(self), *components)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Tag %r' % (self.name,)


class ExcludedSymbol(TypedSymbol):
  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'ExcludedSymbol %r' % (self.name,)


