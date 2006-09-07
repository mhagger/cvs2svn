#! /usr/bin/python

# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006 CollabNet.  All rights reserved.
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

"""Parse an RCS file, showing the rcsparse callbacks that are called.

This program is useful to see whether an RCS file has a problem (in
the sense of not being parseable by rcsparse) and also to illuminate
the correspondence between RCS file contents and rcsparse callbacks.

The output of this program can also be considered to be a kind of
'canonical' format for RCS files, at least in so far as rcsparse
returns all relevant information in the file and provided that the
order of callbacks is always the same."""


from __future__ import generators

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

import cvs2svn_rcsparse


class Logger:
    def __init__(self, name):
        self.name = name

    def __call__(self, *args):
        print '%s(%s)' % (self.name, ', '.join(['%r' % arg for arg in args]),)


class LoggingSink:
    def __init__(self, f):
        self.f = f

    def __getattr__(self, name):
        return Logger(name)


if __name__ == '__main__':
    if sys.argv[1:]:
        for path in sys.argv[1:]:
            if os.path.isfile(path) and path.endswith(',v'):
                cvs2svn_rcsparse.parse(
                    open(path, 'rb'), LoggingSink(sys.stdout)
                    )
            else:
                sys.stderr.write('%r is being ignored.\n' % path)
    else:
        cvs2svn_rcsparse.parse(sys.stdin, LoggingSink(sys.stdout))

