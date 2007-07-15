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

"""This module provides access to the CVS repository for cvs2svn."""


import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import PipeStream
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.revision_recorder import NullRevisionRecorder
from cvs2svn_lib.revision_excluder import NullRevisionExcluder


class RevisionReader(object):
  """An object that can read the contents of CVSRevisions."""

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed during branch exclusion.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    raise NotImplementedError()

  def get_revision_recorder(self):
    """Return a RevisionRecorder instance that can gather revision info.

    The object returned by this method will be passed to CollectData,
    and its callback methods called as the CVS files are parsed.  If
    no data collection is necessary, this method can return an
    instance of NullRevisionRecorder."""

    raise NotImplementedError

  def get_revision_excluder(self):
    """Return a RevisionExcluder instance to collect exclusion info.

    The object returned by this method will have its callback methods
    called as branches are excluded.  If such information is not
    needed, this method can return an instance of
    NullRevisionExcluder."""

    raise NotImplementedError

  def start(self):
    """Prepare for calls to get_content_stream."""

    raise NotImplementedError

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    """Return a file-like object from which the contents of CVS_REV
    can be read.

    CVS_REV is a CVSRevision.  If SUPPRESS_KEYWORD_SUBSTITUTION is
    True, then suppress the substitution of RCS/CVS keywords in the
    output."""

    raise NotImplementedError

  def skip_content(self, cvs_rev):
    """Inform the reader that CVS_REV would be fetched now, but isn't
    actually needed.

    This may be used for internal housekeeping.
    Note that this is not called for CVSRevisionDelete revisions."""

    raise NotImplementedError

  def finish(self):
    """Inform the reader that all calls to get_content_stream are done.
    Start may be called again at a later point."""

    raise NotImplementedError


class RCSRevisionReader(RevisionReader):
  """A RevisionReader that reads the contents via RCS."""

  def __init__(self, co_executable):
    self.co_executable = co_executable
    try:
      check_command_runs([self.co_executable, '-V'], self.co_executable)
    except CommandFailedException, e:
      raise FatalError('%s\n'
                       'Please check that co is installed and in your PATH\n'
                       '(it is a part of the RCS software).' % (e,))

  def register_artifacts(self, which_pass):
    pass

  def get_revision_recorder(self):
    return NullRevisionRecorder()

  def get_revision_excluder(self):
    return NullRevisionExcluder()

  def start(self):
    pass

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    pipe_cmd = [self.co_executable, '-q', '-x,v', '-p' + cvs_rev.rev]
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(cvs_rev.cvs_file.filename)
    return PipeStream(pipe_cmd)

  def skip_content(self, cvs_rev):
    pass

  def finish(self):
    pass


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

  def register_artifacts(self, which_pass):
    pass

  def get_revision_recorder(self):
    return NullRevisionRecorder()

  def get_revision_excluder(self):
    return NullRevisionExcluder()

  def start(self):
    pass

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    project = cvs_rev.cvs_file.project
    pipe_cmd = [self.cvs_executable] + self.global_arguments + \
               ['-d', project.cvs_repository_root,
                'co', '-r' + cvs_rev.rev, '-p']
    if suppress_keyword_substitution:
      pipe_cmd.append('-kk')
    pipe_cmd.append(project.cvs_module + cvs_rev.cvs_path)
    return PipeStream(pipe_cmd)

  def skip_content(self, cvs_rev):
    pass

  def finish(self):
    pass

