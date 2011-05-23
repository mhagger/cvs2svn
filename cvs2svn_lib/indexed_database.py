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


import cPickle

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.record_table import FileOffsetPacker
from cvs2svn_lib.record_table import RecordTable


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


