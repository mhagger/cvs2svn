#! /bin/sh

# This is the script used to create the branch-from-empty-dir CVS
# repository.  (The repository is checked into svn; this script is
# only here for its documentation value.)
#
# The script should be started from the main cvs2svn directory.
#
# The repository itself tickles a problem that I was having with an
# uncommitted version of better-symbol-selection when BRANCH2 is
# grafted onto BRANCH1.

name=branch-from-empty-dir
repo=`pwd`/test-data/$name-cvsrepos
wc=`pwd`/cvs2svn-tmp/$name-wc
[ -e $repo/CVSROOT ] && rm -rf $repo/CVSROOT
[ -e $repo/proj ] && rm -rf $repo/proj
[ -e $wc ] && rm -rf $wc

cvs -d $repo init
cvs -d $repo co -d $wc .
cd $wc
mkdir proj
cvs add proj
cd proj
mkdir subdir
cvs add subdir
echo '1.1' >subdir/b.txt
cvs add subdir/b.txt
cvs commit -m 'Adding subdir/b.txt:1.1' .


rm subdir/b.txt
cvs rm subdir/b.txt
cvs commit -m 'Removing subdir/b.txt' .


cvs rtag -r 1.2 -b BRANCH1 proj/subdir/b.txt
cvs rtag -r 1.2 -b BRANCH2 proj/subdir/b.txt


echo '1.1' >a.txt
cvs add a.txt
cvs commit -m 'Adding a.txt:1.1' .

cvs tag -b BRANCH1 a.txt
cvs update -r BRANCH1

echo '1.1.2.1' >a.txt
cvs commit -m 'Committing a.txt:1.1.2.1' a.txt

cvs tag -b BRANCH2 a.txt

