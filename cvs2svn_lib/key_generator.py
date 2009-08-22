# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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


class KeyGenerator:
  """Generate a series of unique keys."""

  def __init__(self, first_id=1):
    """Initialize a KeyGenerator with the specified FIRST_ID.

    FIRST_ID should be an int or long, and the generated keys will be
    of the same type."""

    self._key_base = first_id
    self._last_id = None

  def gen_id(self):
    """Generate and return a previously-unused key, as an integer."""

    self._last_id = self._key_base
    self._key_base += 1

    return self._last_id

  def get_last_id(self):
    """Return the last id that was generated, as an integer."""

    return self._last_id


