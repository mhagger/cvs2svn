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

"""This module contains a simple logging facility for cvs2svn."""


import sys
import time

from cvs2svn_lib.boolean import *


class Log:
  """A Simple logging facility.

  Each line will be timestamped if self.use_timestamps is True.  This
  class is a Borg, see
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531."""

  # These constants represent the log levels that this class supports.
  # The increase_verbosity() and decrease_verbosity() methods rely on
  # these constants being consecutive integers:
  WARN = -1
  QUIET = 0
  NORMAL = 1
  VERBOSE = 2

  __shared_state = {}

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    self.log_level = Log.NORMAL
    # Set this to True if you want to see timestamps on each line output.
    self.use_timestamps = False
    self.logger = sys.stdout

  def increase_verbosity(self):
    self.log_level = min(self.log_level + 1, self.VERBOSE)

  def decrease_verbosity(self):
    self.log_level = max(self.log_level - 1, self.WARN)

  def _timestamp(self):
    """Output a detailed timestamp at the beginning of each line output."""

    self.logger.write(time.strftime('[%Y-%m-%d %I:%m:%S %Z] - '))

  def write(self, log_level, *args):
    """This is the public method to use for writing to a file.  Only
    messages whose LOG_LEVEL is <= self.log_level will be printed.  If
    there are multiple ARGS, they will be separated by a space."""

    if log_level > self.log_level:
      return
    if self.use_timestamps:
      self._timestamp()
    self.logger.write(' '.join(map(str,args)) + "\n")
    # Ensure that log output doesn't get out-of-order with respect to
    # stderr output.
    self.logger.flush()

  def warn(self, *args):
    """Log a message at the WARN level."""

    self.write(self.WARN, *args)

  def quiet(self, *args):
    """Log a message at the QUIET level."""

    self.write(self.QUIET, *args)

  def normal(self, *args):
    """Log a message at the NORMAL level."""

    self.write(self.NORMAL, *args)

  def verbose(self, *args):
    """Log a message at the VERBOSE level."""

    self.write(self.VERBOSE, *args)


