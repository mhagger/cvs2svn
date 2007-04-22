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

"""This module contains a database that can store arbitrary CVSItems."""


from __future__ import generators

import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.cvs_file_items import CVSFileItems
from cvs2svn_lib.serializer import PrimedPickleSerializer
from cvs2svn_lib.database import IndexedStore


class NewCVSItemStore:
  """A file of sequential CVSItems, grouped by CVSFile.

  The file consists of a sequence of pickles.  The zeroth one is a
  (pickler, unpickler) pair as described in the primed_pickle module.
  Subsequent ones are pickled lists of CVSItems, each list containing
  all of the CVSItems for a single file.

  We don't use a single pickler for all items because the memo would
  grow too large."""

  def __init__(self, filename):
    """Initialize an instance, creating the file and writing the primer."""

    self.f = open(filename, 'wb')

    primer = (CVSRevision, CVSBranch, CVSTag,)
    self.serializer = PrimedPickleSerializer(primer)
    cPickle.dump(self.serializer, self.f, -1)

    self.current_file_id = None
    self.current_file_items = []

  def _flush(self):
    """Write the current items to disk."""

    if self.current_file_items:
      self.serializer.dumpf(self.f, self.current_file_items)
      self.current_file_id = None
      self.current_file_items = []

  def add(self, cvs_item):
    """Write cvs_item into the database."""

    if cvs_item.cvs_file.id != self.current_file_id:
      self._flush()
      self.current_file_id = cvs_item.cvs_file.id
    self.current_file_items.append(cvs_item)

  def close(self):
    self._flush()
    self.current_file_items = None
    self.f.close()
    self.f = None


class OldCVSItemStore:
  """Read a file created by NewCVSItemStore.

  The file must be read sequentially, except that it is possible to
  read old CVSItems from the current CVSFile."""

  def __init__(self, filename):
    self.f = open(filename, 'rb')

    # Read the memo from the first pickle:
    self.serializer = cPickle.load(self.f)

    # A list of the CVSItems from the current file, in the order that
    # they were read.
    self.current_file_items = []

    # The CVSFileItems instance for the current file.
    self.cvs_file_items = None

  def _read_file_chunk(self):
    self.current_file_items = self.serializer.loadf(self.f)
    self.cvs_file_items = CVSFileItems(self.current_file_items)

  def __iter__(self):
    while True:
      try:
        self._read_file_chunk()
      except EOFError:
        return
      for item in self.current_file_items:
        yield item

  def iter_cvs_file_items(self):
    """Iterate through the CVSFileItems instances, one file at a time.

    Each time yield a CVSFileItems instance for one CVSFile."""

    while True:
      try:
        self._read_file_chunk()
      except EOFError:
        return
      yield self.cvs_file_items.copy()

  def __getitem__(self, id):
    try:
      return self.cvs_file_items[id]
    except KeyError:
      raise FatalError(
          'Key %r not found within items currently accessible.' % (id,))

  def close(self):
    self.f.close()
    self.f = None
    self.current_file_items = None
    self.cvs_file_items = None


def IndexedCVSItemStore(filename, index_filename, mode):
  return IndexedStore(
      filename, index_filename, mode,
      PrimedPickleSerializer((CVSRevision, CVSBranch, CVSTag,)))


