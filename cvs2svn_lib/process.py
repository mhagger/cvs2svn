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

"""This module contains generic utilities used by cvs2svn."""


import subprocess

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import CommandError


def call_command(command, **kw):
  """Call the specified command, checking that it exits successfully.

  Raise a FatalError if the command cannot be executed, or if it exits
  with a non-zero exit code.  Pass KW as keyword arguments to
  subprocess.call()."""

  try:
    retcode = subprocess.call(command, **kw)
    if retcode < 0:
      raise FatalError(
          'Command terminated by signal %d: "%s"'
          % (-retcode, ' '.join(command),)
          )
    elif retcode > 0:
      raise FatalError(
          'Command failed with return code %d: "%s"'
          % (retcode, ' '.join(command),)
          )
  except OSError, e:
    raise FatalError(
        'Command execution failed (%s): "%s"'
        % (e, ' '.join(command),)
        )


class CommandFailedException(Exception):
  """Exception raised if check_command_runs() fails."""

  pass


def check_command_runs(cmd, cmdname):
  """Check whether the command CMD can be executed without errors.

  CMD is a list or string, as accepted by subprocess.Popen().  CMDNAME
  is the name of the command as it should be included in exception
  error messages.

  This function checks three things: (1) the command can be run
  without throwing an OSError; (2) it exits with status=0; (3) it
  doesn't output anything to stderr.  If any of these conditions is
  not met, raise a CommandFailedException describing the problem."""

  try:
    pipe = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
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
    self._pipe_command_str = ' '.join(pipe_command)
    self.pipe = subprocess.Popen(
        pipe_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
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
      raise CommandError(self._pipe_command_str, exit_status, error_output)


