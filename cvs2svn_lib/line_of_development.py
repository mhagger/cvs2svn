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


from boolean import *
from context import Ctx


class LineOfDevelopment:
  """Base class for Trunk and Branch."""

  def is_branch(self):
    raise NotImplemented

  def make_path(self, cvs_file):
    raise NotImplemented


class Trunk(LineOfDevelopment):
  """Represent the main line of development.

  Instances of this class are considered False."""

  def __init__(self):
    pass

  def is_branch(self):
    return False

  def make_path(self, cvs_file):
    return Ctx().project.make_trunk_path(cvs_file.cvs_path)


class Branch(LineOfDevelopment):
  """An object that describes a CVS branch."""

  def __init__(self, name):
    self.name = name

  def is_branch(self):
    return True

  def make_path(self, cvs_file):
    return Ctx().project.make_branch_path(self.name, cvs_file.cvs_path)


