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

The two classes in this module are abstract.  Deriving classes have to
specify how to pack records into strings and unpack strings into
records y overwriting the pack()/unpack() methods.  Arbitrary records
can be written as long as they can be converted to fixed-length
strings.

Note that these classes do not keep track of which records have been
written, aside from keeping track of the highest record number that
was ever written.  If an unwritten record is read, then the unpack()
method will be passes a string containing only NUL characters."""


from __future__ import generators

import os

from cvs2svn_lib.boolean import *


class NewRecordTable:
  def __init__(self, filename, record_len):
    self.f = open(filename, 'wb+')
    self.record_len = record_len
    self.max_memory_cache = 128 * 1024 / self.record_len
    self.cache = {}

  def flush(self):
    pairs = self.cache.items()
    pairs.sort()
    old_i = None
    f = self.f
    for (i, v) in pairs:
      if i != old_i:
        f.seek(i * self.record_len)
      f.write(self.pack(v))
      old_i = i + 1
    self.cache.clear()

  def pack(self, v):
    """Pack record v into a string of length self.record_len."""

    raise NotImplementedError()

  def __setitem__(self, i, v):
    self.cache[i] = v
    if len(self.cache) >= self.max_memory_cache:
      self.flush()

  def close(self):
    self.flush()
    self.f.close()


class OldRecordTable:
  def __init__(self, filename, record_len):
    self.f = open(filename, 'rb')
    self.record_len = record_len
    self.limit = os.path.getsize(filename) // self.record_len

  def unpack(self, s):
    """Unpack string S into a record."""

    raise NotImplementedError()

  def __getitem__(self, i):
    if not 0 <= i < self.limit:
      raise KeyError(i)
    self.f.seek(i * self.record_len)
    s = self.f.read(self.record_len)
    return self.unpack(s)

  def __iter__(self):
    for i in xrange(0, self.limit):
      yield self[i]

  def close(self):
    self.f.close()


