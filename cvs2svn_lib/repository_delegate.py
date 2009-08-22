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


import os
import subprocess

from cvs2svn_lib.common import CommandError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.config import DUMPFILE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.dumpfile_delegate import DumpfileDelegate


class RepositoryDelegate(DumpfileDelegate):
  """Creates a new Subversion Repository.  DumpfileDelegate does all
  of the heavy lifting."""

  def __init__(self, revision_reader, target):
    self.target = target

    # Since the output of this run is a repository, not a dumpfile,
    # the temporary dumpfiles we create should go in the tmpdir.  But
    # since we delete it ourselves, we don't want to use
    # artifact_manager.
    DumpfileDelegate.__init__(
        self, revision_reader, Ctx().get_temp_filename(DUMPFILE)
        )

    self.dumpfile = open(self.dumpfile_path, 'w+b')
    self.loader_pipe = subprocess.Popen(
        [Ctx().svnadmin_executable, 'load', '-q', self.target],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
    self.loader_pipe.stdout.close()
    try:
      self._write_dumpfile_header(self.loader_pipe.stdin)
    except IOError:
      raise FatalError(
          'svnadmin failed with the following output while '
          'loading the dumpfile:\n%s'
          % (self.loader_pipe.stderr.read(),)
          )

  def start_commit(self, revnum, revprops):
    """Start a new commit."""

    DumpfileDelegate.start_commit(self, revnum, revprops)

  def end_commit(self):
    """Feed the revision stored in the dumpfile to the svnadmin load pipe."""

    DumpfileDelegate.end_commit(self)

    self.dumpfile.seek(0)
    while True:
      data = self.dumpfile.read(128*1024) # Chunk size is arbitrary
      if not data:
        break
      try:
        self.loader_pipe.stdin.write(data)
      except IOError:
        raise FatalError("svnadmin failed with the following output "
                         "while loading the dumpfile:\n"
                         + self.loader_pipe.stderr.read())
    self.dumpfile.seek(0)
    self.dumpfile.truncate()

  def finish(self):
    """Clean up."""

    self.dumpfile.close()
    self.loader_pipe.stdin.close()
    error_output = self.loader_pipe.stderr.read()
    exit_status = self.loader_pipe.wait()
    del self.loader_pipe
    if exit_status:
      raise CommandError('svnadmin load', exit_status, error_output)
    os.remove(self.dumpfile_path)


