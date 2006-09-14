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


import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.database import PrimedPDatabase
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.primed_pickle import get_memos
from cvs2svn_lib.primed_pickle import PrimedPickler
from cvs2svn_lib.primed_pickle import PrimedUnpickler


class NewCVSItemStore:
  """A file of sequential CVSItems, grouped by CVSFile.

  The file consists of a sequence of pickles.  The zeroth one is an
  'unpickler_memo' as described in the primed_pickle module.
  Subsequent ones are pickled lists of CVSItems, each list containing
  all of the CVSItems for a single file.

  We don't use a single pickler for all items because the memo would
  grow too large."""

  def __init__(self, filename):
    """Initialize an instance, creating the file and writing the primer."""

    self.f = open(filename, 'wb')

    primer = (CVSRevision, CVSBranch, CVSTag,)
    (pickler_memo, unpickler_memo,) = get_memos(primer)
    self.pickler = PrimedPickler(pickler_memo)
    cPickle.dump(unpickler_memo, self.f, -1)

    self.current_file_id = None
    self.current_file_items = []

  def _flush(self):
    """Write the current items to disk."""

    if self.current_file_items:
      self.pickler.dumpf(self.f, self.current_file_items)
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
    self.f.close()


class OldCVSItemStore:
  """Read a file created by NewCVSItemStore.

  The file must be read sequentially, except that it is possible to
  read old CVSItems from the current CVSFile."""

  def __init__(self, filename):
    self.f = open(filename, 'rb')

    # Read the memo from the first pickle:
    unpickler_memo = cPickle.load(self.f)
    self.unpickler = PrimedUnpickler(unpickler_memo)

    self.current_file_items = []
    self.current_file_map = {}

  def _read_file_chunk(self):
    self.current_file_items = self.unpickler.loadf(self.f)
    self.current_file_map = {}
    for item in self.current_file_items:
      self.current_file_map[item.id] = item

  def __iter__(self):
    while True:
      try:
        self._read_file_chunk()
      except EOFError:
        return
      for item in self.current_file_items:
        yield item

  def __getitem__(self, id):
    try:
      return self.current_file_map[id]
    except KeyError:
      raise FatalError(
          'Key %r not found within items currently accessible.' % (id,))


class CVSItemDatabase:
  """A Database to store CVSItem objects and retrieve them by their id."""

  def __init__(self, filename, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.db = PrimedPDatabase(
        filename, mode, (CVSRevision, CVSBranch, CVSTag,))

  def add(self, cvs_item):
    """Add CVS_ITEM, a CVSItem, to the database."""

    self.db['%x' % cvs_item.id] = cvs_item

  def __getitem__(self, id):
    """Return the CVSItem stored under ID."""

    return self.db['%x' % (id,)]


