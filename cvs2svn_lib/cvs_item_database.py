# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSBranchNoop
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.cvs_item import CVSTagNoop
from cvs2svn_lib.cvs_file_items import CVSFileItems
from cvs2svn_lib.serializer import PrimedPickleSerializer
from cvs2svn_lib.database import IndexedStore


_cvs_item_primer = (
    CVSRevisionAdd, CVSRevisionChange,
    CVSRevisionDelete, CVSRevisionNoop,
    CVSBranch, CVSBranchNoop,
    CVSTag, CVSTagNoop,
    )


class NewCVSItemStore:
  """A file of sequential CVSItems, grouped by CVSFile.

  The file consists of a sequence of pickles.  The zeroth one is a
  Serializer as described in the serializer module.  Subsequent ones
  are pickled lists of CVSItems, each list containing all of the
  CVSItems for a single file.

  We don't use a single pickler for all items because the memo would
  grow too large."""

  def __init__(self, filename):
    """Initialize an instance, creating the file and writing the primer."""

    self.f = open(filename, 'wb')

    self.serializer = PrimedPickleSerializer(
        _cvs_item_primer + (CVSFileItems,)
        )
    cPickle.dump(self.serializer, self.f, -1)

  def add(self, cvs_file_items):
    """Write CVS_FILE_ITEMS into the database."""

    self.serializer.dumpf(self.f, cvs_file_items)

  def close(self):
    self.f.close()
    self.f = None


class OldCVSItemStore:
  """Read a file created by NewCVSItemStore.

  The file must be read sequentially, one CVSFileItems instance at a
  time."""

  def __init__(self, filename):
    self.f = open(filename, 'rb')

    # Read the memo from the first pickle:
    self.serializer = cPickle.load(self.f)

  def iter_cvs_file_items(self):
    """Iterate through the CVSFileItems instances, one file at a time.

    Each time yield a CVSFileItems instance for one CVSFile."""

    try:
      while True:
        yield self.serializer.loadf(self.f)
    except EOFError:
      return

  def close(self):
    self.f.close()
    self.f = None


def IndexedCVSItemStore(filename, index_filename, mode):
  return IndexedStore(
      filename, index_filename, mode,
      PrimedPickleSerializer(_cvs_item_primer)
      )


