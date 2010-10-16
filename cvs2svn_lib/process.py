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
from cvs2svn_lib.log import logger


def call_command(command, **kw):
  """Call the specified command, checking that it exits successfully.

  Raise a FatalError if the command cannot be executed, or if it exits
  with a non-zero exit code.  Pass KW as keyword arguments to
  subprocess.call()."""

  logger.debug('Running command %r' % (command,))
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


def check_command_runs(command, commandname):
  """Check whether the command CMD can be executed without errors.

  CMD is a list or string, as accepted by subprocess.Popen().  CMDNAME
  is the name of the command as it should be included in exception
  error messages.

  This function checks three things: (1) the command can be run
  without throwing an OSError; (2) it exits with status=0; (3) it
  doesn't output anything to stderr.  If any of these conditions is
  not met, raise a CommandFailedException describing the problem."""

  logger.debug('Running command %r' % (command,))
  try:
    pipe = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
  except OSError, e:
    raise CommandFailedException('error executing %s: %s' % (commandname, e,))
  (stdout, stderr) = pipe.communicate()
  if pipe.returncode or stderr:
    msg = 'error executing %s; returncode=%s' % (commandname, pipe.returncode,)
    if stderr:
      msg += ', error output:\n%s' % (stderr,)
    raise CommandFailedException(msg)


def get_command_output(command):
  """Run COMMAND and return its stdout.

  COMMAND is a list of strings.  Run the command and return its stdout
  as a string.  If the command exits with a nonzero return code or
  writes something to stderr, raise a CommandError."""

  """A file-like object from which revision contents can be read."""

  logger.debug('Running command %r' % (command,))
  pipe = subprocess.Popen(
      command,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      )
  (stdout, stderr) = pipe.communicate()
  if pipe.returncode or stderr:
    raise CommandError(' '.join(command), pipe.returncode, stderr)
  return stdout


