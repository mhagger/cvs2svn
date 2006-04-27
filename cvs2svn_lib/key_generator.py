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

"""This module contains the KeyGenerator class."""


import sys
import os
import marshal

from boolean import *


class KeyGenerator:
  """Generate a series of unique strings."""

  def __init__(self):
    self.key_base = 0L

  def gen_key(self):
    """Generate and return a previously-unused key."""

    key = '%x' % self.key_base
    self.key_base += 1

    return key


