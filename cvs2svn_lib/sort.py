# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

"""Functions to sort large files."""


import sys
import os

from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.process import call_command


def sort_file(infilename, outfilename, options=[]):
  """Sort file INFILENAME, storing the results to OUTFILENAME.

  OPTIONS is an optional list of strings that are passed as additional
  options to the sort command."""

  # GNU sort will sort our dates differently (incorrectly!) if our
  # LC_ALL is anything but 'C', so if LC_ALL is set, temporarily set
  # it to 'C'
  lc_all_tmp = os.environ.get('LC_ALL', None)
  os.environ['LC_ALL'] = 'C'

  # The -T option to sort has a nice side effect.  The Win32 sort is
  # case insensitive and cannot be used, and since it does not
  # understand the -T option and dies if we try to use it, there is no
  # risk that we use that sort by accident.
  command = [
      Ctx().sort_executable,
      '-T', Ctx().tmpdir
      ] + options + [
      infilename
      ]

  try:
    # Under Windows, the subprocess module uses the Win32
    # CreateProcess, which always looks in the Windows system32
    # directory before it looks in the directories listed in the PATH
    # environment variable.  Since the Windows sort.exe is in the
    # system32 directory it will always be chosen.  A simple
    # workaround is to launch the sort in a shell.  When the shell
    # (cmd.exe) searches it only examines the directories in the PATH
    # so putting the directory with GNU sort ahead of the Windows
    # system32 directory will cause GNU sort to be chosen.
    call_command(
        command, stdout=open(outfilename, 'w'), shell=(sys.platform=='win32')
        )
  finally:
    if lc_all_tmp is None:
      del os.environ['LC_ALL']
    else:
      os.environ['LC_ALL'] = lc_all_tmp

  # On some versions of Windows, os.system() does not return an error
  # if the command fails.  So add little consistency tests here that
  # the output file was created and has the right size:

  if not os.path.exists(outfilename):
    raise FatalError('Sort output file missing: %r' % (outfilename,))

  if os.path.getsize(outfilename) != os.path.getsize(infilename):
    raise FatalError(
        'Sort input and output file sizes differ:\n'
        '    %r (%d bytes)\n'
        '    %r (%d bytes)' % (
            infilename, os.path.getsize(infilename),
            outfilename, os.path.getsize(outfilename),
            )
        )


