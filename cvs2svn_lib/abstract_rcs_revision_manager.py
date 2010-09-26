# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2010 CollabNet.  All rights reserved.
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

"""Base class for RCSRevisionReader and CVSRevisionReader."""


from cvs2svn_lib.common import canonicalize_eol
from cvs2svn_lib.process import get_command_output
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.revision_manager import RevisionReader
from cvs2svn_lib.apple_single_filter import get_maybe_apple_single


class AbstractRCSRevisionReader(RevisionReader):
  """A base class for RCSRevisionReader and CVSRevisionReader."""

  def get_pipe_command(self, cvs_rev, k_option):
    """Return the command that is needed to get the contents for CVS_REV.

    K_OPTION is a list containing the '-k' option that is needed, if
    any."""

    raise NotImplementedError()

  def select_k_option(self, cvs_rev):
    """Return the '-k' option to be used for CVS_REV.

    Return a list containing any '-k' option that should be used when
    checking out content for CVS_REV.  If no option is needed, return
    an empty list."""

    if cvs_rev.get_property('_keyword_handling') == 'collapsed':
      return ['-kk']
    else:
      return []

  def get_content(self, cvs_rev):
    data = get_command_output(
        self.get_pipe_command(cvs_rev, self.select_k_option(cvs_rev))
        )

    if Ctx().decode_apple_single:
      # Insert a filter to decode any files that are in AppleSingle
      # format:
      data = get_maybe_apple_single(data)

    eol_fix = cvs_rev.get_property('_eol_fix')
    if eol_fix:
      data = canonicalize_eol(data, eol_fix)

    return data


