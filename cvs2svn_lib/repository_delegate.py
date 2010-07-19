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

"""This module contains class RepositoryDelegate."""


import subprocess

from cvs2svn_lib.common import CommandError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_dump import DumpstreamDelegate


class LoaderPipe(object):
  """A file-like object that writes to 'svnadmin load'.

  Some error checking and reporting are done when writing."""

  def __init__(self, target):
    self.loader_pipe = subprocess.Popen(
        [Ctx().svnadmin_executable, 'load', '-q', target],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
    self.loader_pipe.stdout.close()

  def write(self, s):
    try:
      self.loader_pipe.stdin.write(s)
    except IOError, e:
      raise FatalError(
          'svnadmin failed with the following output while '
          'loading the dumpfile:\n%s'
          % (self.loader_pipe.stderr.read(),)
          )

  def close(self):
    self.loader_pipe.stdin.close()
    error_output = self.loader_pipe.stderr.read()
    exit_status = self.loader_pipe.wait()
    del self.loader_pipe
    if exit_status:
      raise CommandError('svnadmin load', exit_status, error_output)


def RepositoryDelegate(revision_reader, target):
  loader_pipe = LoaderPipe(target)
  return DumpstreamDelegate(revision_reader, loader_pipe)


