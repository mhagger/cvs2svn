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
from cvs2svn_lib.keyword_expander import expand_keywords
from cvs2svn_lib.keyword_expander import collapse_keywords
from cvs2svn_lib.apple_single_filter import get_maybe_apple_single


class AbstractRCSRevisionReader(RevisionReader):
  """A base class for RCSRevisionReader and CVSRevisionReader."""

  # A map from (eol_fix, keyword_handling) to ('-k' option needed for
  # RCS/CVS, explicit_keyword_handling).
  _text_options = {
      (False, 'collapsed') : (['-kk'], None),
      (False, 'expanded') : ([], None),
      (False, 'untouched') : ([], None),

      (True, 'collapsed') : (['-kk'], None),
      (True, 'expanded') : ([], None),
      (True, 'untouched') : ([], None),
      }

  def get_pipe_command(self, cvs_rev, k_option):
    """Return the command that is needed to get the contents for CVS_REV.

    K_OPTION is a list containing the '-k' option that is needed, if
    any."""

    raise NotImplementedError()

  def get_content(self, cvs_rev):
    # Is EOL fixing requested?
    eol_fix = cvs_rev.get_property('_eol_fix') or None

    # How do we want keywords to be handled?
    keyword_handling = cvs_rev.get_property('_keyword_handling') or None

    try:
      (k_option, explicit_keyword_handling) = self._text_options[
          bool(eol_fix), keyword_handling
          ]
    except KeyError:
      raise FatalError(
          'Undefined _keyword_handling property (%r) for %s'
          % (keyword_handling, cvs_rev,)
          )

    data = get_command_output(self.get_pipe_command(cvs_rev, k_option))

    if Ctx().decode_apple_single:
      # Insert a filter to decode any files that are in AppleSingle
      # format:
      data = get_maybe_apple_single(data)

    if explicit_keyword_handling == 'expanded':
      data = expand_keywords(data, cvs_rev)
    elif explicit_keyword_handling == 'collapsed':
      data = collapse_keywords(data)

    if eol_fix:
      data = canonicalize_eol(data, eol_fix)

    return data


