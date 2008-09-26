#!/usr/bin/python

"""Remove redundant tag fixup commits from a cvs2svn-converted git repository.

Process each tag in a git repository. If the tagged commit is
tree-wise identical with another tagged commit, the tag is moved to
point at the other commit (i.e., tags pointing at identical content
will all point at a single tag fixup commit).

Furthermore, if one of the parents of the tag fixup commit is
identical to the tag fixup commit itself, then the tag is moved to the
parent.

The script is meant to be run against a repository converted by
cvs2svn, since cvs2svn creates empty commits for some tags.

"""

from subprocess import Popen, PIPE, call

# Cache trees we have already seen, and that are suitable targets for
# moved tags
tree_cache = {} # tree SHA1 -> commit SHA1

# Cache parent commit -> parent tree mapping
parent_cache = {} # commit SHA1 -> tree SHA1

def resolve_commit(commit):
    """Return the tree object associated with the given commit."""

    get_tree_cmd = ["git", "rev-parse", commit + "^{tree}"]
    tree = Popen(get_tree_cmd, stdout = PIPE).communicate()[0].strip()
    return tree

def move_tag(tag, from_commit, to_commit):
    """Move the given tag to the given commit."""

    print "Moving tag %s from %s to %s..." % (tag, from_commit, to_commit),
    retcode = call(["git", "tag", "-f", tag, to_commit])
    if retcode == 0:
        print "done"
    else:
        print "FAILED"

def try_to_move_tag(tag, commit, tree, parents):
    """Try to move the given tag to a separate commit (with identical tree)."""

    if tree in tree_cache:
        # We have already found a suitable commit for this tree
        move_tag(tag, commit, tree_cache[tree])
        return

    # Try to move this tag to one of its commit's parents
    for p in parents:
        if p not in parent_cache:
            # Not in cache
            parent_cache[p] = resolve_commit(p)
        p_tree = parent_cache[p]
        if tree == p_tree:
            # We can move tag to parent p
            move_tag(tag, commit, p)
            commit = p
            break

    # Register the resulting commit object in the tree_cache
    assert tree not in tree_cache # Sanity check
    tree_cache[tree] = commit

# Command for retrieving tags and associated metadata
# See 'git for-each-ref' manual page for --format details
get_tag_info_cmd = [
    "git",
    "for-each-ref",
    "--format=%(refname)%00%(objecttype)%00%(subject)%00"
              "%(objectname)%00%(tree)%00%(parent)%00"
              "%(*objectname)%00%(*tree)%00%(*parent)",
    "refs/tags",
]

get_tag_info = Popen(get_tag_info_cmd, stdout = PIPE)

while True: # While get_tag_info process is still running
    for line in get_tag_info.stdout:
        line = line.strip()
        (tag, objtype, subject,
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
            # We shall try to move this tag, if possible
            parent_list = []
            if parents:
                parent_list = parents.split(" ")
            for p in parent_list:
                assert len(p) == 40
            assert tag.startswith("refs/tags/")
            try_to_move_tag(tag[10:], commit, tree, parent_list)
        else:
            # We shall not move this tag, but it is a possible target
            # for other tags that we _do_ want to move
            tree_cache.setdefault(tree, commit)

    if get_tag_info.poll() is not None:
        # Break if no longer running:
        break

assert get_tag_info.returncode == 0

