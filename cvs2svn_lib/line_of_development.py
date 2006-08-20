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

"""This module contains classes to store CVS branches."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx


class LineOfDevelopment:
  """Base class for Trunk and Branch."""

  def make_path(self, cvs_file):
    raise NotImplemented


class Trunk(LineOfDevelopment):
  """Represent the main line of development."""

  def __init__(self):
    pass

  def make_path(self, cvs_file):
    return cvs_file.project.make_trunk_path(cvs_file.cvs_path)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Trunk'


class Branch(LineOfDevelopment):
  """An object that describes a CVS branch."""

  def __init__(self, symbol):
    self.symbol = symbol
    self.id = symbol.id
    self.name = symbol.name

  def make_path(self, cvs_file):
    return cvs_file.project.make_branch_path(self.symbol, cvs_file.cvs_path)

  def __str__(self):
    """For convenience only.  The format is subject to change at any time."""

    return 'Branch %r <%x>' % (self.name, self.id,)


