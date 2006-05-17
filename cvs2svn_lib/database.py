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

"""This module contains database facilities used by cvs2svn."""


from __future__ import generators

import sys
import os
import marshal
import cPickle

from boolean import *
from common import \
        warning_prefix, \
        error_prefix


# DBM module selection

# 1. If we have bsddb3, it is probably newer than bsddb.  Fake bsddb = bsddb3,
#    so that the dbhash module used by anydbm will use bsddb3.
try:
  import bsddb3
  sys.modules['bsddb'] = sys.modules['bsddb3']
except ImportError:
  pass

# 2. These DBM modules are not good for cvs2svn.
import anydbm
if (anydbm._defaultmod.__name__ == 'dumbdbm'
    or anydbm._defaultmod.__name__ == 'dbm'):
  sys.stderr.write(
    error_prefix
    + ': your installation of Python does not contain a suitable\n'
    + 'DBM module -- cvs2svn cannot continue.\n'
    + 'See http://python.org/doc/current/lib/module-anydbm.html to solve.\n')
  sys.exit(1)

# 3. If we are using the old bsddb185 module, then try prefer gdbm instead.
#    Unfortunately, gdbm appears not to be trouble free, either.
if hasattr(anydbm._defaultmod, 'bsddb') \
    and not hasattr(anydbm._defaultmod.bsddb, '__version__'):
  try:
    gdbm = __import__('gdbm')
  except ImportError:
    sys.stderr.write(warning_prefix +
        ': The version of the bsddb module found '
        'on your computer has been reported to malfunction on some datasets, '
        'causing KeyError exceptions. You may wish to upgrade your Python to '
        'version 2.3 or later.\n')
  else:
    anydbm._defaultmod = gdbm


# Always use these constants for opening databases.
DB_OPEN_READ = 'r'
DB_OPEN_WRITE = 'w'
DB_OPEN_NEW = 'n'


class AbstractDatabase:
  """An abstract base class for anydbm-based databases."""

  def __init__(self, filename, mode):
    """A convenience function for opening an anydbm database."""

    # pybsddb3 has a bug which prevents it from working with
    # Berkeley DB 4.2 if you open the db with 'n' ("new").  This
    # causes the DB_TRUNCATE flag to be passed, which is disallowed
    # for databases protected by lock and transaction support
    # (bsddb databases use locking from bsddb version 4.2.4 onwards).
    #
    # Therefore, manually perform the removal (we can do this, because
    # we know that for bsddb - but *not* anydbm in general - the database
    # consists of one file with the name we specify, rather than several
    # based on that name).
    if mode == 'n' and anydbm._defaultmod.__name__ == 'dbhash':
      if os.path.isfile(filename):
        os.unlink(filename)
      mode = 'c'

    self.db = anydbm.open(filename, mode)

    # Import implementations for many mapping interface methods.  Note
    # that we specifically do not do this for any method which handles
    # *values*, because our derived classes define __getitem__ and
    # __setitem__ to override the storage of values, and grabbing
    # methods directly from the dbm object would bypass this.
    for meth_name in ('__delitem__', 'keys',
        '__iter__', 'has_key', '__contains__', 'iterkeys', 'clear'):
      meth_ref = getattr(self.db, meth_name, None)
      if meth_ref:
        setattr(self, meth_name, meth_ref)

  def __delitem__(self, key):
    # gdbm defines a __delitem__ method, but it cannot be assigned.  So
    # this method provides a fallback definition via explicit delegation:
    del self.db[key]

  def __iter__(self):
    for key in self.keys():
      yield key

  def has_key(self, key):
    try:
      self.db[key]
      return True
    except KeyError:
      return False

  def __contains__(self, key):
    return self.has_key(key)

  def iterkeys(self):
    return self.__iter__()

  def clear(self):
    for key in self.keys():
      del self[key]

  def items(self):
    return [(key, self[key],) for key in self.keys()]

  def values(self):
    return [self[key] for key in self.keys()]

  def get(self, key, default=None):
    try:
      return self[key]
    except KeyError:
      return default


class SDatabase(AbstractDatabase):
  """A database that can only store strings."""

  def __getitem__(self, key):
    return self.db[key]

  def __setitem__(self, key, value):
    self.db[key] = value


class Database(AbstractDatabase):
  """A database that uses the marshal module to store built-in types."""

  def __getitem__(self, key):
    return marshal.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = marshal.dumps(value)


class PDatabase(AbstractDatabase):
  """A database that uses the cPickle module to store built-in types."""

  def __getitem__(self, key):
    return cPickle.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = cPickle.dumps(value, True)


