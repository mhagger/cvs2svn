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

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.record_table import FileOffsetPacker
from cvs2svn_lib.record_table import RecordTable


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
if anydbm._defaultmod.__name__ in ['dumbdbm', 'dbm']:
  Log().error(
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
    Log().warn(
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


class IndexedDatabase:
  """A file of objects that are written sequentially and read randomly.

  The objects are indexed by small non-negative integers, and a
  RecordTable is used to store the index -> fileoffset map.
  fileoffset=0 is used to represent an empty record.  (An offset of 0
  cannot occur for a legitimate record because the serializer is
  written there.)

  The main file consists of a sequence of pickles (or other serialized
  data format).  The zeroth record is a pickled Serializer.
  Subsequent ones are objects serialized using the serializer.  The
  offset of each object in the file is stored to an index table so
  that the data can later be retrieved randomly.

  Objects are always stored to the end of the file.  If an object is
  deleted or overwritten, the fact is recorded in the index_table but
  the space in the pickle file is not garbage collected.  This has the
  advantage that one can create a modified version of a database that
  shares the main data file with an old version by copying the index
  file.  But it has the disadvantage that space is wasted whenever
  objects are written multiple times."""

  def __init__(self, filename, index_filename, mode, serializer=None):
    """Initialize an IndexedDatabase, writing the serializer if necessary.

    SERIALIZER is only used if MODE is DB_OPEN_NEW; otherwise the
    serializer is read from the file."""

    self.filename = filename
    self.index_filename = index_filename
    self.mode = mode
    if self.mode == DB_OPEN_NEW:
      self.f = open(self.filename, 'wb+')
    elif self.mode == DB_OPEN_WRITE:
      self.f = open(self.filename, 'rb+')
    elif self.mode == DB_OPEN_READ:
      self.f = open(self.filename, 'rb')
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

    self.index_table = RecordTable(
        self.index_filename, self.mode, FileOffsetPacker()
        )

    if self.mode == DB_OPEN_NEW:
      assert serializer is not None
      self.serializer = serializer
      cPickle.dump(self.serializer, self.f, -1)
    else:
      # Read the memo from the first pickle:
      self.serializer = cPickle.load(self.f)

    # Seek to the end of the file, and record that position:
    self.f.seek(0, 2)
    self.fp = self.f.tell()
    self.eofp = self.fp

  def __setitem__(self, index, item):
    """Write ITEM into the database indexed by INDEX."""

    # Make sure we're at the end of the file:
    if self.fp != self.eofp:
      self.f.seek(self.eofp)
    self.index_table[index] = self.eofp
    s = self.serializer.dumps(item)
    self.f.write(s)
    self.eofp += len(s)
    self.fp = self.eofp

  def _fetch(self, offset):
    if self.fp != offset:
      self.f.seek(offset)

    # There is no easy way to tell how much data will be read, so just
    # indicate that we don't know the current file pointer:
    self.fp = None

    return self.serializer.loadf(self.f)

  def iterkeys(self):
    return self.index_table.iterkeys()

  def itervalues(self):
    for offset in self.index_table.itervalues():
      yield self._fetch(offset)

  def __getitem__(self, index):
    offset = self.index_table[index]
    return self._fetch(offset)

  def get(self, item, default=None):
    try:
      return self[item]
    except KeyError:
      return default

  def get_many(self, indexes, default=None):
    """Yield (index,item) tuples for INDEXES, in arbitrary order.

    Yield (index,default) for indexes with no defined values."""

    offsets = []
    for (index, offset) in self.index_table.get_many(indexes):
      if offset is None:
        yield (index, default)
      else:
        offsets.append((offset, index))

    # Sort the offsets to reduce disk seeking:
    offsets.sort()
    for (offset,index) in offsets:
      yield (index, self._fetch(offset))

  def __delitem__(self, index):
    # We don't actually free the data in self.f.
    del self.index_table[index]

  def close(self):
    self.index_table.close()
    self.index_table = None
    self.f.close()
    self.f = None

  def __str__(self):
    return 'IndexedDatabase(%r)' % (self.filename,)


class IndexedStore(IndexedDatabase):
  """A file of items that is written sequentially and read randomly.

  This is just like IndexedDatabase, except that it has an additional
  add() method which assumes that the object to be written to the
  database has an 'id' member, which is used as its database index.
  See IndexedDatabase for more information."""

  def add(self, item):
    """Write ITEM into the database indexed by ITEM.id."""

    self[item.id] = item


