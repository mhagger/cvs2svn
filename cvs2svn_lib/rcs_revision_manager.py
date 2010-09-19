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

"""Access the CVS repository via RCS's 'co' command."""


from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import canonicalize_eol
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import get_command_output
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.revision_manager import RevisionReader
from cvs2svn_lib.apple_single_filter import get_maybe_apple_single


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

  def get_content(self, cvs_rev):
    pipe_cmd = [
        self.co_executable,
        '-q',
        '-x,v',
        '-p%s' % (cvs_rev.rev,)
        ]
    if cvs_rev.get_property('_keyword_handling') == 'collapsed':
      pipe_cmd.append('-kk')
    pipe_cmd.append(cvs_rev.cvs_file.rcs_path)
    data = get_command_output(pipe_cmd)

    if Ctx().decode_apple_single:
      # Insert a filter to decode any files that are in AppleSingle
      # format:
      data = get_maybe_apple_single(data)

    eol_fix = cvs_rev.get_property('_eol_fix')
    if eol_fix:
      data = canonicalize_eol(data, eol_fix)

    return data


