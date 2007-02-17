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


from __future__ import generators

import os
import types
import struct

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.log import Log


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


class RecordTable:
  def __init__(self, filename, mode, packer):
    self.filename = filename
    self.mode = mode
    if self.mode == DB_OPEN_NEW:
      self.f = open(self.filename, 'wb+')
    elif self.mode == DB_OPEN_WRITE:
      self.f = open(self.filename, 'rb+')
    elif self.mode == DB_OPEN_READ:
      self.f = open(self.filename, 'rb')
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)
    self.packer = packer

    # Number of items that can be stored in the write cache:
    self._max_memory_cache = 4 * 1024 * 1024 / self.packer.record_len

    # Read and write cache; a map {i : (dirty, s)}, where i is an
    # index, dirty indicates whether the value has to be written to
    # disk, and s is the packed value for the index.  Up to
    # self._max_memory_cache items can be stored here.  When the cache
    # fills up, it is written to disk in one go and then cleared.
    self._cache = {}

    # The index just beyond the last record ever written:
    self._limit = os.path.getsize(self.filename) // self.packer.record_len

    # The index just beyond the last record ever written to disk:
    self._limit_written = self._limit

  def __str__(self):
    return 'RecordTable(%r)' % (self.filename,)

  def flush(self):
    Log().debug('Flushing cache for %s' % (self,))
    pairs = self._cache.items()
    pairs.sort()
    old_i = None
    f = self.f
    for (i, (dirty, s)) in pairs:
      if not dirty:
        continue
      if i == old_i:
        # No seeking needed
        pass
      elif i <= self._limit_written:
        # Just jump there:
        f.seek(i * self.packer.record_len)
      else:
        # Jump to the end of the file then write _empty_values until
        # we reach the correct location:
        f.seek(self._limit_written * self.packer.record_len)
        while self._limit_written < i:
          f.write(self.packer.empty_value)
          self._limit_written += 1
      f.write(s)
      old_i = i + 1
      self._limit_written = max(self._limit_written, old_i)
    self.f.flush()
    self._cache.clear()

  def _set_packed_record(self, i, s):
    """Set the value for index I to the packed value S."""

    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    if i < 0:
      raise KeyError()
    self._cache[i] = (True, s)
    if len(self._cache) >= self._max_memory_cache:
      self.flush()
    self._limit = max(self._limit, i + 1)

  def __setitem__(self, i, v):
    self._set_packed_record(i, self.packer.pack(v))

  def __getitem__(self, i):
    """Return the item for index I.

    Raise KeyError if that item has never been set (or if it was set
    to self.packer.empty_value)."""

    try:
      s = self._cache[i][1]
    except KeyError:
      if not 0 <= i < self._limit_written:
        raise KeyError(i)
      self.f.seek(i * self.packer.record_len)
      s = self.f.read(self.packer.record_len)
      self._cache[i] = (False, s)

    if s == self.packer.empty_value:
      raise KeyError(i)

    return self.packer.unpack(s)

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

  def __iter__(self):
    """Yield the values in the map in key order.

    Skip over values that haven't been defined."""

    for i in xrange(0, self._limit):
      try:
        yield self[i]
      except KeyError:
        pass

  def close(self):
    self.flush()
    self.f.close()


