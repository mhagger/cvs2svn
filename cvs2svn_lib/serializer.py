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


class Serializer:
  """An object able to serialize/deserialize some class of objects."""

  def _create_dumper(self, f):
    """Return a new serializer."""

    raise NotImplementedError()

  def dumpf(self, f, object):
    """Serialize OBJECT to file-like object F."""

    self._create_dumper(f).dump(object)

  def dumps(self, object):
    """Return a string containing OBJECT in serialized form."""

    f = cStringIO.StringIO()
    self._create_dumper(f).dump(object)
    return f.getvalue()

  def _create_loader(self, f):
    """Return a new deserializer."""

    raise NotImplementedError()

  def loadf(self, f):
    """Return the next object deserialized from file-like object F."""

    return self._create_loader(f).load()

  def loads(self, s):
    """Return the object deserialized from string S."""

    return self._create_loader(cStringIO.StringIO(s)).load()


class PrimedPickleSerializer(Serializer):
  """This class acts as a pickler/unpickler with a pre-initialized memo.

  The picklers and unpicklers are 'pre-trained' to recognize the
  objects that are in the primer.  (Note that the memos needed for
  pickling and unpickling are different.)

  A new pickler/unpickler is created for each use, each time with the
  memo initialized appropriately for pickling or unpickling."""

  def __init__(self, primer):
    """Prepare to make picklers/unpicklers with the specified primer."""

    f = cStringIO.StringIO()
    pickler = cPickle.Pickler(f, -1)
    pickler.dump(primer)
    self.pickler_memo = pickler.memo

    unpickler = cPickle.Unpickler(cStringIO.StringIO(f.getvalue()))
    unpickler.load()
    self.unpickler_memo = unpickler.memo

  def _create_dumper(self, f):
    """Return a new pickler with an initialized memo."""

    pickler = cPickle.Pickler(f, -1)
    pickler.memo = self.pickler_memo.copy()
    return pickler

  def _create_loader(self, f):
    """Return a new unpickler with an initialized memo."""

    unpickler = cPickle.Unpickler(f)
    unpickler.memo = self.unpickler_memo.copy()
    return unpickler


