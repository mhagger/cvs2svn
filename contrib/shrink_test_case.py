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

"""Shrink a test case as much as possible.

!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!! This script irretrievably destroys the CVS repository that it is !!
!! applied to!                                                      !!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Usage: shrink_test_case.py CVSREPO TEST_COMMAND

This script is meant to be used to shrink the size of a CVS repository
that is to be used as a test case for cvs2svn.  It tries to throw out
parts of the repository while preserving the bug.

CVSREPO should be the path of a copy of a CVS archive.  TEST_COMMAND
is a command that should run successfully (i.e., with exit code '0')
if the bug is still present, and fail if the bug is absent."""


import sys
import os
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

from cvs2svn_lib.key_generator import KeyGenerator

verbose = 1

tmpdir = 'shrink_test_case-tmp'

file_key_generator = KeyGenerator(1)

def get_tmp_filename():
    return os.path.join(tmpdir, 'f%07d.tmp' % file_key_generator.gen_id())


class CommandFailedException(Exception):
    pass


def command(cmd, *args):
    if verbose >= 2:
        sys.stderr.write('Running: %s %s...' % (cmd, ' '.join(args),))
    retval = os.spawnlp(os.P_WAIT, cmd, cmd, *args)
    if retval:
        if verbose >= 2:
            sys.stderr.write('failed (%s).\n' % retval)
        raise CommandFailedException(' '.join([cmd] + list(args)))
    else:
        if verbose >= 2:
            sys.stderr.write('succeeded.\n')


class Modification:
    """A reversible modification that can be made to the repository."""

    def modify(self):
        """Modify the repository.

        Store enough information that the change can be reverted."""

        raise NotImplementedError()

    def revert(self):
        """Revert this modification."""

        raise NotImplementedError()

    def commit(self):
        """Make this modification permanent."""

        raise NotImplementedError()

    def try_mod(self):
        self.modify()
        try:
            command(*test_command)
        except CommandFailedException:
            if verbose >= 1:
                sys.stdout.write(
                    'The bug disappeared after the following modifications '
                    '(which were reverted):\n'
                    )
                self.output(sys.stdout, '  ')
            else:
                sys.stdout.write(
                    'Attempted modification unsuccessful.\n'
                    )
            self.revert()
            return False
        else:
            self.commit()
            sys.stdout.write(
                'The bug remains after the following modifications:\n'
                )
            self.output(sys.stdout, '  ')
            return True

    def output(self, f, prefix=''):
        raise NotImplementedError()

    def __repr__(self):
        return str(self)


class CompoundModification(Modification):
    def __init__(self, modifications):
        self.modifications = modifications

    def modify(self):
        for modification in self.modifications:
            modification.modify()

    def revert(self):
        for modification in self.modifications:
            modification.revert()

    def commit(self):
        for modification in self.modifications:
            modification.commit()

    def output(self, f, prefix=''):
        for modification in self.modifications:
            modification.output(f, prefix=prefix)

    def __str__(self):
        return str(self.modifications)


class DeleteDirectoryModification(Modification):
    def __init__(self, path):
        self.path = path

    def modify(self):
        self.tempfile = get_tmp_filename()
        shutil.move(self.path, self.tempfile)

    def revert(self):
        shutil.move(self.tempfile, self.path)
        self.tempfile = None

    def commit(self):
        shutil.rmtree(self.tempfile)
        self.tempfile = None

    def output(self, f, prefix=''):
        f.write('%sDeleted directory %r\n' % (prefix, self.path,))

    def __str__(self):
        return 'DeleteDirectory(%r)' % self.path


class DeleteFileModification(Modification):
    def __init__(self, path):
        self.path = path

    def modify(self):
        self.tempfile = get_tmp_filename()
        shutil.move(self.path, self.tempfile)

    def revert(self):
        shutil.move(self.tempfile, self.path)
        self.tempfile = None

    def commit(self):
        os.remove(self.tempfile)
        self.tempfile = None

    def output(self, f, prefix=''):
        f.write('%sDeleted file %r\n' % (prefix, self.path,))

    def __str__(self):
        return 'DeleteFile(%r)' % self.path


def try_modification_combinations(mods):
    """Try to do as many modifications from the list as possible.

    Return True if any modifications were successful."""

    # A list of lists of modifications that should still be tried:
    todo = [mods]

    retval = False

    while todo:
        mods = todo.pop(0)
        if not mods:
            continue
        elif len(mods) == 1:
            retval = retval | mods[0].try_mod()
        elif CompoundModification(mods).try_mod():
            # All modifications, together, worked.
            retval = True
        else:
            # We can't do all of them at once.  Try doing subsets of each
            # half of the list:
            n = len(mods) // 2
            todo.extend([mods[:n], mods[n:]])

    return retval


def get_dirs(path):
    for filename in os.listdir(path):
        subdir = os.path.join(path, filename)
        if os.path.isdir(subdir):
            yield subdir


def get_files(path):
    for filename in os.listdir(path):
        subdir = os.path.join(path, filename)
        if os.path.isfile(subdir):
            yield subdir


def try_delete_subdirs(path):
    """Try to delete subdirectories under PATH (recursively)."""

    # First try to delete the subdirectories themselves:
    mods = [
        DeleteDirectoryModification(subdir)
        for subdir in get_dirs(path)
        ]
    try_modification_combinations(mods)

    # Now recurse into any remaining subdirectories and do the same:
    for subdir in get_dirs(path):
        try_delete_subdirs(subdir)


def try_delete_files(path):
    mods = [
        DeleteFileModification(filename)
        for filename in get_files(path)
        ]

    try_modification_combinations(mods)

    # Now recurse into any remaining subdirectories and do the same:
    for subdir in get_dirs(path):
        try_delete_files(subdir)


cvsrepo = sys.argv[1]
test_command = sys.argv[2:]


if not os.path.isdir(tmpdir):
    os.makedirs(tmpdir)


# Verify that test_command succeeds with the original repository:
try:
    command(*test_command)
except CommandFailedException, e:
    sys.stderr.write(
        'ERROR!  The test command failed with the original repository.\n'
        'The test command should be designed so that it succeeds\n'
        '(indicating that the bug is still present) with the original\n'
        'repository, and fails only after the bug disappears.\n'
        'Please fix your test command and start again.\n'
        )
    sys.exit(1)

try_delete_subdirs(cvsrepo)
try_delete_files(cvsrepo)
