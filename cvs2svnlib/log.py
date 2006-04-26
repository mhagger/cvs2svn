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

from boolean import *


# These constants represent the log levels that this script supports
LOG_WARN = -1
LOG_QUIET = 0
LOG_NORMAL = 1
LOG_VERBOSE = 2


class Log:
  """A Simple logging facility.  Each line will be timestamped is
  self.use_timestamps is TRUE.  This class is a Borg, see
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531."""

  __shared_state = {}

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    self.log_level = LOG_NORMAL
    # Set this to true if you want to see timestamps on each line output.
    self.use_timestamps = None
    self.logger = sys.stdout

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


