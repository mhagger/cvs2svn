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

"""Strip the text content out of RCS-format files.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!! This script irretrievably destroys any RCS files that it is applied to! !!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Usage: destroy_repository.py PATH ...

Each PATH that is a *,v file will be stripped.

Each PATH that is a directory will be traversed and all of its *,v
files stripped.

Other PATHs will be ignored.

The *,v files must be writable by the user running the script.
Typically CVS repositories are read-only, so you might have to run
something like

    $ chmod -R ug+w my/repo/path

before running this script.

Most cvs2svn behavior is completely independent of the text contained
in an RCS file.  (The text is not even looked at until OutputPass.)

The idea is to use this script when preparing test cases for problems
that you experience with cvs2svn.  Instead of sending us your whole
CVS repository, you should:

1. Make a copy of the original repository

2. Run this script on the copy (NEVER ON THE ORIGINAL!!!)

3. Verify that the problem still exists when you use cvs2svn to
   convert the 'destroyed' copy

4. Send us the 'destroyed' copy along with the exact cvs2svn version
   that you used, the exact command line that you used to start the
   conversion, and the options file if you used one.

The 'destroyed' copy has a couple of advantages:

* It is much smaller than the original.

* Some of the proprietary information that might have been in the file
  texts of the original repository has been deleted.  Note that this
  script does NOT obliterate other information that might also be
  considered proprietary: log messages, file names, author names,
  commit dates, etc.  In fact, it's not guaranteed even to obliterate
  all of the file text, or to do anything else for that matter.

"""

import sys
import os

def destroy_file(filename):
    text = open(filename, 'rb').read()
    chunks = text.split('@')

    i = 1
    while i < len(chunks):
        # chunks[i] is the first part of a quoted string.  If the next
        # chunk is empty, that means that two '@' came in a row, in
        # which case we delete the empty chunk and merge chunks[i]
        # with chunks[i + 2]:
        chunks_to_merge = [chunks[i]]
        n = i
        while n + 2 < len(chunks) and chunks[n + 1] == '':
            chunks_to_merge.append(chunks[n + 2])
            n += 2

        if n != i:
            chunks[i:n+1] = ['@@'.join(chunks_to_merge)]

        if chunks[i - 1].endswith('text\n'):
            chunks[i] = ''

        i += 2

    open(filename, 'wb').write('@'.join(chunks))


def visit(arg, dirname, names):
    for name in names:
        path = os.path.join(dirname, name)
        if os.path.isfile(path) and path.endswith(',v'):
            sys.stderr.write('Destroying %s...' % path)
            destroy_file(path)
            sys.stderr.write('done.\n')
        elif os.path.isdir(path):
            # Subdirectories are traversed automatically
            pass
        else:
            sys.stderr.write('File %s is being ignored.\n' % path)


def destroy_dir(path):
    os.path.walk(path, visit, None)


for path in sys.argv[1:]:
    if os.path.isfile(path) and path.endswith(',v'):
        destroy_file(path)
    elif os.path.isdir(path):
        destroy_dir(path)
    else:
        sys.stderr.write('File %s is being ignored.\n' % path)


