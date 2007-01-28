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

  If self.log_level is DEBUG or higher, each line will be timestamped
  with the number of seconds since the start of the program run.

  If self.use_timestamps is True, each line will be timestamped with a
  human-readable clock time.

  This class is a Borg; see
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531."""

  # These constants represent the log levels that this class supports.
  # The increase_verbosity() and decrease_verbosity() methods rely on
  # these constants being consecutive integers:
  WARN = -1
  QUIET = 0
  NORMAL = 1
  VERBOSE = 2
  DEBUG = 3

  __shared_state = {}

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    self.log_level = Log.NORMAL
    # Set this to True if you want to see timestamps on each line output.
    self.use_timestamps = False
    self.logger = sys.stdout
    self.start_time = time.time()

  def increase_verbosity(self):
    self.log_level = min(self.log_level + 1, Log.DEBUG)

  def decrease_verbosity(self):
    self.log_level = max(self.log_level - 1, Log.WARN)

  def is_on(self, level):
    """Return True iff messages at the specified LEVEL are currently on.

    LEVEL should be one of the constants Log.WARN, Log.QUIET, etc."""

    return self.log_level >= level

  def _timestamp(self):
    """Return a timestamp if needed."""

    retval = []

    if self.log_level >= Log.DEBUG:
      retval.append('%f:' % (time.time() - self.start_time,))

    if self.use_timestamps:
      retval.append(time.strftime('[%Y-%m-%d %I:%m:%S %Z] -'))

    return retval

  def write(self, log_level, *args):
    """Write a message to the log at level LOG_LEVEL.

    This is the public method to use for writing to a file.  Only
    messages whose LOG_LEVEL is <= self.log_level will be printed.  If
    there are multiple ARGS, they will be separated by spaces."""

    if self.is_on(log_level):
      self.logger.write(' '.join(self._timestamp() + map(str, args)) + "\n")
      # Ensure that log output doesn't get out-of-order with respect to
      # stderr output.
      self.logger.flush()

  def warn(self, *args):
    """Log a message at the WARN level."""

    self.write(Log.WARN, *args)

  def quiet(self, *args):
    """Log a message at the QUIET level."""

    self.write(Log.QUIET, *args)

  def normal(self, *args):
    """Log a message at the NORMAL level."""

    self.write(Log.NORMAL, *args)

  def verbose(self, *args):
    """Log a message at the VERBOSE level."""

    self.write(Log.VERBOSE, *args)

  def debug(self, *args):
    """Log a message at the DEBUG level."""

    self.write(Log.DEBUG, *args)


