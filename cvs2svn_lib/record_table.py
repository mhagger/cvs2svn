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

"""Classes to manage Databases of fixed-length records.

The databases map small, non-negative integers to fixed-size records.
The records are written in index order to a disk file.  Gaps in the
index sequence leave gaps in the data file, so for best space
efficiency the indexes of existing records should be approximately
continuous.

To use a RecordTable, you need a class derived from Packer which can
serialize/deserialize your records into fixed-size strings.  Deriving
classes have to specify how to pack records into strings and unpack
strings into records by overwriting the pack() and unpack() methods
respectively.

Note that these classes keep track of gaps in the records that have
been written by filling them with packer.empty_value.  If a record is
read which contains packer.empty_value, then a KeyError is raised."""


import os
import types
import struct
import mmap

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.log import logger


# A unique value that can be used to stand for "unset" without
# preventing the use of None.
_unset = object()


class Packer(object):
  def __init__(self, record_len, empty_value=None):
    self.record_len = record_len
    if empty_value is None:
      self.empty_value = '\0' * self.record_len
    else:
      assert type(empty_value) is types.StringType
      assert len(empty_value) == self.record_len
      self.empty_value = empty_value

  def pack(self, v):
    """Pack record V into a string of length self.record_len."""

    raise NotImplementedError()

  def unpack(self, s):
    """Unpack string S into a record."""

    raise NotImplementedError()


class StructPacker(Packer):
  def __init__(self, format, empty_value=_unset):
    self.format = format
    if empty_value is not _unset:
      empty_value = self.pack(empty_value)
    else:
      empty_value = None

    Packer.__init__(self, struct.calcsize(self.format),
                    empty_value=empty_value)

  def pack(self, v):
    return struct.pack(self.format, v)

  def unpack(self, v):
    return struct.unpack(self.format, v)[0]


class UnsignedIntegerPacker(StructPacker):
  def __init__(self, empty_value=0):
    StructPacker.__init__(self, '=I', empty_value)


class SignedIntegerPacker(StructPacker):
  def __init__(self, empty_value=0):
    StructPacker.__init__(self, '=i', empty_value)


class FileOffsetPacker(Packer):
  """A packer suitable for file offsets.

  We store the 5 least significant bytes of the file offset.  This is
  enough bits to represent 1 TiB.  Of course if the computer
  doesn't have large file support, only the lowest 31 bits can be
  nonzero, and the offsets are limited to 2 GiB."""

  # Convert file offsets to 8-bit little-endian unsigned longs...
  INDEX_FORMAT = '<Q'
  # ...but then truncate to 5 bytes.
  INDEX_FORMAT_LEN = 5

  PAD = '\0' * (struct.calcsize(INDEX_FORMAT) - INDEX_FORMAT_LEN)

  def __init__(self):
    Packer.__init__(self, self.INDEX_FORMAT_LEN)

  def pack(self, v):
    return struct.pack(self.INDEX_FORMAT, v)[:self.INDEX_FORMAT_LEN]

  def unpack(self, s):
    return struct.unpack(self.INDEX_FORMAT, s + self.PAD)[0]


class RecordTableAccessError(RuntimeError):
  pass


class AbstractRecordTable:
  def __init__(self, filename, mode, packer):
    self.filename = filename
    self.mode = mode
    self.packer = packer
    # Simplify and speed access to this oft-needed quantity:
    self._record_len = self.packer.record_len

  def __str__(self):
    return '%s(%r)' % (self.__class__.__name__, self.filename,)

  def _set_packed_record(self, i, s):
    """Set the value for index I to the packed value S."""

    raise NotImplementedError()

  def __setitem__(self, i, v):
    self._set_packed_record(i, self.packer.pack(v))

  def _get_packed_record(self, i):
    """Return the packed record for index I.

    Raise KeyError if it is not present."""

    raise NotImplementedError()

  def __getitem__(self, i):
    """Return the item for index I.

    Raise KeyError if that item has never been set (or if it was set
    to self.packer.empty_value)."""

    s = self._get_packed_record(i)

    if s == self.packer.empty_value:
      raise KeyError(i)

    return self.packer.unpack(s)

  def get_many(self, indexes, default=None):
    """Yield (index, item) typles for INDEXES in arbitrary order.

    Yield (index,default) for indices for which not item is defined."""

    indexes = list(indexes)
    # Sort the indexes to reduce disk seeking:
    indexes.sort()
    for i in indexes:
      yield (i, self.get(i, default))

  def get(self, i, default=None):
    try:
      return self[i]
    except KeyError:
      return default

  def __delitem__(self, i):
    """Delete the item for index I.

    Raise KeyError if that item has never been set (or if it was set
    to self.packer.empty_value)."""

    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()

    # Check that the value was set (otherwise raise KeyError):
    self[i]
    self._set_packed_record(i, self.packer.empty_value)

  def iterkeys(self):
    """Yield the keys in the map in key order."""

    for i in xrange(0, self._limit):
      try:
        self[i]
        yield i
      except KeyError:
        pass

  def itervalues(self):
    """Yield the values in the map in key order.

    Skip over values that haven't been defined."""

    for i in xrange(0, self._limit):
      try:
        yield self[i]
      except KeyError:
        pass


class RecordTable(AbstractRecordTable):
  # The approximate amount of memory that should be used for the cache
  # for each instance of this class:
  CACHE_MEMORY = 4 * 1024 * 1024

  # Empirically, each entry in the cache table has an overhead of
  # about 96 bytes on a 32-bit computer.
  CACHE_OVERHEAD_PER_ENTRY = 96

  def __init__(self, filename, mode, packer, cache_memory=CACHE_MEMORY):
    AbstractRecordTable.__init__(self, filename, mode, packer)
    if self.mode == DB_OPEN_NEW:
      self.f = open(self.filename, 'wb+')
    elif self.mode == DB_OPEN_WRITE:
      self.f = open(self.filename, 'rb+')
    elif self.mode == DB_OPEN_READ:
      self.f = open(self.filename, 'rb')
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)
    self.cache_memory = cache_memory

    # Number of items that can be stored in the write cache.
    self._max_memory_cache = (
        self.cache_memory
        / (self.CACHE_OVERHEAD_PER_ENTRY + self._record_len))

    # Read and write cache; a map {i : (dirty, s)}, where i is an
    # index, dirty indicates whether the value has to be written to
    # disk, and s is the packed value for the index.  Up to
    # self._max_memory_cache items can be stored here.  When the cache
    # fills up, it is written to disk in one go and then cleared.
    self._cache = {}

    # The index just beyond the last record ever written:
    self._limit = os.path.getsize(self.filename) // self._record_len

    # The index just beyond the last record ever written to disk:
    self._limit_written = self._limit

  def flush(self):
    logger.debug('Flushing cache for %s' % (self,))

    pairs = [(i, s) for (i, (dirty, s)) in self._cache.items() if dirty]

    if pairs:
      pairs.sort()
      old_i = None
      f = self.f
      for (i, s) in pairs:
        if i == old_i:
          # No seeking needed
          pass
        elif i <= self._limit_written:
          # Just jump there:
          f.seek(i * self._record_len)
        else:
          # Jump to the end of the file then write _empty_values until
          # we reach the correct location:
          f.seek(self._limit_written * self._record_len)
          while self._limit_written < i:
            f.write(self.packer.empty_value)
            self._limit_written += 1
        f.write(s)
        old_i = i + 1
        self._limit_written = max(self._limit_written, old_i)

      self.f.flush()

    self._cache.clear()

  def _set_packed_record(self, i, s):
    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    if i < 0:
      raise KeyError()
    self._cache[i] = (True, s)
    if len(self._cache) >= self._max_memory_cache:
      self.flush()
    self._limit = max(self._limit, i + 1)

  def _get_packed_record(self, i):
    try:
      return self._cache[i][1]
    except KeyError:
      if not 0 <= i < self._limit_written:
        raise KeyError(i)
      self.f.seek(i * self._record_len)
      s = self.f.read(self._record_len)
      self._cache[i] = (False, s)
      if len(self._cache) >= self._max_memory_cache:
        self.flush()

      return s

  def close(self):
    self.flush()
    self._cache = None
    self.f.close()
    self.f = None


class MmapRecordTable(AbstractRecordTable):
  GROWTH_INCREMENT = 65536

  def __init__(self, filename, mode, packer):
    AbstractRecordTable.__init__(self, filename, mode, packer)
    if self.mode == DB_OPEN_NEW:
      self.python_file = open(self.filename, 'wb+')
      self.python_file.write('\0' * self.GROWTH_INCREMENT)
      self.python_file.flush()
      self._filesize = self.GROWTH_INCREMENT
      self.f = mmap.mmap(
          self.python_file.fileno(), self._filesize,
          access=mmap.ACCESS_WRITE
          )

      # The index just beyond the last record ever written:
      self._limit = 0
    elif self.mode == DB_OPEN_WRITE:
      self.python_file = open(self.filename, 'rb+')
      self._filesize = os.path.getsize(self.filename)
      self.f = mmap.mmap(
          self.python_file.fileno(), self._filesize,
          access=mmap.ACCESS_WRITE
          )

      # The index just beyond the last record ever written:
      self._limit = os.path.getsize(self.filename) // self._record_len
    elif self.mode == DB_OPEN_READ:
      self.python_file = open(self.filename, 'rb')
      self._filesize = os.path.getsize(self.filename)
      self.f = mmap.mmap(
          self.python_file.fileno(), self._filesize,
          access=mmap.ACCESS_READ
          )

      # The index just beyond the last record ever written:
      self._limit = os.path.getsize(self.filename) // self._record_len
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

  def flush(self):
    self.f.flush()

  def _set_packed_record(self, i, s):
    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    if i < 0:
      raise KeyError()
    if i >= self._limit:
      # This write extends the range of valid indices.  First check
      # whether the file has to be enlarged:
      new_size = (i + 1) * self._record_len
      if new_size > self._filesize:
        self._filesize = (
            (new_size + self.GROWTH_INCREMENT - 1)
            // self.GROWTH_INCREMENT
            * self.GROWTH_INCREMENT
            )
        self.f.resize(self._filesize)
      if i > self._limit:
        # Pad up to the new record with empty_value:
        self.f[self._limit * self._record_len:i * self._record_len] = \
            self.packer.empty_value * (i - self._limit)
      self._limit = i + 1

    self.f[i * self._record_len:(i + 1) * self._record_len] = s

  def _get_packed_record(self, i):
    if not 0 <= i < self._limit:
      raise KeyError(i)
    return self.f[i * self._record_len:(i + 1) * self._record_len]

  def close(self):
    self.flush()
    self.f.close()
    self.python_file.close()


