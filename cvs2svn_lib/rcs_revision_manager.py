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
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.abstract_rcs_revision_manager import AbstractRCSRevisionReader


class RCSRevisionReader(AbstractRCSRevisionReader):
  """A RevisionReader that reads the contents via RCS."""

  def __init__(self, co_executable):
    self.co_executable = co_executable
    try:
      check_command_runs([self.co_executable, '-V'], self.co_executable)
    except CommandFailedException, e:
      raise FatalError('%s\n'
                       'Please check that co is installed and in your PATH\n'
                       '(it is a part of the RCS software).' % (e,))

  def get_pipe_command(self, cvs_rev, k_option):
    return [
        self.co_executable,
        '-q',
        '-x,v',
        '-p%s' % (cvs_rev.rev,)
        ] + k_option + [
        cvs_rev.cvs_file.rcs_path
        ]


