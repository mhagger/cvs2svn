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

from __future__ import generators

import sys
import os
import shutil
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

from cvs2svn_lib.key_generator import KeyGenerator

tmpdir = 'destroy_repository-tmp'

file_key_generator = KeyGenerator(1)

def get_tmp_filename():
    return os.path.join(tmpdir, 'f%07d.tmp' % file_key_generator.gen_id())


def read_chunks(filename):
    """Generate '@'-delimited chunks of text from FILENAME.

    Each yielded value contains all of the file contents up until the
    next '@'.  The '@' are never included in the output.  The last
    yield value is the part of the file following the last '@'."""

    f = open(filename, 'rb')
    buffer = []
    while True:
        s = f.read(4096)
        if not s:
            # That was the end of the file.  Yield whatever is left in
            # buffer (even if the buffer is empty).
            yield ''.join(buffer)
            return
        while True:
            i = s.find('@')
            if i == -1:
                buffer.append(s)
                break

            buffer.append(s[:i])
            s = s[i + 1:]
            retval = ''.join(buffer)
            buffer = []
            yield retval


def read_merged_chunks(filename):
    """Generate the chunks from a properly-formed RCS file.

    'Properly formed' means that it contains an even number of
    '@'-characters.  A single '@' starts a quoted string.  While in a
    quoted string, a double-'@' stands for a '@' within the string,
    and a single-'@' stands for the end of the string.

    This generator yields

        unquoted, quoted, unquoted, quoted, unquoted, ...

    where 'unquoted' are literal file contents between the quoted
    strings, and 'quoted' are the contents of quoted strings including
    '@@' for any enclosed '@' characters.  This routine will always
    yield an odd number of chunks (or raise a RuntimeError if the RCS
    file was malformed)."""

    chunk_generator = read_chunks(filename)

    # Yield the first chunk (before any '@'):
    try:
        yield chunk_generator.next()

        # Each iteration of this loop produces one merged quoted
        # string and the non-quoted part that comes after it:
        while True:
            # The file is positioned at the first chunk of a quoted string
            # (or end of file).  First read all chunks that belong to this
            # quoted string into chunks_to_merge.

            # The following line is allowed to raise StopIteration; it
            # simply means that the end of the file has been reached:
            try:
                chunks_to_merge = [chunk_generator.next()]
            except StopIteration:
                return

            while True:
                next_chunk = chunk_generator.next()

                if next_chunk:
                    # The quoted string is over and next_chunk is what
                    # comes next.  First yield the quoted string:
                    retval = '@@'.join(chunks_to_merge)
                    chunks_to_merge = None
                    yield retval

                    # Now yield the non-quoted stuff that follows it:
                    yield next_chunk

                    break

                # An empty trunk following a quoted string
                # indicates that the chunk continues:
                chunks_to_merge.append(chunk_generator.next())

    except StopIteration, e:
        # This shouldn't happen--all legitimate StopIterations have
        # been caught within the body of this try.
        traceback.print_exc()
        raise RuntimeError(
            'RCS file has invalid quoting structure.\n%r\n' % e
            )


class FileDestroyer:
    def __init__(self):
        pass

    def destroy_file(self, filename):
        chunk_generator = read_merged_chunks(filename)

        tmp_filename = get_tmp_filename()
        f = open(tmp_filename, 'wb')

        while True:
            try:
                unquoted = chunk_generator.next()
            except StopIteration, e:
                # This shouldn't happen--read_merged_chunks promises to yield
                # an odd number of chunks.
                raise RuntimeError('RCS file has invalid quoting structure')

            f.write(unquoted)

            try:
                quoted = chunk_generator.next()
            except StopIteration, e:
                # No problem--this is a legitimate end-of-file:
                break

            # Now allow the contents of unquoted to affect the processing
            # of quoted:

            if unquoted.endswith('\ntext\n'):
                quoted = ''

            # Now write the (possibly altered) quoted string:
            f.write('@')
            f.write(quoted)
            f.write('@')

        f.close()

        # Replace the original file with the new one:
        os.remove(filename)
        shutil.move(tmp_filename, filename)

    def visit(self, dirname, names):
        for name in names:
            path = os.path.join(dirname, name)
            if os.path.isfile(path) and path.endswith(',v'):
                sys.stderr.write('Destroying %s...' % path)
                self.destroy_file(path)
                sys.stderr.write('done.\n')
            elif os.path.isdir(path):
                # Subdirectories are traversed automatically
                pass
            else:
                sys.stderr.write('File %s is being ignored.\n' % path)

    def destroy_dir(self, path):
        os.path.walk(path, FileDestroyer.visit, self)


if __name__ == '__main__':
    if not os.path.isdir(tmpdir):
        os.makedirs(tmpdir)

    file_destroyer = FileDestroyer()

    for path in sys.argv[1:]:
        if os.path.isfile(path) and path.endswith(',v'):
            file_destroyer.destroy_file(path)
        elif os.path.isdir(path):
            file_destroyer.destroy_dir(path)
        else:
            sys.stderr.write('File %s is being ignored.\n' % path)


