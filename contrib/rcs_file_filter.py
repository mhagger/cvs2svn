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

"""Filter an RCS file."""

from __future__ import generators

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

import cvs2svn_rcsparse


def at_quote(s):
    return '@' + s.replace('@', '@@') + '@'


def format_date(date):
    date_tuple = time.gmtime(date)
    year = date_tuple[0]
    if 1900 <= year <= 1999:
        year = '%02d' % (year - 1900)
    else:
        year = '%04d' % year
    return year + time.strftime('.%m.%d.%H.%M.%S', date_tuple)


class WriteRCSFileSink(cvs2svn_rcsparse.Sink):
    """A Sink that outputs reconstructed RCS file contents."""

    def __init__(self, f):
        """Create a Sink object that will write its output into F.

        F should be a file-like object."""

        self.f = f
        self.head = None
        self.principal_branch = None
        self.accessors = []
        self.symbols = []
        self.lockers = []
        self.locking = None
        self.comment = None
        self.expansion = None

    def set_head_revision(self, revision):
        self.head = revision

    def set_principal_branch(self, branch_name):
        self.principal_branch = branch_name

    def set_access(self, accessors):
        self.accessors = accessors

    def define_tag(self, name, revision):
        self.symbols.append((name, revision,))

    def set_locker(self, revision, locker):
        self.lockers.append((revision, locker,))

    def set_locking(self, mode):
        self.locking = mode

    def set_comment(self, comment):
        self.comment = comment

    def set_expansion(self, mode):
        self.expansion = mode

    def admin_completed(self):
        self.f.write('head\t%s;\n' % self.head)
        if self.principal_branch is not None:
            self.f.write('branch\t%s;\n' % self.principal_branch)
        self.f.write('access')
        for accessor in self.accessors:
            self.f.write('\n\t%s' % accessor)
        self.f.write(';\n')
        self.f.write('symbols')
        for (name, revision) in self.symbols:
            self.f.write('\n\t%s:%s' % (name, revision))
        self.f.write(';\n')
        self.f.write('locks')
        for (revision, locker) in self.lockers:
            self.f.write('\n\t%s:%s' % (locker, revision))
        self.f.write('; %s;\n' % self.locking)
        if self.comment is not None:
            self.f.write('comment\t%s;\n' % at_quote(self.comment))
        if self.expansion is not None:
            self.f.write('expand\t%s;\n' % at_quote(self.expansion))
        self.f.write('\n')

    def define_revision(
        self, revision, timestamp, author, state, branches, next
        ):
        self.f.write(
            '\n%s\ndate\t%s;\tauthor %s;\tstate %s;\n'
            % (revision, format_date(timestamp), author, state,)
            )
        self.f.write('branches')
        for branch in branches:
            self.f.write('\n\t%s' % branch)
        self.f.write(';\n')
        self.f.write('next\t%s;\n' % (next or ''))

    def tree_completed(self):
        pass

    def set_description(self, description):
        self.f.write('\n\ndesc\n%s\n' % at_quote(description))

    def set_revision_info(self, revision, log, text):
        self.f.write('\n')
        self.f.write('\n')
        self.f.write('%s\n' % revision)
        self.f.write('log\n%s\n' % at_quote(log))
        self.f.write('text\n%s\n' % at_quote(text))

    def parse_completed(self):
        pass


if __name__ == '__main__':
    if sys.argv[1:]:
        for path in sys.argv[1:]:
            if os.path.isfile(path) and path.endswith(',v'):
                cvs2svn_rcsparse.parse(
                    open(path, 'rb'), WriteRCSFileSink(sys.stdout)
                    )
            else:
                sys.stderr.write('%r is being ignored.\n' % path)
    else:
        cvs2svn_rcsparse.parse(sys.stdin, WriteRCSFileSink(sys.stdout))


