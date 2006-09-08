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
import re
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

from cvs2svn_lib.key_generator import KeyGenerator
import cvs2svn_rcsparse
from rcs_file_filter import WriteRCSFileSink
from rcs_file_filter import FilterSink


tmpdir = 'destroy_repository-tmp'

file_key_generator = KeyGenerator(1)

def get_tmp_filename():
    return os.path.join(tmpdir, 'f%07d.tmp' % file_key_generator.gen_id())


class Substituter:
    def __init__(self, template):
        self.template = template
        self.key_generator = KeyGenerator(1)

        # A map from old values to new ones.
        self.substitutions = {}

    def get_substitution(self, s):
        r = self.substitutions.get(s)
        if r == None:
            r = self.template % self.key_generator.gen_id()
            self.substitutions[s] = r
        return r


class LogSubstituter(Substituter):
    # If a log messages matches any of these regular expressions, it
    # is passed through untouched.
    untouchable_log_res = [
        re.compile(r'^Initial revision\n$'),
        re.compile(r'^file .+ was initially added on branch .+\.\n$'),
        re.compile(r'^\*\*\* empty log message \*\*\*\n$'),
        re.compile(r'^initial checkin$'),
        ]

    def __init__(self):
        Substituter.__init__(self, 'log %d')

    def _is_untouchable(self, log):
        for untouchable_log_re in self.untouchable_log_res:
            if untouchable_log_re.search(log):
                return True
        return False

    def get_substitution(self, log):
        if self._is_untouchable(log):
            return log
        else:
            return Substituter.get_substitution(self, log)


class DestroyerFilterSink(FilterSink):
    def __init__(self, log_substituter, sink):
        FilterSink.__init__(self, sink)

        self.log_substituter = log_substituter

    def set_description(self, description):
        FilterSink.set_description(self, '')

    def set_revision_info(self, revision, log, text):
        FilterSink.set_revision_info(
            self, revision, self.log_substituter.get_substitution(log), ''
            )


class FileDestroyer:
    def __init__(self):
        self.log_substituter = LogSubstituter()

    def destroy_file(self, filename):
        tmp_filename = get_tmp_filename()
        f = open(tmp_filename, 'wb')
        cvs2svn_rcsparse.parse(
            open(filename, 'rb'),
            DestroyerFilterSink(
                self.log_substituter,
                WriteRCSFileSink(f),
                )
            )
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


