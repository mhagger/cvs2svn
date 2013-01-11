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

"""This module contains a simple logging facility for cvs2svn."""


import sys
import time
import threading


class _Log:
  """A Simple logging facility.

  If self.log_level is DEBUG or higher, each line will be timestamped
  with the number of wall-clock seconds since the time when this
  module was first imported.

  The public methods of this class are thread-safe."""

  # These constants represent the log levels that this class supports.
  # The increase_verbosity() and decrease_verbosity() methods rely on
  # these constants being consecutive integers:
  ERROR = -2
  WARN = -1
  QUIET = 0
  NORMAL = 1
  VERBOSE = 2
  DEBUG = 3

  start_time = time.time()

  def __init__(self):
    self.log_level = _Log.NORMAL

    # The output file to use for errors:
    self._err = sys.stderr

    # The output file to use for lower-priority messages.  We also
    # write these to stderr so that other output (e.g., dumpfiles) can
    # be written to stdout without being contaminated with progress
    # messages:
    self._out = sys.stderr

    # Lock to serialize writes to the log:
    self.lock = threading.Lock()

  def increase_verbosity(self):
    self.lock.acquire()
    try:
      self.log_level = min(self.log_level + 1, _Log.DEBUG)
    finally:
      self.lock.release()

  def decrease_verbosity(self):
    self.lock.acquire()
    try:
      self.log_level = max(self.log_level - 1, _Log.ERROR)
    finally:
      self.lock.release()

  def is_on(self, level):
    """Return True iff messages at the specified LEVEL are currently on.

    LEVEL should be one of the constants _Log.WARN, _Log.QUIET, etc."""

    return self.log_level >= level

  def _timestamp(self):
    """Return a timestamp if needed, as a string with a trailing space."""

    retval = []

    if self.log_level >= _Log.DEBUG:
      retval.append('%f: ' % (time.time() - self.start_time,))

    return ''.join(retval)

  def _write(self, out, *args):
    """Write a message to OUT.

    If there are multiple ARGS, they will be separated by spaces.  If
    there are multiple lines, they will be output one by one with the
    same timestamp prefix."""

    timestamp = self._timestamp()
    s = ' '.join(map(str, args))
    lines = s.split('\n')
    if lines and not lines[-1]:
      del lines[-1]

    self.lock.acquire()
    try:
      for s in lines:
        out.write('%s%s\n' % (timestamp, s,))
      # Ensure that log output doesn't get out-of-order with respect to
      # stderr output.
      out.flush()
    finally:
      self.lock.release()

  def write(self, *args):
    """Write a message to SELF._out.

    This is a public method to use for writing to the output log
    unconditionally."""

    self._write(self._out, *args)

  def error(self, *args):
    """Log a message at the ERROR level."""

    if self.is_on(_Log.ERROR):
      self._write(self._err, *args)

  def warn(self, *args):
    """Log a message at the WARN level."""

    if self.is_on(_Log.WARN):
      self._write(self._out, *args)

  def quiet(self, *args):
    """Log a message at the QUIET level."""

    if self.is_on(_Log.QUIET):
      self._write(self._out, *args)

  def normal(self, *args):
    """Log a message at the NORMAL level."""

    if self.is_on(_Log.NORMAL):
      self._write(self._out, *args)

  def verbose(self, *args):
    """Log a message at the VERBOSE level."""

    if self.is_on(_Log.VERBOSE):
      self._write(self._out, *args)

  def debug(self, *args):
    """Log a message at the DEBUG level."""

    if self.is_on(_Log.DEBUG):
      self._write(self._out, *args)


# Create an instance that everybody can use:
logger = _Log()


