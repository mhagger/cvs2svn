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

"""This module contains a database that can store arbitrary CVSItems."""


import re
import cPickle

from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSBranchNoop
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.cvs_item import CVSTagNoop
from cvs2svn_lib.cvs_file_items import CVSFileItems
from cvs2svn_lib.serializer import Serializer
from cvs2svn_lib.serializer import PrimedPickleSerializer
from cvs2svn_lib.indexed_database import IndexedStore


cvs_item_primer = (
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
        cvs_item_primer + (CVSFileItems,)
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


class LinewiseSerializer(Serializer):
  """A serializer that writes exactly one line for each object.

  The actual serialization is done by a wrapped serializer; this class
  only escapes any newlines in the serialized data then appends a
  single newline."""

  def __init__(self, wrapee):
    self.wrapee = wrapee

  @staticmethod
  def _encode_newlines(s):
    """Return s with newlines and backslashes encoded.

    The string is returned with the following character transformations:

      LF -> \n
      CR -> \r
      ^Z -> \z (needed for Windows)
      \ -> \\

    """

    return s.replace('\\', '\\\\') \
            .replace('\n', '\\n') \
            .replace('\r', '\\r') \
            .replace('\x1a', '\\z')

  _escape_re = re.compile(r'(\\\\|\\n|\\r|\\z)')
  _subst = {'\\n' : '\n', '\\r' : '\r', '\\z' : '\x1a', '\\\\' : '\\'}

  @staticmethod
  def _decode_newlines(s):
    """Return s with newlines and backslashes decoded.

    This function reverses the encoding of _encode_newlines().

    """

    def repl(m):
      return LinewiseSerializer._subst[m.group(1)]

    return LinewiseSerializer._escape_re.sub(repl, s)

  def dumpf(self, f, object):
    f.write(self.dumps(object))

  def dumps(self, object):
    return self._encode_newlines(self.wrapee.dumps(object)) + '\n'

  def loadf(self, f):
    return self.loads(f.readline())

  def loads(self, s):
    return self.wrapee.loads(self._decode_newlines(s[:-1]))


class NewSortableCVSRevisionDatabase(object):
  """A serially-accessible, sortable file for holding CVSRevisions.

  This class creates such files."""

  def __init__(self, filename, serializer):
    self.f = open(filename, 'w')
    self.serializer = LinewiseSerializer(serializer)

  def add(self, cvs_rev):
    self.f.write(
        '%x %08x %s' % (
            cvs_rev.metadata_id, cvs_rev.timestamp,
            self.serializer.dumps(cvs_rev),
            )
        )

  def close(self):
    self.f.close()
    self.f = None


class OldSortableCVSRevisionDatabase(object):
  """A serially-accessible, sortable file for holding CVSRevisions.

  This class reads such files."""

  def __init__(self, filename, serializer):
    self.filename = filename
    self.serializer = LinewiseSerializer(serializer)

  def __iter__(self):
    f = open(self.filename, 'r')
    for l in f:
      s = l.split(' ', 2)[-1]
      yield self.serializer.loads(s)
    f.close()

  def close(self):
    pass


class NewSortableCVSSymbolDatabase(object):
  """A serially-accessible, sortable file for holding CVSSymbols.

  This class creates such files."""

  def __init__(self, filename, serializer):
    self.f = open(filename, 'w')
    self.serializer = LinewiseSerializer(serializer)

  def add(self, cvs_symbol):
    self.f.write(
        '%x %s' % (cvs_symbol.symbol.id, self.serializer.dumps(cvs_symbol))
        )

  def close(self):
    self.f.close()
    self.f = None


class OldSortableCVSSymbolDatabase(object):
  """A serially-accessible, sortable file for holding CVSSymbols.

  This class reads such files."""

  def __init__(self, filename, serializer):
    self.filename = filename
    self.serializer = LinewiseSerializer(serializer)

  def __iter__(self):
    f = open(self.filename, 'r')
    for l in f:
      s = l.split(' ', 1)[-1]
      yield self.serializer.loads(s)
    f.close()

  def close(self):
    pass


def IndexedCVSItemStore(filename, index_filename, mode):
  return IndexedStore(
      filename, index_filename, mode,
      PrimedPickleSerializer(cvs_item_primer)
      )


