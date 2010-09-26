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


from cvs2svn_lib.revision_manager import RevisionReader


class AbstractRCSRevisionReader(RevisionReader):
  """A base class for RCSRevisionReader and CVSRevisionReader."""

  def select_k_option(self, cvs_rev):
    """Return the '-k' option to be used for CVS_REV.

    Return a list containing any '-k' option that should be used when
    checking out content for CVS_REV.  If no option is needed, return
    an empty list."""

    if cvs_rev.get_property('_keyword_handling') == 'collapsed':
      return ['-kk']
    else:
      return []


