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
import cStringIO
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.record_table import FileOffsetPacker
from cvs2svn_lib.record_table import RecordTable
from cvs2svn_lib.primed_pickle import get_memos
from cvs2svn_lib.primed_pickle import PrimedPickler
from cvs2svn_lib.primed_pickle import PrimedUnpickler


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
    for meth_name in ('__delitem__',
        '__iter__', 'has_key', '__contains__', 'iterkeys', 'clear'):
      meth_ref = getattr(self.db, meth_name, None)
      if meth_ref:
        setattr(self, meth_name, meth_ref)

  def __delitem__(self, key):
    # gdbm defines a __delitem__ method, but it cannot be assigned.  So
    # this method provides a fallback definition via explicit delegation:
    del self.db[key]

  def keys(self):
    return self.db.keys()

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


class Database(AbstractDatabase):
  """A database that uses the marshal module to store built-in types."""

  def __getitem__(self, key):
    return marshal.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = marshal.dumps(value)


class PDatabase(AbstractDatabase):
  """A database that uses the cPickle module to store arbitrary objects."""

  def __getitem__(self, key):
    return cPickle.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = cPickle.dumps(value, -1)


class PrimedPDatabase(AbstractDatabase):
  """A database that uses cPickle module to store arbitrary objects.

  The Pickler and Unpickler are 'primed' by pre-pickling PRIMER, which
  can be an arbitrary object (e.g., a list of objects that are
  expected to occur frequently in the database entries).  From then
  on, if objects within individual database entries are recognized
  from PRIMER, then only their persistent IDs need to be pickled
  instead of the whole object.

  Concretely, when a new database is created, the pickler memo and
  unpickler memo for PRIMER are computed, pickled, and stored in
  db[self.primer_key] as a tuple.  When an existing database is opened
  for reading or update, the pickler and unpickler memos are read from
  db[self.primer_key].  In either case, these memos are used to
  initialize a PrimedPickler and PrimedUnpickler, which are used for
  future write and read accesses respectively.

  Since the database entry with key self.primer_key is used to store
  the memo, self.primer_key may not be used as a key for normal
  entries."""

  primer_key = '_'

  def __init__(self, filename, mode, primer):
    AbstractDatabase.__init__(self, filename, mode)

    if mode == DB_OPEN_NEW:
      pickler_memo, unpickler_memo = get_memos(primer)
      self.db[self.primer_key] = \
          cPickle.dumps((pickler_memo, unpickler_memo,))
    else:
      (pickler_memo, unpickler_memo,) = \
          cPickle.loads(self.db[self.primer_key])
    self.primed_pickler = PrimedPickler(pickler_memo)
    self.primed_unpickler = PrimedUnpickler(unpickler_memo)

  def __getitem__(self, key):
    return self.primed_unpickler.loads(self.db[key])

  def __setitem__(self, key, value):
    self.db[key] = self.primed_pickler.dumps(value)

  def keys(self):
    retval = self.db.keys()
    retval.remove(self.primer_key)
    return retval


class IndexedStore:
  """A file of items that is written sequentially and read randomly.

  The items are indexed by item.id, which must consist of small
  positive integers, as a RecordTable is used to store the index ->
  fileoffset map and fileoffset=0 is used to represent an empty
  record.

  The main file consists of a sequence of pickles.  The zeroth one is
  a tuple (pickler_memo, unpickler_memo) as described in the
  primed_pickle module.  Subsequent ones are pickled items.  The
  offset of each item in the file is stored to an index table so that
  the data can later be retrieved randomly.

  Objects are always stored to the end of the file.  If an item is
  deleted or overwritten, the fact is recorded in the index_table but
  the space in the pickle file is not garbage collected.  This has the
  advantage that one can create a modified version of a database that
  shares the main pickle file with an old version by copying the index
  file.  But it has the disadvantage that space is wasted whenever
  items are written multiple times."""

  def __init__(self, filename, index_filename, mode, primer=None):
    """Initialize an IndexedStore, writing the primer if necessary.

    PRIMER is only used if MODE is DB_OPEN_NEW; otherwise the primer
    is read from the file."""

    self.mode = mode
    if self.mode == DB_OPEN_NEW:
      self.f = open(filename, 'wb+')
    elif self.mode == DB_OPEN_WRITE:
      self.f = open(filename, 'rb+')
    elif self.mode == DB_OPEN_READ:
      self.f = open(filename, 'rb')
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

    self.index_table = RecordTable(
        index_filename, self.mode, FileOffsetPacker())

    if self.mode == DB_OPEN_NEW:
      (pickler_memo, unpickler_memo,) = get_memos(primer)
      cPickle.dump((pickler_memo, unpickler_memo,), self.f, -1)
    else:
      # Read the memo from the first pickle:
      (pickler_memo, unpickler_memo,) = cPickle.load(self.f)

    self.pickler = PrimedPickler(pickler_memo)
    self.unpickler = PrimedUnpickler(unpickler_memo)

  def add(self, item):
    """Write ITEM into the database indexed by ITEM.id."""

    # Make sure we're at the end of the file:
    self.f.seek(0, 2)
    self.index_table[item.id] = self.f.tell()
    self.pickler.dumpf(self.f, item)

  def _fetch(self, offset):
    self.f.seek(offset)
    return self.unpickler.loadf(self.f)

  def __iter__(self):
    for offset in self.index_table:
      if offset != 0:
        yield self._fetch(offset)

  def __getitem__(self, id):
    offset = self.index_table[id]
    if offset == 0:
      raise KeyError()
    return self._fetch(offset)

  def __delitem__(self, id):
    offset = self.index_table[id]
    if offset == 0:
      raise KeyError()
    self.index_table[id] = 0

  def close(self):
    self.index_table.close()
    self.f.close()


