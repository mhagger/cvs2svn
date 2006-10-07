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
import re

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import CommandError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import SimplePopen
from cvs2svn_lib.process import CommandFailedException


class PipeStream:
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


class CVSRepository:
  """A CVS repository from which data can be extracted."""

  def __init__(self, cvs_repos_path):
    """CVS_REPOS_PATH is the top of the CVS repository (at least as
    far as this run is concerned)."""

    if not os.path.isdir(cvs_repos_path):
      raise FatalError("The specified CVS repository path '%s' is not an "
                       "existing directory." % cvs_repos_path)

    self.cvs_repos_path = os.path.normpath(cvs_repos_path)
    self.cvs_prefix_re = re.compile(
        r'^' + re.escape(self.cvs_repos_path)
        + r'(' + re.escape(os.sep) + r'|$)')

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    """Return a file-like object from which the contents of CVS_REV
    can be read.

    CVS_REV is a CVSRevision.  If SUPPRESS_KEYWORD_SUBSTITUTION is
    True, then suppress the substitution of RCS/CVS keywords in the
    output."""

    raise NotImplementedError


class CVSRepositoryViaRCS(CVSRepository):
  """A CVSRepository accessed via RCS."""

  def __init__(self, cvs_repos_path):
    CVSRepository.__init__(self, cvs_repos_path)
    try:
      check_command_runs([ Ctx().co_executable, '-V' ], 'co')
    except CommandFailedException, e:
      raise FatalError('%s\n'
                       'Please check that co is installed and in your PATH\n'
                       '(it is a part of the RCS software).' % (e,))

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    pipe_cmd = [ Ctx().co_executable, '-q', '-x,v', '-p' + cvs_rev.rev ]
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(cvs_rev.cvs_file.filename)
    return PipeStream(pipe_cmd)


class CVSRepositoryViaCVS(CVSRepository):
  """A CVSRepository accessed via CVS."""

  def __init__(self, cvs_repos_path):
    CVSRepository.__init__(self, cvs_repos_path)
    # Ascend above the specified root if necessary, to find the
    # cvs_repository_root (a directory containing a CVSROOT directory)
    # and the cvs_module (the path of the conversion root within the
    # cvs repository) NB: cvs_module must be seperated by '/' *not* by
    # os.sep .
    def is_cvs_repository_root(path):
      return os.path.isdir(os.path.join(path, 'CVSROOT'))

    self.cvs_repository_root = os.path.abspath(self.cvs_repos_path)
    self.cvs_module = ""
    while not is_cvs_repository_root(self.cvs_repository_root):
      # Step up one directory:
      prev_cvs_repository_root = self.cvs_repository_root
      self.cvs_repository_root, module_component = \
          os.path.split(self.cvs_repository_root)
      if self.cvs_repository_root == prev_cvs_repository_root:
        # Hit the root (of the drive, on Windows) without finding a
        # CVSROOT dir.
        raise FatalError(
            "the path '%s' is not a CVS repository, nor a path "
            "within a CVS repository.  A CVS repository contains "
            "a CVSROOT directory within its root directory."
            % (self.cvs_repos_path,))

      self.cvs_module = module_component + "/" + self.cvs_module

    os.environ['CVSROOT'] = self.cvs_repository_root

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

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    pipe_cmd = [ Ctx().cvs_executable ] + self.global_arguments + \
               [ 'co', '-r' + cvs_rev.rev, '-p' ]
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(self.cvs_module + cvs_rev.cvs_path)
    return PipeStream(pipe_cmd)


