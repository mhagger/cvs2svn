#! /bin/sh

# This is the script used to create the branch-from-deleted-1-1 CVS
# repository.  (The repository is checked into svn; this script is
# only here for its documentation value.)
#
# The script should be started from the main cvs2svn directory.

name=branch-from-deleted-1-1
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

echo "Create a file a.txt on trunk:"
echo '1.1' >a.txt
cvs add a.txt
cvs commit -m 'Adding a.txt:1.1' .

echo "Create two branches on file a.txt:"
cvs tag -b BRANCH1
cvs tag -b BRANCH2


echo "Add file b.txt on BRANCH1:"
cvs up -r BRANCH1

echo '1.1.2.1' >b.txt
cvs add b.txt
cvs commit -m 'Adding b.txt:1.1.2.1'


echo "Add file b.txt on BRANCH2:"
cvs up -r BRANCH2

echo '1.1.4.1' >b.txt
cvs add b.txt
cvs commit -m 'Adding b.txt:1.1.4.1'


echo "Add file b.txt on trunk:"
cvs up -A
echo '1.2' >b.txt
cvs add b.txt
cvs commit -m 'Adding b.txt:1.2'



echo "Add file c.txt on BRANCH1:"
cvs up -r BRANCH1

echo '1.1.2.1' >c.txt
cvs add c.txt
cvs commit -m 'Adding c.txt:1.1.2.1'


echo "Add file c.txt on BRANCH2:"
cvs up -r BRANCH2

echo '1.1.4.1' >c.txt
cvs add c.txt
cvs commit -m 'Adding c.txt:1.1.4.1'



echo "Create branch BRANCH3 from 1.1 versions of b.txt and c.txt:"
cvs rtag -r 1.1 -b BRANCH3 proj/b.txt proj/c.txt

echo "Create tag TAG1 from 1.1 versions of b.txt and c.txt:"
cvs rtag -r 1.1 TAG1 proj/b.txt proj/c.txt


