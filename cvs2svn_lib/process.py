# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

"""This module contains generic utilities used by cvs2svn."""


import sys
import os
import types
import subprocess

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import CommandError


# ============================================================================
# This code is copied with a few modifications from:
#   subversion/subversion/bindings/swig/python/svn/core.py

if sys.platform == "win32":
  import re
  _escape_shell_arg_re = re.compile(r'(\\+)(\"|$)')

  def escape_shell_arg(arg):
    # The (very strange) parsing rules used by the C runtime library are
    # described at:
    # http://msdn.microsoft.com/library/en-us/vclang/html/_pluslang_Parsing_C.2b2b_.Command.2d.Line_Arguments.asp

    # double up slashes, but only if they are followed by a quote character
    arg = re.sub(_escape_shell_arg_re, r'\1\1\2', arg)

    # surround by quotes and escape quotes inside
    arg = '"' + arg.replace('"', '"^""') + '"'
    return arg


  def argv_to_command_string(argv):
    """Flatten a list of command line arguments into a command string.

    The resulting command string is expected to be passed to the system
    shell which os functions like popen() and system() invoke internally.
    """

    # According cmd's usage notes (cmd /?), it parses the command line by
    # "seeing if the first character is a quote character and if so, stripping
    # the leading character and removing the last quote character."
    # So to prevent the argument string from being changed we add an extra set
    # of quotes around it here.
    return '"' + ' '.join(map(escape_shell_arg, argv)) + '"'

else:
  def escape_shell_arg(arg):
    return "'" + arg.replace("'", "'\\''") + "'"

  def argv_to_command_string(argv):
    """Flatten a list of command line arguments into a command string.

    The resulting command string is expected to be passed to the system
    shell which os functions like popen() and system() invoke internally.
    """

    return ' '.join(map(escape_shell_arg, argv))


class SimplePopen:
  def __init__(self, cmd, capture_stderr):
    if capture_stderr:
      stderr = subprocess.PIPE
    else:
      stderr = None
    self._popen = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr
        )
    self.stdin = self._popen.stdin
    self.stdout = self._popen.stdout
    if capture_stderr:
      self.stderr = self._popen.stderr
    self.wait = self._popen.wait


def run_command(command):
  if os.system(command):
    raise FatalError('Command failed: "%s"' % (command,))


class CommandFailedException(Exception):
  """Exception raised if check_command_runs() fails."""

  pass


def check_command_runs(cmd, cmdname):
  """Check whether the command CMD can be executed without errors.

  CMD is a list or string, as accepted by SimplePopen.  CMDNAME is the
  name of the command as it should be included in exception error
  messages.

  This function checks three things: (1) the command can be run
  without throwing an OSError; (2) it exits with status=0; (3) it
  doesn't output anything to stderr.  If any of these conditions is
  not met, raise a CommandFailedException describing the problem."""

  try:
    pipe = SimplePopen(cmd, True)
  except OSError, e:
    raise CommandFailedException('error executing %s: %s' % (cmdname, e,))
  pipe.stdin.close()
  pipe.stdout.read()
  errmsg = pipe.stderr.read()
  status = pipe.wait()
  if status or errmsg:
    msg = 'error executing %s: status %s' % (cmdname, status,)
    if errmsg:
      msg += ', error output:\n%s' % (errmsg,)
    raise CommandFailedException(msg)


class PipeStream(object):
  """A file-like object from which revision contents can be read."""

  def __init__(self, pipe_command):
    self.pipe_command = ' '.join(pipe_command)
    self.pipe = SimplePopen(pipe_command, True)
    self.pipe.stdin.close()

  def read(self, size=None):
    if size is None:
      return self.pipe.stdout.read()
    else:
      return self.pipe.stdout.read(size)

  def close(self):
    self.pipe.stdout.close()
    error_output = self.pipe.stderr.read()
    exit_status = self.pipe.wait()
    if exit_status:
      raise CommandError(self.pipe_command, exit_status, error_output)


