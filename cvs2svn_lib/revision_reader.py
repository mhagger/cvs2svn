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

"""This module provides access to the CVS repository for cvs2svn."""


import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import CommandError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import SimplePopen
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.revision_recorder import NullRevisionRecorder


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
      raise CommandError(self.pipe_cmd, exit_status, error_output)


class RevisionReader(object):
  """An object that can read the contents of CVSRevisions."""

  def get_revision_recorder(self):
    """Return a RevisionRecorder instance that can gather revision info.

    The object returned by this method will be passed to CollectData,
    and its callback methods called as the CVS files are parsed.  If
    no data collection is necessary, this method can return an
    instance of NullRevisionRecorder."""

    raise NotImplementedError

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    """Return a file-like object from which the contents of CVS_REV
    can be read.

    CVS_REV is a CVSRevision.  If SUPPRESS_KEYWORD_SUBSTITUTION is
    True, then suppress the substitution of RCS/CVS keywords in the
    output."""

    raise NotImplementedError


class RCSRevisionReader(RevisionReader):
  """A RevisionReader that reads the contents via RCS."""

  def __init__(self):
    try:
      check_command_runs([ Ctx().co_executable, '-V' ], 'co')
    except CommandFailedException, e:
      raise FatalError('%s\n'
                       'Please check that co is installed and in your PATH\n'
                       '(it is a part of the RCS software).' % (e,))

  def get_revision_recorder(self):
    return NullRevisionRecorder()

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    pipe_cmd = [ Ctx().co_executable, '-q', '-x,v', '-p' + cvs_rev.rev ]
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(cvs_rev.cvs_file.filename)
    return PipeStream(pipe_cmd)


class CVSRevisionReader(RevisionReader):
  """A RevisionReader that reads the contents via CVS."""

  def __init__(self):
    def cvs_ok(global_arguments):
      check_command_runs(
          [ Ctx().cvs_executable ] + global_arguments + [ '--version' ],
          'cvs')

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

  def get_revision_recorder(self):
    return NullRevisionRecorder()

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    project = cvs_rev.cvs_file.project
    pipe_cmd = [ Ctx().cvs_executable ] + self.global_arguments + \
               [ '-d', project.cvs_repository_root,
                 'co', '-r' + cvs_rev.rev, '-p' ]
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(project.cvs_module + cvs_rev.cvs_path)
    return PipeStream(pipe_cmd)


