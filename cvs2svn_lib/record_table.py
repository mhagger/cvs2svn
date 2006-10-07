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

Note that these classes do not keep track of which records have been
written, aside from keeping track of the highest record number that
was ever written.  If a record that was never written is read, then
the unpack() method will be passes a string containing only NUL
characters."""


from __future__ import generators

import os
import struct

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW


class Packer(object):
  def __init__(self, record_len):
    self.record_len = record_len

  def pack(self, v):
    """Pack record V into a string of length self.record_len."""

    raise NotImplementedError()

  def unpack(self, s):
    """Unpack string S into a record."""

    raise NotImplementedError()


class StructPacker(Packer):
  def __init__(self, format):
    self.format = format
    Packer.__init__(self, struct.calcsize(self.format))

  def pack(self, v):
    return struct.pack(self.format, v)

  def unpack(self, v):
    return struct.unpack(self.format, v)[0]


class UnsignedIntegerPacker(StructPacker):
  def __init__(self):
    StructPacker.__init__(self, '=I')


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
    self.mode = mode
    if self.mode == DB_OPEN_NEW:
      self.f = open(filename, 'wb+')
    elif self.mode == DB_OPEN_WRITE:
      self.f = open(filename, 'rb+')
    elif self.mode == DB_OPEN_READ:
      self.f = open(filename, 'rb')
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)
    self.packer = packer
    # Number of items that can be stored in the write cache:
    self._max_memory_cache = 128 * 1024 / self.packer.record_len
    # Write cache.  Up to self._max_memory_cache items can be stored
    # here.  When the cache fills up, it is written to disk in one go
    # and then cleared.
    self._cache = {}
    self._limit = os.path.getsize(filename) // self.packer.record_len

  def flush(self):
    pairs = self._cache.items()
    pairs.sort()
    old_i = None
    f = self.f
    for (i, v) in pairs:
      if i != old_i:
        f.seek(i * self.packer.record_len)
      f.write(self.packer.pack(v))
      old_i = i + 1
    self._cache.clear()

  def __setitem__(self, i, v):
    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    if i < 0:
      raise KeyError()
    self._cache[i] = v
    if len(self._cache) >= self._max_memory_cache:
      self.flush()
    self._limit = max(self._limit, i + 1)

  def __getitem__(self, i):
    try:
      return self._cache[i]
    except KeyError:
      if not 0 <= i < self._limit:
        raise KeyError(i)
      self.f.seek(i * self.packer.record_len)
      s = self.f.read(self.packer.record_len)
      return self.packer.unpack(s)

  def __iter__(self):
    for i in xrange(0, self._limit):
      yield self[i]

  def close(self):
    self.flush()
    self.f.close()


