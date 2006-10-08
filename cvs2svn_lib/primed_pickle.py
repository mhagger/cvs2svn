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

"""Picklers and unpicklers that are primed with known objects."""

from __future__ import generators

import cStringIO
import cPickle

from cvs2svn_lib.boolean import *


def get_primed_pickler_pair(primer):
  """Return a tuple (PrimedPickler, PrimedUnpickler) for primer.

  These picklers and unpicklers are 'pre-trained' to recognize the
  objects that are in PRIMER.  (Note that the memos needed for
  pickling and unpickling are different.)"""

  f = cStringIO.StringIO()
  pickler = cPickle.Pickler(f, -1)
  pickler.dump(primer)
  unpickler = cPickle.Unpickler(cStringIO.StringIO(f.getvalue()))
  unpickler.load()
  return PrimedPickler(pickler.memo), PrimedUnpickler(unpickler.memo)


class PrimedPickler:
  """This class acts as a pickler with a pre-initialized memo.

  A new pickler is created for each call to dumpf or dumps, each time
  with the memo initialize to self.memo."""

  def __init__(self, memo):
    """Prepare to make picklers with memos initialized to MEMO."""

    self.memo = memo

  def create_pickler(self, f):
    """Return a new pickler with its memo initialized to SELF.memo."""

    pickler = cPickle.Pickler(f, -1)
    pickler.memo = self.memo.copy()
    return pickler

  def dumpf(self, f, object):
    """Pickle OBJECT to file-like object F.

    A new pickler, initialized with SELF.memo, is used for each call
    to this method."""

    self.create_pickler(f).dump(object)

  def dumps(self, object):
    """Return a string containing OBJECT in pickled form.

    A new pickler, initialized with SELF.memo, is used for each call
    to this method."""

    f = cStringIO.StringIO()
    self.create_pickler(f).dump(object)
    return f.getvalue()


class PrimedUnpickler:
  """This class acts as an unpickler with a pre-initialized memo."""

  def __init__(self, memo):
    """Prepare to make picklers with memos initialized to MEMO."""

    self.memo = memo

  def create_unpickler(self, f):
    """Return a new unpickler with its memo initialized to SELF.memo."""

    unpickler = cPickle.Unpickler(f)
    unpickler.memo = self.memo.copy()
    return unpickler

  def loadf(self, f):
    """Return the next object unpickled from file-like object F.

    A new unpickler, initialized with SELF.memo, is used for each call
    to this method."""

    return self.create_unpickler(f).load()

  def loads(self, s):
    """Return the object unpickled from string S.

    A new unpickler, initialized with SELF.memo, is used for each call
    to this method."""

    return self.create_unpickler(cStringIO.StringIO(s)).load()


