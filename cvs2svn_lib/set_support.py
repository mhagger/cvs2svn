# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006 CollabNet.  All rights reserved.
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

"""Provide some backwards-compatibility support for sets.

Importing this module with

    from cvs2svn_lib.set_support import *

guarantees that there will be an identifier 'set' with simple set
semantics.  It might be a builtin type, or sets.Set, or a homebrewed
version."""

from __future__ import generators

# Pretend we have sets on older python versions:
try:
  # Python 2.4 has a builtin set:
  set
except NameError:
  try:
    # Python 2.3 has a sets module:
    from sets import Set as set
  except ImportError:
    # We have to roll our own:
    class set:
      def __init__(self, iterable=()):
        self._dict = { }
        for value in iterable:
          self._dict[value] = None

      def __len__(self):
        return len(self._dict)

      def __iter__(self):
        return self._dict.iterkeys()

      def __contains__(self, value):
        return value in self._dict

      def add(self, value):
        self._dict[value] = None

      def remove(self, value):
        del self._dict[value]

      def pop(self):
        return self._dict.popitem()[0]

      def __and__(self, other):
        """Set intersection."""

        if len(self) <= len(other):
          s1, s2 = self, other
        else:
          s1, s2 = other, self

        retval = set()
        for x in s1:
          if x in s2:
            retval.add(x)
        return retval

      def __repr__(self):
        return 'Set(%r)' % (self._dict.keys(),)

      def __getinitargs__(self):
        return (self._dict.keys(),)


