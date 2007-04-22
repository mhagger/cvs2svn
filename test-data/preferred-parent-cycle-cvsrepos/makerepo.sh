#! /bin/sh

# This is the script used to create the preferred-parent-cycle CVS
# repository.  (The repository is checked into svn; this script is
# only here for its documentation value.)
#
# The script should be started from the main cvs2svn directory.
#
# The branching structure of the three files in this repository is
# constructed to create a loop in the preferred parent of each branch
# A, B, and C.  The branches are as follows ('*' marks revisions,
# which are used to disambiguate the parentage of each branch within a
# single file):
#
# file1:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch A
#            |
#            +--*--+-------- branch B
#                  |
#                  +-------- branch C
#
# file2:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch B
#            |
#            +--*--+-------- branch C
#                  |
#                  +-------- branch A
#
# file3:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch C
#            |
#            +--*--+-------- branch A
#                  |
#                  +-------- branch B
#
# Note that the possible parents of A are (trunk, C, C), those of B
# are (A, trunk, A), and those of C are (B, B, trunk).  Therefore the
# preferred parents form a cycle A -> C -> B -> A.

repo=`pwd`/test-data/preferred-parent-cycle-cvsrepos
wc=`pwd`/tmp/preferred-parent-cycle-wc
[ -e $repo/CVSROOT ] && rm -rf $repo/CVSROOT
[ -e $repo/dir ] && rm -rf $repo/dir
[ -e $wc ] && rm -rf $wc

cvs -d $repo init
cvs -d $repo co -d $wc .
cd $wc
mkdir dir
cvs add dir
cd dir
echo '1.1' >file1
echo '1.1' >file2
echo '1.1' >file3
cvs add file1 file2 file3
cvs commit -m 'Adding files on trunk' .


cvs tag -b A file1
cvs up -r A file1

cvs tag -b B file2
cvs up -r B file2

cvs tag -b C file3
cvs up -r C file3

echo '1.1.2.1' >file1
echo '1.1.2.1' >file2
echo '1.1.2.1' >file3
cvs commit -m 'Adding revision on first-level branch' .


cvs tag -b B file1
cvs up -r B file1

cvs tag -b C file2
cvs up -r C file2

cvs tag -b A file3
cvs up -r A file3

echo '1.1.2.1.2.1' >file1
echo '1.1.2.1.2.1' >file2
echo '1.1.2.1.2.1' >file3
cvs commit -m 'Adding revision on second-level branch' .


cvs tag -b C file1
cvs up -r C file1

cvs tag -b A file2
cvs up -r A file2

cvs tag -b B file3
cvs up -r B file3

