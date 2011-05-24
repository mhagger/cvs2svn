#! /usr/bin/python

# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (C) 2010 Cabot Communications Ltd.  All rights reserved.
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

"""Usage: renumber_branch.py OLDREVNUM NEWREVNUM PATH...

WARNING: This modifies RCS files in-place.  Make sure you only run
         it on a _copy_ of your repository.  And have backups.

Modify RCS files in PATH to renumber a revision and/or branch.

Will also renumber any revisions on the branch and any branches from
a renumbered revision.  E.g. if you ask to renumber branch 1.3.5
to 1.3.99, it will also renumber revision 1.3.5.1 to 1.3.99.1, and
renumber branch 1.3.5.1.7 to 1.3.99.1.7.  This is usually what you
want.

Originally written to correct a non-standard vendor branch number,
by renumbering the 1.1.2 branch to 1.1.1.  This allows cvs2svn to
detect that it's a vendor branch.

This doesn't enforce all the rules about revision numbers.  It is
possible to make invalid repositories using this tool.

This does try to detect if the specified revision number is already
in use, and fail in that case.

"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvs2svn_lib.rcsparser import parse
from rcs_file_filter import WriteRCSFileSink
from rcs_file_filter import FilterSink


class RenumberingFilter(FilterSink):
    '''A filter that transforms all revision numbers using a
    function provided to the constructor.'''

    def __init__(self, sink, transform_revision_func):
        '''Constructor.

        SINK is the object we're wrapping.  It must implement the
             cvs2svn_rcsparse.Sink interface.
        TRANSFORM_REVISION_FUNC is a function that takes a single
             CVS revision number, as a string, and returns the
             possibly-transformed revision number in the same format.
        '''
        FilterSink.__init__(self, sink)
        self.transform_rev = transform_revision_func

    def set_head_revision(self, revision):
        FilterSink.set_head_revision(self, self.transform_rev(revision))

    def set_principal_branch(self, branch_name):
        FilterSink.set_principal_branch(self, self.transform_rev(branch_name))

    def define_tag(self, name, revision):
        FilterSink.define_tag(self, name, self.transform_rev(revision))

    def define_revision(
            self, revision, timestamp, author, state, branches, next
            ):
        revision = self.transform_rev(revision)
        branches = [self.transform_rev(b) for b in branches]
        if next is not None:
            next = self.transform_rev(next)
        FilterSink.define_revision(
            self, revision, timestamp, author, state, branches, next
            )

    def set_revision_info(self, revision, log, text):
        FilterSink.set_revision_info(self, self.transform_rev(revision),
                                     log, text)


def get_transform_func(rev_from, rev_to, force):
    rev_from_z = '%s.0.%s' % tuple(rev_from.rsplit('.', 1))
    rev_to_z = '%s.0.%s' % tuple(rev_to.rsplit('.', 1))
    def transform_revision(revision):
        if revision == rev_from or revision.startswith(rev_from + '.'):
            revision = rev_to + revision[len(rev_from):]
        elif revision == rev_from_z:
            revision = rev_to_z
        elif not force and (revision == rev_to or revision == rev_to_z
                or revision.startswith(rev_to + '.')):
            raise Exception('Target branch already exists')
        return revision
    return transform_revision

def process_file(filename, rev_from, rev_to, force):
    func = get_transform_func(rev_from, rev_to, force)
    tmp_filename = filename + '.tmp'
    infp = open(filename, 'rb')
    outfp = open(tmp_filename, 'wb')
    try:
        writer = WriteRCSFileSink(outfp)
        revfilter = RenumberingFilter(writer, func)
        parse(infp, revfilter)
    finally:
        outfp.close()
        infp.close()
    os.rename(tmp_filename, filename)

def iter_files_in_dir(top_path):
    for (dirpath, dirnames, filenames) in os.walk(top_path):
        for name in filenames:
            yield os.path.join(dirpath, name)

def iter_rcs_files(list_of_starting_paths, verbose=False):
    for base_path in list_of_starting_paths:
        if os.path.isfile(base_path) and base_path.endswith(',v'):
            yield base_path
        elif os.path.isdir(base_path):
            for file_path in iter_files_in_dir(base_path):
                if file_path.endswith(',v'):
                    yield file_path
                elif verbose:
                    sys.stdout.write('File %s is being ignored.\n' % file_path)
        elif verbose:
            sys.stdout.write('PATH %s is being ignored.\n' % base_path)

def main():
    if len(sys.argv) < 4 or '.' not in sys.argv[1] or '.' not in sys.argv[2]:
        sys.stderr.write('Usage: %s OLDREVNUM NEWREVNUM PATH...\n' % (sys.argv[0],))
        sys.exit(1)

    rev_from = sys.argv[1]
    rev_to = sys.argv[2]
    force = False
    for path in iter_rcs_files(sys.argv[3:], verbose=True):
        sys.stdout.write('Processing %s...' % path)
        process_file(path, rev_from, rev_to, force)
        sys.stdout.write('done.\n')

if __name__ == '__main__':
    main()
