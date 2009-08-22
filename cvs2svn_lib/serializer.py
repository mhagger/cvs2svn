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

"""Picklers and unpicklers that are primed with known objects."""


import cStringIO
import marshal
import cPickle
import zlib


class Serializer:
  """An object able to serialize/deserialize some class of objects."""

  def dumpf(self, f, object):
    """Serialize OBJECT to file-like object F."""

    raise NotImplementedError()

  def dumps(self, object):
    """Return a string containing OBJECT in serialized form."""

    raise NotImplementedError()

  def loadf(self, f):
    """Return the next object deserialized from file-like object F."""

    raise NotImplementedError()

  def loads(self, s):
    """Return the object deserialized from string S."""

    raise NotImplementedError()


class MarshalSerializer(Serializer):
  """This class uses the marshal module to serialize/deserialize.

  This means that it shares the limitations of the marshal module,
  namely only being able to serialize a few simple python data types
  without reference loops."""

  def dumpf(self, f, object):
    marshal.dump(object, f)

  def dumps(self, object):
    return marshal.dumps(object)

  def loadf(self, f):
    return marshal.load(f)

  def loads(self, s):
    return marshal.loads(s)


class PrimedPickleSerializer(Serializer):
  """This class acts as a pickler/unpickler with a pre-initialized memo.

  The picklers and unpicklers are 'pre-trained' to recognize the
  objects that are in the primer.  If objects are recognized
  from PRIMER, then only their persistent IDs need to be pickled
  instead of the whole object.  (Note that the memos needed for
  pickling and unpickling are different.)

  A new pickler/unpickler is created for each use, each time with the
  memo initialized appropriately for pickling or unpickling."""

  def __init__(self, primer):
    """Prepare to make picklers/unpicklers with the specified primer.

    The Pickler and Unpickler are 'primed' by pre-pickling PRIMER,
    which can be an arbitrary object (e.g., a list of objects that are
    expected to occur frequently in the objects to be serialized)."""

    f = cStringIO.StringIO()
    pickler = cPickle.Pickler(f, -1)
    pickler.dump(primer)
    self.pickler_memo = pickler.memo

    unpickler = cPickle.Unpickler(cStringIO.StringIO(f.getvalue()))
    unpickler.load()
    self.unpickler_memo = unpickler.memo

  def dumpf(self, f, object):
    """Serialize OBJECT to file-like object F."""

    pickler = cPickle.Pickler(f, -1)
    pickler.memo = self.pickler_memo.copy()
    pickler.dump(object)

  def dumps(self, object):
    """Return a string containing OBJECT in serialized form."""

    f = cStringIO.StringIO()
    self.dumpf(f, object)
    return f.getvalue()

  def loadf(self, f):
    """Return the next object deserialized from file-like object F."""

    unpickler = cPickle.Unpickler(f)
    unpickler.memo = self.unpickler_memo.copy()
    return unpickler.load()

  def loads(self, s):
    """Return the object deserialized from string S."""

    return self.loadf(cStringIO.StringIO(s))


class CompressingSerializer(Serializer):
  """This class wraps other Serializers to compress their serialized data."""

  def __init__(self, wrapee):
    """Constructor.  WRAPEE is the Serializer whose bitstream ought to be
    compressed."""

    self.wrapee = wrapee

  def dumpf(self, f, object):
    marshal.dump(zlib.compress(self.wrapee.dumps(object), 9), f)

  def dumps(self, object):
    return marshal.dumps(zlib.compress(self.wrapee.dumps(object), 9))

  def loadf(self, f):
    return self.wrapee.loads(zlib.decompress(marshal.load(f)))

  def loads(self, s):
    return self.wrapee.loads(zlib.decompress(marshal.loads(s)))


