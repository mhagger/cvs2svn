#!/usr/bin/python

"""Remove redundant fixup commits from a cvs2svn-converted git repository.

Process each head ref and/or tag in a git repository. If the
associated commit is tree-wise identical with another commit, the head
or tag is moved to point at the other commit (i.e., refs pointing at
identical content will all point at a single fixup commit).

Furthermore, if one of the parents of the fixup commit is identical to
the fixup commit itself, then the head or tag is moved to the parent.

The script is meant to be run against a repository converted by
cvs2svn, since cvs2svn creates empty commits for some tags and head
refs (branches).

"""

usage = 'USAGE: %prog [options]'

import sys
import optparse
from subprocess import Popen, PIPE, call


# Cache trees we have already seen, and that are suitable targets for
# moved refs
tree_cache = {} # tree SHA1 -> commit SHA1

# Cache parent commit -> parent tree mapping
parent_cache = {} # commit SHA1 -> tree SHA1


def resolve_commit(commit):
    """Return the tree object associated with the given commit."""

    get_tree_cmd = ["git", "rev-parse", commit + "^{tree}"]
    tree = Popen(get_tree_cmd, stdout = PIPE).communicate()[0].strip()
    return tree


def move_ref(ref, from_commit, to_commit, ref_type):
    """Move the given head to the given commit.
    ref_type is either "tags" or "heads"
    """
    if from_commit != to_commit:
        print "Moving ref %s from %s to %s..." % (ref, from_commit, to_commit),
        if ref_type == "tags":
            command = "tag"
        else:
            command = "branch"
        retcode = call(["git", command, "-f", ref, to_commit])
        if retcode == 0:
            print "done"
        else:
            print "FAILED"


def try_to_move_ref(ref, commit, tree, parents, ref_type):
    """Try to move the given ref to a separate commit (with identical tree)."""

    if tree in tree_cache:
        # We have already found a suitable commit for this tree
        move_ref(ref, commit, tree_cache[tree], ref_type)
        return

    # Try to move this ref to one of its commit's parents
    for p in parents:
        if p not in parent_cache:
            # Not in cache
            parent_cache[p] = resolve_commit(p)
        p_tree = parent_cache[p]
        if tree == p_tree:
            # We can move ref to parent p
            move_ref(ref, commit, p, ref_type)
            commit = p
            break

    # Register the resulting commit object in the tree_cache
    assert tree not in tree_cache # Sanity check
    tree_cache[tree] = commit


def process_refs(ref_type):
    tree_cache.clear()
    parent_cache.clear()

    # Command for retrieving refs and associated metadata
    # See 'git for-each-ref' manual page for --format details
    get_ref_info_cmd = [
        "git",
        "for-each-ref",
        "--format=%(refname)%00%(objecttype)%00%(subject)%00"
                  "%(objectname)%00%(tree)%00%(parent)%00"
                  "%(*objectname)%00%(*tree)%00%(*parent)",
        "refs/%s" % (ref_type,),
    ]

    get_ref_info = Popen(get_ref_info_cmd, stdout = PIPE)

    while True: # While get_ref_info process is still running
        for line in get_ref_info.stdout:
            line = line.strip()
            (ref, objtype, subject,
             commit, tree, parents,
             commit_alt, tree_alt, parents_alt) = line.split(chr(0))
            if objtype == "tag":
                commit = commit_alt
                tree = tree_alt
                parents = parents_alt
            elif objtype != "commit":
                continue

            if subject.startswith("This commit was manufactured by cvs2svn") \
                   or not subject:
                # We shall try to move this ref, if possible
                parent_list = []
                if parents:
                    parent_list = parents.split(" ")
                for p in parent_list:
                    assert len(p) == 40
                ref_prefix = "refs/%s/" % (ref_type,)
                assert ref.startswith(ref_prefix)
                try_to_move_ref(
                    ref[len(ref_prefix):], commit, tree, parent_list, ref_type
                    )
            else:
                # We shall not move this ref, but it is a possible target
                # for other refs that we _do_ want to move
                tree_cache.setdefault(tree, commit)

        if get_ref_info.poll() is not None:
            # Break if no longer running:
            break

    assert get_ref_info.returncode == 0


def main(args):
    parser = optparse.OptionParser(usage=usage, description=__doc__)
    parser.add_option(
        '--tags', '-t',
        action='store_true', default=False,
        help='process tags',
        )
    parser.add_option(
        '--branches', '-b',
        action='store_true', default=False,
        help='process branches',
        )

    (options, args) = parser.parse_args(args=args)

    if args:
        parser.error('Unexpected command-line arguments')

    if not (options.tags or options.branches):
        # By default, process tags but not branches:
        options.tags = True

    if options.tags:
        process_refs("tags")

    if options.branches:
        process_refs("heads")


main(sys.argv[1:])


