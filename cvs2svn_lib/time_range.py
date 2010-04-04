# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2008 CollabNet.  All rights reserved.
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

"""This module contains a class to manage time ranges."""


class TimeRange(object):
  __slots__ = ('t_min', 't_max')

  def __init__(self):
    # Start out with a t_min higher than any incoming time T, and a
    # t_max lower than any incoming T.  This way the first T will push
    # t_min down to T, and t_max up to T, naturally (without any
    # special-casing), and successive times will then ratchet them
    # outward as appropriate.
    self.t_min = 1L<<32
    self.t_max = 0

  def add(self, timestamp):
    """Expand the range to encompass TIMESTAMP."""

    if timestamp < self.t_min:
      self.t_min = timestamp
    if timestamp > self.t_max:
      self.t_max = timestamp

  def __cmp__(self, other):
    # Sorted by t_max, and break ties using t_min.
    return cmp(self.t_max, other.t_max) or cmp(self.t_min, other.t_min)

  def __lt__(self, other):
    c = cmp(self.t_max, other.t_max)
    if 0 == c:
      return self.t_min < other.t_min
    return c < 0


