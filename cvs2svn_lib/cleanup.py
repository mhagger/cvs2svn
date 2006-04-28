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


from __future__ import generators

import os

from boolean import *
from context import Ctx
from log import Log


class Cleanup:
  """This singleton class manages any files created by cvs2svn.  When
  you first create a file, call Cleanup.register, passing the
  filename, and the last pass that you need the file.  After the end
  of that pass, your file will be cleaned up.  This class is a Borg,
  see http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531."""

  __shared_state = {}

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    self._log = {}

  def register(self, file, which_pass):
    """Register FILE for cleanup at the end of WHICH_PASS.
    Registering a given FILE is idempotent; you may register as many
    times as you wish, but it will only be cleaned up once.

    Note that if you register a database file you must close the
    database before cleanup."""

    self._log.setdefault(which_pass, {})[file] = 1

  def temp(self, basename, which_pass=None):
    """Return a temporary filename based on BASENAME in Ctx().tmpdir,
    and schedule its cleanup at the end of WHICH_PASS.  See register()
    for more information.  If WHICH_PASS is None, do not schedule the
    file to be cleaned up."""

    filename = os.path.join(Ctx().tmpdir, basename)
    if which_pass is not None:
      self.register(filename, which_pass)
    return filename

  def cleanup(self, which_pass):
    """Clean up all files, for pass WHICH_PASS."""

    if not self._log.has_key(which_pass):
      return
    for file in self._log[which_pass]:
      Log().write(Log.VERBOSE, "Deleting", file)
      os.unlink(file)


