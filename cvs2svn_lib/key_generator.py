# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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


from cvs2svn_lib.boolean import *


class KeyGenerator:
  """Generate a series of unique keys."""

  def __init__(self, first_id=1L):
    """Initialize a KeyGenerator with the specified FIRST_ID.

    FIRST_ID should be an int or long, and the generated keys will be
    of the same type."""

    self._key_base = first_id

  def gen_id(self):
    """Generate and return a previously-unused key, as an integer."""

    id = self._key_base
    self._key_base += 1

    return id

  def gen_key(self):
    """Generate and return a previously-unused key, as a string."""

    return '%x' % self.gen_id()


