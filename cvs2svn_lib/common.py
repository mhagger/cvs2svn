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

from cvs2svn_lib.boolean import *


SVN_INVALID_REVNUM = -1


# Things that can happen to a file.
OP_NOOP   = '-'
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


class FatalError(FatalException):
  """A FatalException that prepends error_prefix to the message."""

  def __init__(self, msg):
    """Use (error_prefix + ': ' + MSG + '\n') as the error message."""

    FatalException.__init__(self, '%s: %s\n' % (error_prefix, msg,))


class CommandError(FatalError):
  """A FatalError caused by a failed command invocation.

  The error message includes the command name, exit code, and output."""

  def __init__(self, command, exit_status, error_output):
    self.command = command
    self.exit_status = exit_status
    self.error_output = error_output
    FatalError.__init__(
        self,
        'The command %r failed with exit status=%s\n'
        'and the following output:\n'
        '%s'
        % (self.command, self.exit_status, self.error_output.rstrip()))


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


