#!/usr/bin/env python
# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2010 CollabNet.  All rights reserved.
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

"""This program tests the RCSStream class.

When executed, this class conducts a number of unit tests of the
RCSStream class.  It requires RCS's 'ci' program to be installed."""

import sys
import os
import shutil
import unittest
import subprocess

SRCPATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, SRCPATH)

import unittest

from cvs2svn_rcsparse import Sink
from cvs2svn_rcsparse import parse
from cvs2svn_lib.rcs_stream import RCSStream

TMPDIR = os.path.join(SRCPATH, 'cvs2svn-tmp')


# Do we require that the inverse of an inverse delta is identical to
# the original delta?  (This is not really required; it would be
# enough if the deltas were functionally the same.)
STRICT_INVERSES = True


class RCSRecorder(Sink):
  def __init__(self):
    self.texts = {}

  def set_revision_info(self, rev, log, text):
    self.texts[rev] = text


class RCSStreamTestCase(unittest.TestCase):
  def __init__(self, name, doc, v1, v2):
    unittest.TestCase.__init__(self)
    self.name = name
    self.doc = doc
    self.v1 = v1
    self.v2 = v2
    self.filename = os.path.join(TMPDIR, 'rcsstream-%s' % self.name, 'a.txt')

  def shortDescription(self):
    return self.doc

  def call(self, *args, **kwargs):
    retcode = subprocess.call(*args, **kwargs)
    self.assertEqual(retcode, 0)

  def setUp(self):
    if not os.path.isdir(os.path.dirname(self.filename)):
      os.makedirs(os.path.dirname(self.filename))
    open(self.filename, 'wb').write(self.v1)
    self.call(
        ['ci', '-q', '-i', '-t-' + self.name, '-mv1', '-l', self.filename],
        )
    open(self.filename, 'wb').write(self.v2)
    self.call(
        ['ci', '-q', '-f', '-mv2', self.filename],
        )

  def applyTest(self, old, delta, new):
    s1 = RCSStream(old)
    self.assertEqual(s1.get_text(), old)
    s1.apply_diff(delta)
    self.assertEqual(s1.get_text(), new)

    s2 = RCSStream(old)
    self.assertEqual(s2.get_text(), old)
    s2.invert_diff(delta)
    self.assertEqual(s2.get_text(), new)

  def runTest(self):
    self.assert_(os.path.isfile(self.filename + ',v'))
    recorder = RCSRecorder()
    parse(open(self.filename + ',v', 'rb'), recorder)
    v2 = recorder.texts['1.2']
    self.assertEqual(v2, self.v2)
    delta = recorder.texts['1.1']
    s = RCSStream(v2)
    self.assertEqual(s.get_text(), self.v2)
    invdelta = s.invert_diff(delta)
    self.assertEqual(s.get_text(), self.v1)
    delta2 = s.invert_diff(invdelta)

    self.applyTest(self.v2, delta, self.v1)
    self.applyTest(self.v1, invdelta, self.v2)

    if STRICT_INVERSES:
      self.assertEqual(delta2, delta)
    elif delta2 != delta:
      self.applyTest(self.v2, delta2, self.v1)

  def tearDown(self):
    shutil.rmtree(os.path.dirname(self.filename))


suite = unittest.TestSuite()


def add_test_pair(name, v1, v2):
  suite.addTest(RCSStreamTestCase(name, name, v1, v2))
  if v1 != v2:
    suite.addTest(RCSStreamTestCase(name + '-reverse', name + '-reverse', v2, v1))


def add_test(name, v1, v2):
  add_test_pair(name, v1, v2)
  if v1.endswith('\n'):
    add_test_pair(name + '-1', v1[:-1], v2)
  if v2.endswith('\n'):
    add_test_pair(name + '-2', v1, v2[:-1])
  if v1.endswith('\n') and  v2.endswith('\n'):
    add_test_pair(name + '-3', v1[:-1], v2[:-1])


add_test('empty', '', '')
add_test('ab-initio', '', 'blah\n')

add_test('delete-at-start', 'a\nb\nc\n', 'b\nc\n')
add_test('delete-in-middle', 'a\nb\nc\n', 'a\nc\n')
add_test('delete-at-end', 'a\nb\nc\n', 'a\nb\n')

add_test('replace-at-start', 'a\nb\nc\n', 'a1\nb\nc\n')
add_test('replace-in-middle', 'a\nb\nc\n', 'a\nb1\nc\n')
add_test('replace-at-end', 'a\nb\nc\n', 'a\nb\nc1\n')

add_test('enlarge-at-start', 'a\nb\nc\n', 'a1\na2\nb\nc\n')
add_test('enlarge-in-middle', 'a\nb\nc\n', 'a\nb1\nb2\nc\n')
add_test('enlarge-at-end', 'a\nb\nc\n', 'a\nb\nc1\nc2\n')


unittest.TextTestRunner(verbosity=2).run(suite)


