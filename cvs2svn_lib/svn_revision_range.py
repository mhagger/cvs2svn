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

"""This module contains the SvnRevisionRange class."""


from __future__ import generators


class SvnRevisionRange:
  """The range of subversion revision numbers from which a path can be
  copied.  self.opening_revnum is the number of the earliest such
  revision, and self.closing_revnum is one higher than the number of
  the last such revision.  If self.closing_revnum is None, then no
  closings were registered."""

  def __init__(self, opening_revnum):
    self.opening_revnum = opening_revnum
    self.closing_revnum = None

  def add_closing(self, closing_revnum):
    # When we have a non-trunk default branch, we may have multiple
    # closings--only register the first closing we encounter.
    if self.closing_revnum is None:
      self.closing_revnum = closing_revnum

  def __str__(self):
    if self.closing_revnum is None:
      return '[%d:]' % (self.opening_revnum,)
    else:
      return '[%d:%d]' % (self.opening_revnum, self.closing_revnum,)


