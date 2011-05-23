# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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


import sys
import os
import cPickle

from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import logger


# DBM module selection

# 1. If we have bsddb3, it is probably newer than bsddb.  Fake bsddb = bsddb3,
#    so that the dbhash module used by anydbm will use bsddb3.
try:
  import bsddb3
  sys.modules['bsddb'] = bsddb3
except ImportError:
  pass

# 2. These DBM modules are not good for cvs2svn.
import anydbm
if anydbm._defaultmod.__name__ in ['dumbdbm', 'dbm']:
  logger.error(
      '%s: cvs2svn uses the anydbm package, which depends on lower level '
          'dbm\n'
      'libraries.  Your system has %s, with which cvs2svn is known to have\n'
      'problems.  To use cvs2svn, you must install a Python dbm library '
          'other than\n'
      'dumbdbm or dbm.  See '
          'http://python.org/doc/current/lib/module-anydbm.html\n'
      'for more information.\n'
      % (error_prefix, anydbm._defaultmod.__name__,)
      )
  sys.exit(1)

# 3. If we are using the old bsddb185 module, then try prefer gdbm instead.
#    Unfortunately, gdbm appears not to be trouble free, either.
if hasattr(anydbm._defaultmod, 'bsddb') \
    and not hasattr(anydbm._defaultmod.bsddb, '__version__'):
  try:
    gdbm = __import__('gdbm')
  except ImportError:
    logger.warn(
        '%s: The version of the bsddb module found on your computer '
            'has been\n'
        'reported to malfunction on some datasets, causing KeyError '
            'exceptions.\n'
        % (warning_prefix,)
        )
  else:
    anydbm._defaultmod = gdbm


class Database:
  """A database that uses a Serializer to store objects of a certain type.

  The serializer is stored in the database under the key
  self.serializer_key.  (This implies that self.serializer_key may not
  be used as a key for normal entries.)

  The backing database is an anydbm-based DBM.

  """

  serializer_key = '_.%$1\t;_ '

  def __init__(self, filename, mode, serializer=None):
    """Constructor.

    The database stores its Serializer, so none needs to be supplied
    when opening an existing database."""

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
    if mode == DB_OPEN_NEW and anydbm._defaultmod.__name__ == 'dbhash':
      if os.path.isfile(filename):
        os.unlink(filename)
      self.db = anydbm.open(filename, 'c')
    else:
      self.db = anydbm.open(filename, mode)

    # Import implementations for many mapping interface methods.
    for meth_name in ('__delitem__',
        '__iter__', 'has_key', '__contains__', 'iterkeys', 'clear'):
      meth_ref = getattr(self.db, meth_name, None)
      if meth_ref:
        setattr(self, meth_name, meth_ref)

    if mode == DB_OPEN_NEW:
      self.serializer = serializer
      self.db[self.serializer_key] = cPickle.dumps(self.serializer)
    else:
      self.serializer = cPickle.loads(self.db[self.serializer_key])

  def __getitem__(self, key):
    return self.serializer.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = self.serializer.dumps(value)

  def __delitem__(self, key):
    # gdbm defines a __delitem__ method, but it cannot be assigned.  So
    # this method provides a fallback definition via explicit delegation:
    del self.db[key]

  def keys(self):
    retval = self.db.keys()
    retval.remove(self.serializer_key)
    return retval

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

  def close(self):
    self.db.close()
    self.db = None


