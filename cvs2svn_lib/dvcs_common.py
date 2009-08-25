# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007-2009 CollabNet.  All rights reserved.
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

"""Miscellaneous utility code common to DVCS backends (like
Git, Mercurial, or Bazaar).
"""

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.output_option import OutputOption


class DVCSOutputOption(OutputOption):
  # name of output format (for error messages); must be set by
  # subclasses
  name = None

  def normalize_author_transforms(self, author_transforms):
    """Return a new dict with the same content as author_transforms, but all
    strings encoded to UTF-8.  Also turns None into the empty dict."""
    result = {}
    if author_transforms is not None:
      for (cvsauthor, (name, email,)) in author_transforms.iteritems():
        cvsauthor = to_utf8(cvsauthor)
        name = to_utf8(name)
        email = to_utf8(email)
        result[cvsauthor] = (name, email,)
    return result

  def check(self):
    if Ctx().cross_project_commits:
      raise FatalError(
          '%s output is not supported with cross-project commits' % self.name
          )
    if Ctx().cross_branch_commits:
      raise FatalError(
          '%s output is not supported with cross-branch commits' % self.name
          )
    if Ctx().username is None:
      raise FatalError(
          '%s output requires a default commit username' % self.name
          )


def to_utf8(s):
  if isinstance(s, unicode):
    return s.encode('utf8')
  else:
    return s


