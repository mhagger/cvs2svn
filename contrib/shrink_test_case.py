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
import getopt

sys.path.insert(0, os.path.dirname(os.path.dirname(sys.argv[0])))

from cvs2svn_lib.key_generator import KeyGenerator

usage_string = """\
USAGE: %(progname)s [OPT...] CVSREPO TEST_COMMAND

  CVSREPO is the path to a CVS repository.

  ***THE REPOSITORY WILL BE DESTROYED***

  TEST_COMMAND is a command that runs successfully (i.e., with exit
  code '0') if the bug is still present, and fails if the bug is
  absent.

Valid options:
  --skip-initial-test  Assume that the bug is present when run on the initial
                       repository.  Usually this fact is verified
                       automatically.
  --help, -h           Print this usage message.
"""


verbose = 1

tmpdir = 'shrink_test_case-tmp'

file_key_generator = KeyGenerator(1)


def usage(f=sys.stderr):
    f.write(usage_string % {'progname' : sys.argv[0]})


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

    def get_size(self):
        """Return the estimated size of this modification.

        This should be approximately the number of bytes by which the
        problem will be shrunk if this modification is successful.  It
        is used to choose the order to attempt the modifications."""

        raise NotImplementedError()

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

    def try_mod(self, test_command):
        if verbose >= 1:
            sys.stdout.write('Testing with the following modifications:\n')
            self.output(sys.stdout, '  ')
        self.modify()
        try:
            test_command()
        except CommandFailedException:
            if verbose >= 1:
                sys.stdout.write(
                    'The bug disappeared.  Reverting modifications.\n'
                    )
            else:
                sys.stdout.write('Attempted modification unsuccessful.\n')
            self.revert()
            return False
        except KeyboardInterrupt:
            sys.stderr.write('Interrupted.  Reverting last modifications.\n')
            self.revert()
            raise
        except Exception:
            sys.stderr.write(
                'Unexpected exception.  Reverting last modifications.\n'
                )
            self.revert()
            raise
        else:
            self.commit()
            if verbose >= 1:
                sys.stdout.write('The bug remains.  Keeping modifications.\n')
            else:
                sys.stdout.write(
                    'The bug remains after the following modifications:\n'
                    )
                self.output(sys.stdout, '  ')
            return True

    def get_submodifications(self, success):
        """Return a generator or iterable of submodifications.

        Return submodifications that should be tried after this this
        modification.  SUCCESS specifies whether this modification was
        successful."""

        return []

    def output(self, f, prefix=''):
        raise NotImplementedError()

    def __repr__(self):
        return str(self)


class EmptyModificationListException(Exception):
    pass


class SplitModification(Modification):
    """Holds two modifications split out of a failing modification.

    Because the original modification failed, it known that mod1+mod2
    can't succeed.  So if mod1 succeeds, mod2 need not be attempted
    (though its submodifications are attempted)."""

    def __init__(self, mod1, mod2):
        # Choose mod1 to be the larger modification:
        if mod2.get_size() > mod1.get_size():
            mod1, mod2 = mod2, mod1

        self.mod1 = mod1
        self.mod2 = mod2

    def get_size(self):
        return self.mod1.get_size()

    def modify(self):
        self.mod1.modify()

    def revert(self):
        self.mod1.revert()

    def commit(self):
        self.mod1.commit()

    def get_submodifications(self, success):
        if success:
            for mod in self.mod2.get_submodifications(False):
                yield mod
        else:
            yield self.mod2

        for mod in self.mod1.get_submodifications(success):
            yield mod

    def output(self, f, prefix=''):
        self.mod1.output(f, prefix=prefix)

    def __str__(self):
        return 'SplitModification(%s, %s)' % (self.mod1, self.mod2,)


class CompoundModification(Modification):
    def __init__(self, modifications):
        if not modifications:
            raise EmptyModificationListException()
        self.modifications = modifications
        self.size = sum(mod.get_size() for mod in self.modifications)

    def get_size(self):
        return self.size

    def modify(self):
        for modification in self.modifications:
            modification.modify()

    def revert(self):
        for modification in self.modifications:
            modification.revert()

    def commit(self):
        for modification in self.modifications:
            modification.commit()

    def get_submodifications(self, success):
        if success:
            # All modifications were completed successfully; no need
            # to try subsets:
            pass
        elif len(self.modifications) == 1:
            # Our modification list cannot be subdivided, but maybe
            # the remaining modification can:
            for mod in self.modifications[0].get_submodifications(False):
                yield mod
        else:
            # Create subsets of each half of the list and put them in
            # a SplitModification:
            n = len(self.modifications) // 2
            yield SplitModification(
                create_modification(self.modifications[:n]),
                create_modification(self.modifications[n:])
                )

    def output(self, f, prefix=''):
        for modification in self.modifications:
            modification.output(f, prefix=prefix)

    def __str__(self):
        return str(self.modifications)


def create_modification(mods):
    """Create and return a Modification based on the iterable MODS.

    Raise EmptyModificationListException if mods is empty."""

    mods = list(mods)
    if len(mods) == 1:
        return mods[0]
    else:
        return CompoundModification(mods)


def compute_dir_size(path):
    size = 0L
    for filename in os.listdir(path):
        subpath = os.path.join(path, filename)
        if os.path.isdir(subpath):
            size += compute_dir_size(subpath)
        elif os.path.isfile(subpath):
            size += os.path.getsize(subpath)

    return size


class DeleteDirectoryModification(Modification):
    def __init__(self, path):
        self.path = path
        self.size = compute_dir_size(self.path)

    def get_size(self):
        return self.size

    def modify(self):
        self.tempfile = get_tmp_filename()
        shutil.move(self.path, self.tempfile)

    def revert(self):
        shutil.move(self.tempfile, self.path)
        self.tempfile = None

    def commit(self):
        shutil.rmtree(self.tempfile)
        self.tempfile = None

    def get_submodifications(self, success):
        if success:
            # The whole directory could be deleted; no need to recurse:
            pass
        else:
            # Try deleting subdirectories:
            mods = [
                DeleteDirectoryModification(subdir)
                for subdir in get_dirs(self.path)
                ]
            if mods:
                yield create_modification(mods)

            # Try deleting files:
            mods = [
                DeleteFileModification(filename)
                for filename in get_files(self.path)
                ]
            if mods:
                yield create_modification(mods)

    def output(self, f, prefix=''):
        f.write('%sDeleted directory %r\n' % (prefix, self.path,))

    def __str__(self):
        return 'DeleteDirectory(%r)' % self.path


class DeleteFileModification(Modification):
    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(self.path)

    def get_size(self):
        return self.size

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


def try_modification_combinations(test_command, mod):
    """Try MOD and its submodifications.

    Return True if any modifications were successful."""

    # A list of lists of modifications that should still be tried:
    todo = [mod]

    while todo:
        todo.sort(key=lambda mod: mod.get_size())
        mod = todo.pop()
        success = mod.try_mod(test_command)
        # Now add possible submodifications to the list of things to try:
        todo.extend(mod.get_submodifications(success))


def get_dirs(path):
    filenames = os.listdir(path)
    filenames.sort()
    for filename in filenames:
        subpath = os.path.join(path, filename)
        if os.path.isdir(subpath):
            yield subpath


def get_files(path):
    filenames = os.listdir(path)
    filenames.sort()
    for filename in filenames:
        subpath = os.path.join(path, filename)
        if os.path.isfile(subpath):
            yield subpath


try:
    opts, args = getopt.getopt(sys.argv[1:], 'h', [
        'skip-initial-test',
        'help',
        ])
except getopt.GetoptError, e:
    sys.stderr.write('Unknown option: %s\n' % (e,))
    usage()
    sys.exit(1)


skip_initial_test = False

for opt, value in opts:
    if opt in ['--skip-initial-test']:
        skip_initial_test = True
    elif opt in ['-h', '--help']:
        usage(sys.stdout)
        sys.exit(0)
    else:
        sys.exit('Internal error')


cvsrepo = args[0]

def test_command():
    command(*args[1:])

if not os.path.isdir(tmpdir):
    os.makedirs(tmpdir)

if not skip_initial_test:
    # Verify that test_command succeeds with the original repository:
    try:
        test_command()
    except CommandFailedException, e:
        sys.stderr.write(
            'ERROR!  The test command failed with the original repository.\n'
            'The test command should be designed so that it succeeds\n'
            '(indicating that the bug is still present) with the original\n'
            'repository, and fails only after the bug disappears.\n'
            'Please fix your test command and start again.\n'
            )
        sys.exit(1)
    sys.stdout.write(
        'The bug is confirmed to exist in the initial repository.\n'
        )


try:
    try:
        try_modification_combinations(
            test_command, DeleteDirectoryModification(cvsrepo)
            )
    except KeyboardInterrupt:
        pass
finally:
    os.rmdir(tmpdir)


