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

"""This module contains the FillSource class."""


from cvs2svn_lib.boolean import *


class FillSource:
  """Representation of a fill source used by the symbol filler in
  SVNRepositoryMirror."""

  def __init__(self, prefix, node):
    """Create an unscored fill source with a prefix and a key."""

    self.prefix = prefix
    self.node = node
    self.score = None
    self.revnum = None

  def set_score(self, score, revnum):
    """Set the SCORE and REVNUM."""

    self.score = score
    self.revnum = revnum

  def __cmp__(self, other):
    """Comparison operator used to sort FillSources in descending
    score order."""

    if self.score is None or other.score is None:
      raise TypeError, 'Tried to compare unscored FillSource'
    return cmp(other.score, self.score)


