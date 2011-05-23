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

"""Access the CVS repository via CVS's 'cvs' command."""


from cvs2svn_lib.common import FatalError
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.abstract_rcs_revision_manager import AbstractRCSRevisionReader


class CVSRevisionReader(AbstractRCSRevisionReader):
  """A RevisionReader that reads the contents via CVS."""

  # Different versions of CVS support different global options.  Here
  # are the global options that we try to use, in order of decreasing
  # preference:
  _possible_global_options = [
      ['-Q', '-R', '-f'],
      ['-Q', '-R'],
      ['-Q', '-f'],
      ['-Q'],
      ['-q', '-R', '-f'],
      ['-q', '-R'],
      ['-q', '-f'],
      ['-q'],
      ]

  def __init__(self, cvs_executable, global_options=None):
    """Initialize a CVSRevisionReader.

    CVS_EXECUTABLE is the CVS command (possibly including the full
    path to the executable; otherwise it is sought in the $PATH).
    GLOBAL_ARGUMENTS, if specified, should be a list of global options
    that are passed to the CVS command before the subcommand.  If
    GLOBAL_ARGUMENTS is not specified, then each of the possibilities
    listed in _possible_global_options is checked in order until one
    is found that runs successfully and without any output to stderr."""

    self.cvs_executable = cvs_executable

    if global_options is None:
      for global_options in self._possible_global_options:
        try:
          self._check_cvs_runs(global_options)
        except CommandFailedException, e:
          pass
        else:
          break
      else:
        raise FatalError(
            '%s\n'
            'Please check that cvs is installed and in your PATH.' % (e,)
            )
    else:
      try:
        self._check_cvs_runs(global_options)
      except CommandFailedException, e:
        raise FatalError(
            '%s\n'
            'Please check that cvs is installed and in your PATH and that\n'
            'the global options that you specified (%r) are correct.'
            % (e, global_options,)
            )

    # The global options were OK; use them for all CVS invocations.
    self.global_options = global_options

  def _check_cvs_runs(self, global_options):
    """Check that CVS can be started.

    Try running 'cvs --version' with the current setting for
    self.cvs_executable and the specified global_options.  If not
    successful, raise a CommandFailedException."""

    check_command_runs(
        [self.cvs_executable] + global_options + ['--version'],
        self.cvs_executable,
        )

  def get_pipe_command(self, cvs_rev, k_option):
    project = cvs_rev.cvs_file.project
    return [
        self.cvs_executable
        ] + self.global_options + [
        '-d', ':local:' + project.cvs_repository_root,
        'co',
        '-r' + cvs_rev.rev,
        '-p'
        ] + k_option + [
        project.cvs_module + cvs_rev.cvs_path
        ]


