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

"""Access the CVS repository via CVS's 'cvs' command."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import PipeStream
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.revision_manager import RevisionReader
from cvs2svn_lib.revision_manager import NullRevisionRecorder
from cvs2svn_lib.revision_manager import NullRevisionExcluder


class CVSRevisionReader(RevisionReader):
  """A RevisionReader that reads the contents via CVS."""

  def __init__(self, cvs_executable):
    self.cvs_executable = cvs_executable

    def cvs_ok(global_arguments):
      check_command_runs(
          [self.cvs_executable] + global_arguments + ['--version'],
          self.cvs_executable)

    self.global_arguments = [ "-q", "-R" ]
    try:
      cvs_ok(self.global_arguments)
    except CommandFailedException, e:
      self.global_arguments = [ "-q" ]
      try:
        cvs_ok(self.global_arguments)
      except CommandFailedException, e:
        raise FatalError(
            '%s\n'
            'Please check that cvs is installed and in your PATH.' % (e,))

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    project = cvs_rev.cvs_file.project
    pipe_cmd = [self.cvs_executable] + self.global_arguments + \
               ['-d', project.cvs_repository_root,
                'co', '-r' + cvs_rev.rev, '-p']
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(project.cvs_module + cvs_rev.cvs_path)
    return PipeStream(pipe_cmd)


