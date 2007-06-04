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

"""This module contains common facilities used by cvs2svn."""


import time
import codecs

from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log


# Always use these constants for opening databases.
DB_OPEN_READ = 'r'
DB_OPEN_WRITE = 'w'
DB_OPEN_NEW = 'n'


SVN_INVALID_REVNUM = -1


# Things that can happen to a file.
OP_ADD    = 'A'
OP_DELETE = 'D'
OP_CHANGE = 'C'


# Warnings and errors start with these strings.  They are typically
# followed by a colon and a space, as in "%s: " ==> "WARNING: ".
warning_prefix = "WARNING"
error_prefix = "ERROR"


class FatalException(Exception):
  """Exception thrown on a non-recoverable error.

  If this exception is thrown by main(), it is caught by the global
  layer of the program, its string representation is printed, and the
  program is ended with an exit code of 1."""

  pass


class InternalError(FatalException):
  """Exception thrown in the case of a cvs2svn internal error (aka, bug)."""

  pass


class FatalError(FatalException):
  """A FatalException that prepends error_prefix to the message."""

  def __init__(self, msg):
    """Use (error_prefix + ': ' + MSG + '\n') as the error message."""

    FatalException.__init__(self, '%s: %s\n' % (error_prefix, msg,))


class CommandError(FatalError):
  """A FatalError caused by a failed command invocation.

  The error message includes the command name, exit code, and output."""

  def __init__(self, command, exit_status, error_output=''):
    self.command = command
    self.exit_status = exit_status
    self.error_output = error_output
    if error_output.rstrip():
      FatalError.__init__(
          self,
          'The command %r failed with exit status=%s\n'
          'and the following output:\n'
          '%s'
          % (self.command, self.exit_status, self.error_output.rstrip()))
    else:
      FatalError.__init__(
          self,
          'The command %r failed with exit status=%s and no output'
          % (self.command, self.exit_status))


def path_join(*components):
  """Join two or more pathname COMPONENTS, inserting '/' as needed.
  Empty component are skipped."""

  return '/'.join(filter(None, components))


def path_split(path):
  """Split the svn pathname PATH into a pair, (HEAD, TAIL).

  This is similar to os.path.split(), but always uses '/' as path
  separator.  PATH is an svn path, which should not start with a '/'.
  HEAD is everything before the last slash, and TAIL is everything
  after.  If PATH ends in a slash, TAIL will be empty.  If there is no
  slash in PATH, HEAD will be empty.  If PATH is empty, both HEAD and
  TAIL are empty."""

  pos = path.rfind('/')
  if pos == -1:
    return ('', path,)
  else:
    return (path[:pos], path[pos+1:],)


def format_date(date):
  """Return an svn-compatible date string for DATE (seconds since epoch).

  A Subversion date looks like '2002-09-29T14:44:59.000000Z'."""

  return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(date))


class UTF8Encoder:
  """Callable that decodes strings into unicode then encodes them as utf8."""

  def __init__(self, encodings, fallback_encoding=None):
    """Create a UTF8Encoder instance.

    ENCODINGS is a list containing the names of encodings that are
    attempted to be used as source encodings in 'strict' mode.

    FALLBACK_ENCODING, if specified, is the name of an encoding that
    should be used as a source encoding in lossy 'replace' mode if all
    of ENCODINGS failed.

    Raise LookupError if any of the specified encodings is unknown."""

    self.decoders = [
        (encoding, codecs.lookup(encoding)[1])
        for encoding in encodings]

    if fallback_encoding is None:
      self.fallback_decoder = None
    else:
      self.fallback_decoder = (
          fallback_encoding, codecs.lookup(fallback_encoding)[1]
          )

  def __call__(self, s):
    """Try to decode 8-bit string S using our configured source encodings.

    Return the string as unicode, encoded in an 8-bit string as utf8.

    Raise UnicodeError if the string cannot be decoded using any of
    the source encodings and no fallback encoding was specified."""

    for (name, decoder) in self.decoders:
      try:
        return decoder(s)[0].encode('utf8')
      except ValueError:
        Log().verbose("Encoding '%s' failed for string %r" % (name, s))

    if self.fallback_decoder is not None:
      (name, decoder) = self.fallback_decoder
      return decoder(s, 'replace')[0].encode('utf8')
    else:
      raise UnicodeError


class Timestamper:
  """Return monotonic timestamps derived from changeset timestamps."""

  def __init__(self):
    # The last timestamp that has been returned:
    self.timestamp = 0.0

    # The maximum timestamp that is considered reasonable:
    self.max_timestamp = time.time() + 24.0 * 60.0 * 60.0

  def get(self, timestamp, change_expected):
    """Return a reasonable timestamp derived from TIMESTAMP.

    Push TIMESTAMP into the future if necessary to ensure that it is
    at least one second later than every other timestamp that has been
    returned by previous calls to this method.

    If CHANGE_EXPECTED is not True, then log a message if the
    timestamp has to be changed."""

    if timestamp > self.max_timestamp:
      # If a timestamp is in the future, it is assumed that it is
      # bogus.  Shift it backwards in time to prevent it forcing other
      # timestamps to be pushed even further in the future.

      # Note that this is not nearly a complete solution to the bogus
      # timestamp problem.  A timestamp in the future still affects
      # the ordering of changesets, and a changeset having such a
      # timestamp will not be committed until all changesets with
      # earlier timestamps have been committed, even if other
      # changesets with even earlier timestamps depend on this one.
      self.timestamp = self.timestamp + 1.0
      if not change_expected:
        Log().warn(
            'Timestamp "%s" is in the future; changed to "%s".'
            % (time.asctime(time.gmtime(timestamp)),
               time.asctime(time.gmtime(self.timestamp)),)
            )
    elif timestamp < self.timestamp + 1.0:
      self.timestamp = self.timestamp + 1.0
      if not change_expected and Log().is_on(Log.VERBOSE):
        Log().verbose(
            'Timestamp "%s" adjusted to "%s" to ensure monotonicity.'
            % (time.asctime(time.gmtime(timestamp)),
               time.asctime(time.gmtime(self.timestamp)),)
            )
    else:
      self.timestamp = timestamp

    return self.timestamp


