#!/usr/bin/env python -u
# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2009-2010 CollabNet.  All rights reserved.
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

"""Generate git blobs directly from RCS files.

Usage: generate_blobs.py BLOBFILE

To standard input should be written a series of pickles, each of which
contains the following tuple:

(RCSFILE, {CVS_REV : MARK, ...})

indicating which RCS file to read, which CVS revisions should be
written to the blob file, and which marks to give each of the blobs.

Since the tuples are read from stdin, either the calling program has
to write to this program's stdin in binary mode and ensure that this
program's standard input is opened in binary mode (e.g., using
Python's '-u' option) or both can be in text mode *provided* that
pickle protocol 0 is used.

The program does most of its work in RAM, keeping at most one revision
fulltext and one revision deltatext (plus perhaps one or two copies as
scratch space) in memory at a time.  But there are times when the
fulltext of a revision is needed multiple times, for example when
multiple branches sprout from the revision.  In these cases, the
fulltext is written to disk.  If the fulltext is also needed for the
blobfile, then the copy in the blobfile is read again when it is
needed.  If the fulltext is not needed in the blobfile, then it is
written to a temporary file created with Python's tempfile module."""

import sys
import os
import tempfile
import cPickle as pickle

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

from cvs2svn_lib.rcsparser import Sink
from cvs2svn_lib.rcsparser import parse
from cvs2svn_lib.rcs_stream import RCSStream


def read_marks():
  # A map from CVS revision number (e.g., 1.2.3.4) to mark:
  marks = {}
  for l in sys.stdin:
    [rev, mark] = l.strip().split()
    marks[rev] = mark

  return marks


class RevRecord(object):
  def __init__(self, rev, mark=None):
    self.rev = rev
    self.mark = mark

    # The rev whose fulltext is the base for this one's delta.
    self.base = None

    # Other revs that refer to this one as their base text:
    self.refs = set()

    # The (f, offset, length) where the fulltext of this revision can
    # be found:
    self.fulltext = None

  def is_needed(self):
    return bool(self.mark is not None or self.refs)

  def is_written(self):
    return self.fulltext is not None

  def write_blob(self, f, text):
    f.seek(0, 2)
    length = len(text)
    f.write('blob\n')
    f.write('mark :%s\n' % (self.mark,))
    f.write('data %d\n' % (length,))
    offset = f.tell()
    f.write(text)
    f.write('\n')

    self.fulltext = (f, offset, length)

    # This record (with its mark) has now been written, so the mark is
    # no longer needed.  Setting it to None might allow is_needed() to
    # become False:
    self.mark = None

  def write(self, f, text):
    f.seek(0, 2)
    offset = f.tell()
    length = len(text)
    f.write(text)
    self.fulltext = (f, offset, length)

  def read_fulltext(self):
    assert self.fulltext is not None
    (f, offset, length) = self.fulltext
    f.seek(offset)
    return f.read(length)

  def __str__(self):
    if self.mark is not None:
      return '%s (%r): %r, %s' % (
          self.rev, self.mark, self.refs, self.fulltext is not None,
          )
    else:
      return '%s: %r, %s' % (self.rev, self.refs, self.fulltext is not None)


class WriteBlobSink(Sink):
  def __init__(self, blobfile, marks):
    self.blobfile = blobfile

    # A map {rev : RevRecord} for all of the revisions whose fulltext
    # will still be needed:
    self.revrecs = {}

    # The revisions that need marks will definitely be needed, so
    # create records for them now (the rest will be filled in while
    # reading the RCS file):
    for (rev, mark) in marks.items():
      self.revrecs[rev] = RevRecord(rev, mark)

    # The RevRecord of the last fulltext that has been reconstructed,
    # if it still is_needed():
    self.last_revrec = None
    # An RCSStream holding the fulltext of last_revrec:
    self.last_rcsstream = None

    # A file to temporarily hold the fulltexts of revisions for which
    # no blobs are needed:
    self.fulltext_file = tempfile.TemporaryFile()

  def __getitem__(self, rev):
    try:
      return self.revrecs[rev]
    except KeyError:
      revrec = RevRecord(rev)
      self.revrecs[rev] = revrec
      return revrec

  def define_revision(self, rev, timestamp, author, state, branches, next):
    revrec = self[rev]

    if next is not None:
      revrec.refs.add(next)

    revrec.refs.update(branches)

    for dependent_rev in revrec.refs:
      dependent_revrec = self[dependent_rev]
      assert dependent_revrec.base is None
      dependent_revrec.base = rev

  def tree_completed(self):
    """Remove unneeded RevRecords.

    Remove the RevRecords for any revisions whose fulltext will not be
    needed (neither as blob output nor as the base of another needed
    revision)."""

    revrecs_to_remove = [
        revrec
        for revrec in self.revrecs.itervalues()
        if not revrec.is_needed()
        ]
    while revrecs_to_remove:
      revrec = revrecs_to_remove.pop()
      del self.revrecs[revrec.rev]
      if revrec.base is not None:
        base_revrec = self[revrec.base]
        base_revrec.refs.remove(revrec.rev)
        if not base_revrec.is_needed():
          revrecs_to_remove.append(base_revrec)

  def set_revision_info(self, rev, log, text):
    revrec = self.revrecs.get(rev)

    if revrec is None:
      return

    base_rev = revrec.base
    if base_rev is None:
      # This must be the last revision on trunk, for which the
      # fulltext is stored directly in the RCS file:
      assert self.last_revrec is None
      if revrec.mark is not None:
        revrec.write_blob(self.blobfile, text)
      if revrec.is_needed():
        self.last_revrec = revrec
        self.last_rcsstream = RCSStream(text)
    elif self.last_revrec is not None and base_rev == self.last_revrec.rev:
      # Our base revision is stored in self.last_rcsstream.
      self.last_revrec.refs.remove(rev)
      if self.last_revrec.is_needed() and not self.last_revrec.is_written():
        self.last_revrec.write(
            self.fulltext_file, self.last_rcsstream.get_text()
            )
      self.last_rcsstream.apply_diff(text)
      if revrec.mark is not None:
        revrec.write_blob(self.blobfile, self.last_rcsstream.get_text())
      if revrec.is_needed():
        self.last_revrec = revrec
      else:
        self.last_revrec = None
        self.last_rcsstream = None
    else:
      # Our base revision is not stored in self.last_rcsstream; it
      # will have to be obtained from elsewhere.

      # Store the old last_rcsstream if necessary:
      if self.last_revrec is not None:
        if not self.last_revrec.is_written():
          self.last_revrec.write(
              self.fulltext_file, self.last_rcsstream.get_text()
              )
        self.last_revrec = None
        self.last_rcsstream = None

      base_revrec = self[base_rev]
      rcsstream = RCSStream(base_revrec.read_fulltext())
      base_revrec.refs.remove(rev)
      rcsstream.apply_diff(text)
      if revrec.mark is not None:
        revrec.write_blob(self.blobfile, rcsstream.get_text())
      if revrec.is_needed():
        self.last_revrec = revrec
        self.last_rcsstream = rcsstream
      del rcsstream

  def parse_completed(self):
    self.fulltext_file.close()


def main(args):
  [blobfilename] = args
  blobfile = open(blobfilename, 'w+b')
  while True:
    try:
      (rcsfile, marks) = pickle.load(sys.stdin)
    except EOFError:
      break
    f = open(rcsfile, 'rb')
    try:
      parse(f, WriteBlobSink(blobfile, marks))
    finally:
      f.close()

  blobfile.close()


if __name__ == '__main__':
  main(sys.argv[1:])


