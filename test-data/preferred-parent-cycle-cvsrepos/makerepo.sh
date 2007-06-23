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
# which are used to prevent trunk from being a possible parent of
# branches A, B, or C):
#
# file1:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch X
#            |
#            +-------------- branch A
#            |
#            +-------------- branch B
#            |
#            +-------------- branch C
#
# file2:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch Y
#            |
#            +-------------- branch B
#            |
#            +-------------- branch C
#            |
#            +-------------- branch A
#
# file3:
# --*--+-------------------- trunk
#      |
#      +--*--+-------------- branch Z
#            |
#            +-------------- branch C
#            |
#            +-------------- branch A
#            |
#            +-------------- branch B
#

# Note that the possible parents of A are (X, Y, Z, C*2, B*1), those
# of B are (X, Y, Z, A*2, C*1), and those of C are (X, Y, Z, B*2,
# A*1).  Therefore the preferred parents form a cycle A -> C -> B ->
# A.

repo=`pwd`/test-data/preferred-parent-cycle-cvsrepos
wc=`pwd`/cvs2svn-tmp/preferred-parent-cycle-wc
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


cvs tag -b X file1
cvs up -r X file1

cvs tag -b Y file2
cvs up -r Y file2

cvs tag -b Z file3
cvs up -r Z file3

echo '1.1.2.1' >file1
echo '1.1.2.1' >file2
echo '1.1.2.1' >file3
cvs commit -m 'Adding revision on first-level branches' .


cvs tag -b A file1
cvs up -r A file1

cvs tag -b B file1
cvs up -r B file1

cvs tag -b C file1
cvs up -r C file1


cvs tag -b B file2
cvs up -r B file2

cvs tag -b C file2
cvs up -r C file2

cvs tag -b A file2
cvs up -r A file2


cvs tag -b C file3
cvs up -r C file3

cvs tag -b A file3
cvs up -r A file3

cvs tag -b B file3
cvs up -r B file3

