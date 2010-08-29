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

"""Search a directory for files whose names contain illegal characters.

Usage: find_illegal_filenames.py PATH ...

PATH should be a directory.  It will be traversed looking for
filenames that contain characters that are not allowed in paths in an
SVN archive."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.output_option import OutputOption


def visit_directory(unused, dirname, files):
    for file in files:
        path = os.path.join(dirname, file)
        try:
            OutputOption().verify_filename_legal(file)
        except FatalError:
            sys.stderr.write('File %r contains illegal characters!\n' % path)


if not sys.argv[1:]:
    sys.stderr.write('usage: %s PATH ...\n' % sys.argv[0])
    sys.exit(1)

for path in sys.argv[1:]:
    os.path.walk(path, visit_directory, None)

