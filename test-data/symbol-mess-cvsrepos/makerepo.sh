#! /bin/sh

# This is the script used to create the symbol-mess CVS repository.
# (The repository is checked into svn; this script is only here for
# its documentation value.)

# The script should be started from the main cvs2svn directory.

repo=`pwd`/test-data/symbol-mess-cvsrepos
wc=`pwd`/cvs2svn-tmp/symbol-mess-wc
[ -e $repo/CVSROOT ] && rm -rf $repo/CVSROOT
[ -e $repo/dir ] && rm -rf $repo/dir
[ -e $wc ] && rm -rf $wc

cvs -d $repo init
cvs -d $repo co -d $wc .
cd $wc
mkdir dir
cvs add dir
echo 'line1' >dir/file1
echo 'line1' >dir/file2
echo 'line1' >dir/file3
cvs add dir/file1 dir/file2 dir/file3
cvs commit -m 'Adding files on trunk' dir

cd dir

# One plain old garden-variety tag and one branch:
cvs tag TAG
cvs tag -b BRANCH

# A branch with a commit on it:
cvs tag -b BRANCH_WITH_COMMIT
cvs up -r BRANCH_WITH_COMMIT
echo 'line2' >>file1
cvs commit -m 'Commit on branch BRANCH_WITH_COMMIT' file1
cvs up -A

# Make some symbols for testing majority rule strategy:
cvs tag MOSTLY_TAG file1 file2
cvs tag -b MOSTLY_TAG file3

cvs tag -b MOSTLY_BRANCH file1 file2
cvs tag MOSTLY_BRANCH file3

# A branch that is blocked by another branch (but with no commits):
cvs tag -b BLOCKED_BY_BRANCH file1 file2 file3
cvs up -r BLOCKED_BY_BRANCH
echo 'line2' >>file1
cvs commit -m 'Establish branch BLOCKED_BY_BRANCH' file1
cvs tag -b BLOCKING_BRANCH
cvs up -A

# A branch that is blocked by another branch with a commit:
cvs tag -b BLOCKED_BY_COMMIT file1 file2 file3
cvs up -r BLOCKED_BY_COMMIT
echo 'line2' >>file1
cvs commit -m 'Establish branch BLOCKED_BY_COMMIT' file1
cvs tag -b BLOCKING_COMMIT
cvs up -r BLOCKING_COMMIT
echo 'line3' >>file1
cvs commit -m 'Committing blocking commit on BLOCKING_COMMIT' file1
cvs up -A

# A branch that is blocked by an unnamed branch with a commit:
cvs tag -b BLOCKED_BY_UNNAMED file1 file2 file3
cvs up -r BLOCKED_BY_UNNAMED
echo 'line2' >>file1
cvs commit -m 'Establish branch BLOCKED_BY_UNNAMED' file1
cvs tag -b TEMP
cvs up -r TEMP
echo 'line3' >>file1
cvs commit -m 'Committing blocking commit on TEMP' file1
cvs up -A
# Now delete the name from the blocking branch.
cvs tag -d -B TEMP

