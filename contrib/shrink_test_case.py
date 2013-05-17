#! /usr/bin/python

# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2008 CollabNet.  All rights reserved.
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

This script is meant to be used to shrink the size of a CVS repository
that is to be used as a test case for cvs2svn.  It tries to throw out
parts of the repository while preserving the bug.

CVSREPO should be the path of a copy of a CVS archive.  TEST_COMMAND
is a command that should run successfully (i.e., with exit code '0')
if the bug is still present, and fail if the bug is absent."""


import sys
import os
import shutil
import optparse
from cStringIO import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvs2svn_lib.key_generator import KeyGenerator

from cvs2svn_lib.rcsparser import Sink
from cvs2svn_lib.rcsparser import parse

from contrib.rcs_file_filter import WriteRCSFileSink
from contrib.rcs_file_filter import FilterSink


usage = 'USAGE: %prog [options] CVSREPO TEST_COMMAND'
description = """\
Simplify a CVS repository while preserving the presence of a bug.

***THE CVS REPOSITORY WILL BE DESTROYED***

CVSREPO is the path to a CVS repository.

TEST_COMMAND is a command that runs successfully (i.e., with exit
code '0') if the bug is still present, and fails if the bug is
absent.
"""


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
    # Add a little bit for the directory itself.
    size = 100L
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


def rev_tuple(revision):
    retval = [int(s) for s in revision.split('.') if int(s)]
    if retval[-2] == 0:
        del retval[-2]
    return tuple(retval)


class RCSFileFilter:
    def get_size(self):
        raise NotImplementedError()

    def get_filter_sink(self, sink):
        raise NotImplementedError()

    def filter(self, text):
        fout = StringIO()
        sink = WriteRCSFileSink(fout)
        filter = self.get_filter_sink(sink)
        parse(StringIO(text), filter)
        return fout.getvalue()

    def get_subfilters(self):
        return []

    def output(self, f, prefix=''):
        raise NotImplementedError()


class DeleteTagRCSFileFilter(RCSFileFilter):
    class Sink(FilterSink):
        def __init__(self, sink, tagname):
            FilterSink.__init__(self, sink)
            self.tagname = tagname

        def define_tag(self, name, revision):
            if name != self.tagname:
                FilterSink.define_tag(self, name, revision)

    def __init__(self, tagname):
        self.tagname = tagname

    def get_size(self):
        return 50

    def get_filter_sink(self, sink):
        return self.Sink(sink, self.tagname)

    def output(self, f, prefix=''):
        f.write('%sDeleted tag %r\n' % (prefix, self.tagname,))


def get_tag_set(path):
    class TagCollector(Sink):
        def __init__(self):
            self.tags = set()

            # A map { branch_tuple : name } for branches on which no
            # revisions have yet been seen:
            self.branches = {}

        def define_tag(self, name, revision):
            revtuple = rev_tuple(revision)
            if len(revtuple) % 2 == 0:
                # This is a tag (as opposed to branch)
                self.tags.add(name)
            else:
                self.branches[revtuple] = name

        def define_revision(
            self, revision, timestamp, author, state, branches, next
            ):
            branch = rev_tuple(revision)[:-1]
            try:
                del self.branches[branch]
            except KeyError:
                pass

        def get_tags(self):
            tags = self.tags
            for branch in self.branches.values():
                tags.add(branch)
            return tags

    tag_collector = TagCollector()
    f = open(path, 'rb')
    try:
        parse(f, tag_collector)
    finally:
        f.close()
    return tag_collector.get_tags()


class DeleteBranchTreeRCSFileFilter(RCSFileFilter):
    class Sink(FilterSink):
        def __init__(self, sink, branch_rev):
            FilterSink.__init__(self, sink)
            self.branch_rev = branch_rev

        def is_on_branch(self, revision):
            revtuple = rev_tuple(revision)
            return revtuple[:len(self.branch_rev)] == self.branch_rev

        def define_tag(self, name, revision):
            if not self.is_on_branch(revision):
                FilterSink.define_tag(self, name, revision)

        def define_revision(
            self, revision, timestamp, author, state, branches, next
            ):
            if not self.is_on_branch(revision):
                branches = [
                    branch
                    for branch in branches
                    if not self.is_on_branch(branch)
                    ]
                FilterSink.define_revision(
                    self, revision, timestamp, author, state, branches, next
                    )

        def set_revision_info(self, revision, log, text):
            if not self.is_on_branch(revision):
                FilterSink.set_revision_info(self, revision, log, text)

    def __init__(self, branch_rev, subbranch_tree):
        self.branch_rev = branch_rev
        self.subbranch_tree = subbranch_tree

    def get_size(self):
        return 100

    def get_filter_sink(self, sink):
        return self.Sink(sink, self.branch_rev)

    def get_subfilters(self):
        for (branch_rev, subbranch_tree) in self.subbranch_tree:
            yield DeleteBranchTreeRCSFileFilter(branch_rev, subbranch_tree)

    def output(self, f, prefix=''):
        f.write(
            '%sDeleted branch %s\n'
            % (prefix, '.'.join([str(s) for s in self.branch_rev]),)
            )


def get_branch_tree(path):
    """Return the forest of branches in path.

    Return [(branch_revision, [sub_branch, ...]), ...], where
    branch_revision is a revtuple and sub_branch has the same form as
    the whole return value.

    """

    class BranchCollector(Sink):
        def __init__(self):
            self.branches = {}

        def define_revision(
            self, revision, timestamp, author, state, branches, next
            ):
            parent = rev_tuple(revision)[:-1]
            if len(parent) == 1:
                parent = (1,)
            entry = self.branches.setdefault(parent, [])
            for branch in branches:
                entry.append(rev_tuple(branch)[:-1])

        def _get_subbranches(self, parent):
            retval = []
            try:
                branches = self.branches[parent]
            except KeyError:
                return []
            del self.branches[parent]
            for branch in branches:
                subbranches = self._get_subbranches(branch)
                retval.append((branch, subbranches,))
            return retval

        def get_branches(self):
            retval = self._get_subbranches((1,))
            assert not self.branches
            return retval

    branch_collector = BranchCollector()
    f = open(path, 'rb')
    try:
        parse(f, branch_collector)
    finally:
        f.close()
    return branch_collector.get_branches()


class RCSFileModification(Modification):
    """A Modification that involves changing the contents of an RCS file."""

    def __init__(self, path, filters):
        self.path = path
        self.filters = filters[:]
        self.size = 0
        for filter in self.filters:
            self.size += filter.get_size()

    def get_size(self):
        return self.size

    def modify(self):
        self.tempfile = get_tmp_filename()
        shutil.move(self.path, self.tempfile)

        f = open(self.tempfile, 'rb')
        try:
            text = f.read()
        finally:
            f.close()

        for filter in self.filters:
            text = filter.filter(text)

        f = open(self.path, 'wb')
        try:
            f.write(text)
        finally:
            f.close()

    def revert(self):
        shutil.move(self.tempfile, self.path)
        self.tempfile = None

    def commit(self):
        os.remove(self.tempfile)
        self.tempfile = None

    def get_submodifications(self, success):
        if success:
            # All filters completed successfully; no need to try
            # subsets:
            pass
        elif len(self.filters) == 1:
            # The last filter failed; see if it has any subfilters:
            subfilters = list(self.filters[0].get_subfilters())
            if subfilters:
                yield RCSFileModification(self.path, subfilters)
        else:
            n = len(self.filters) // 2
            yield SplitModification(
                RCSFileModification(self.path, self.filters[:n]),
                RCSFileModification(self.path, self.filters[n:])
                )

    def output(self, f, prefix=''):
        f.write('%sModified file %r\n' % (prefix, self.path,))
        for filter in self.filters:
            filter.output(f, prefix=(prefix + '  '))

    def __str__(self):
        return 'RCSFileModification(%r)' % (self.filters,)


def try_modification_combinations(test_command, mods):
    """Try MOD and its submodifications.

    Return True if any modifications were successful."""

    # A list of lists of modifications that should still be tried:
    todo = list(mods)

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


def get_files(path, recurse=False):
    filenames = os.listdir(path)
    filenames.sort()
    for filename in filenames:
        subpath = os.path.join(path, filename)
        if os.path.isfile(subpath):
            yield subpath
        elif recurse and os.path.isdir(subpath):
            for x in get_files(subpath, recurse=recurse):
                yield x


def shrink_repository(test_command, cvsrepo):
    try_modification_combinations(
            test_command, [DeleteDirectoryModification(cvsrepo)]
            )

    # Try deleting branches:
    mods = []
    for path in get_files(cvsrepo, recurse=True):
        branch_tree = get_branch_tree(path)
        if branch_tree:
            filters = []
            for (branch_revision, subbranch_tree) in branch_tree:
                filters.append(
                    DeleteBranchTreeRCSFileFilter(
                        branch_revision, subbranch_tree
                        )
                    )
            mods.append(RCSFileModification(path, filters))
    if mods:
        try_modification_combinations(test_command, mods)

    # Try deleting tags:
    mods = []
    for path in get_files(cvsrepo, recurse=True):
        tags = list(get_tag_set(path))
        if tags:
            tags.sort()
            filters = [DeleteTagRCSFileFilter(tag) for tag in tags]
            mods.append(RCSFileModification(path, filters))

    if mods:
        try_modification_combinations(test_command, mods)


first_fail_message = """\
ERROR!  The test command failed with the original repository.  The
test command should be designed so that it succeeds (indicating that
the bug is still present) with the original repository, and fails only
after the bug disappears.  Please fix your test command and start
again.
"""


class MyHelpFormatter(optparse.IndentedHelpFormatter):
    """A HelpFormatter for optparse that doesn't reformat the description."""

    def format_description(self, description):
        return description


def main():
    parser = optparse.OptionParser(
        usage=usage, description=description,
        formatter=MyHelpFormatter(),
        )
    parser.set_defaults(skip_initial_test=False)
    parser.add_option(
        '--skip-initial-test',
        action='store_true', default=False,
        help='skip verifying that the bug exists in the original repository',
        )

    (options, args) = parser.parse_args()

    cvsrepo = args[0]

    def test_command():
        command(*args[1:])

    if not os.path.isdir(tmpdir):
        os.makedirs(tmpdir)

    if not options.skip_initial_test:
        sys.stdout.write('Testing with the original repository.\n')
        try:
            test_command()
        except CommandFailedException, e:
            sys.stderr.write(first_fail_message)
            sys.exit(1)
        sys.stdout.write(
            'The bug is confirmed to exist in the initial repository.\n'
            )

    try:
        try:
            shrink_repository(test_command, cvsrepo)
        except KeyboardInterrupt:
            pass
    finally:
        try:
            os.rmdir(tmpdir)
        except Exception, e:
            sys.stderr.write('ERROR: %s (ignored)\n' % (e,))


if __name__ == '__main__':
    main()


