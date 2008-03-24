#! /bin/sh

# Run script from the main cvs2svn directory to create the
# exclude-ntdb cvs repository.

CVSROOT=`pwd`/test-data/exclude-ntdb-cvsrepos
TMP=cvs2svn-tmp

rm -rf $TMP
mkdir $TMP

cd $TMP

#cvs -d $CVSROOT init
rm -rf $CVSROOT/proj

mkdir proj

echo 'Import proj/file.txt:'
cd proj
echo '1.1.1.1' >file.txt
cvs -d $CVSROOT import -m "First import" proj vendorbranch vendortag1
sleep 2
cd ..

echo 'Check out the repository:'
cvs -d $CVSROOT co -d wc .

echo 'Add a tag and a branch to trunk (these appear on revision 1.1.1.1)'
echo 'and commit a revision on the branch:'
cd wc/proj
cvs tag tag1
cvs tag -b branch1
cvs up -r branch1
echo 1.1.1.1.2.1 >file.txt
cvs ci -m 'Commit on branch branch1'
sleep 2
cd ../..

echo 'Import proj/file.txt a second time:'
cd proj
echo '1.1.1.2' >file.txt
cvs -d $CVSROOT import -m "Second import" proj vendorbranch vendortag2
sleep 2
cd ..

echo 'Add a second tag and branch to trunk (these appear on revision'
echo '1.1.1.2) and commit a revision on the branch:'
cd wc/proj
cvs up -A
cvs tag tag2
cvs tag -b branch2
cvs up -r branch2
echo 1.1.1.2.2.1 >file.txt
cvs ci -m 'Commit on branch branch2'
sleep 2
cd ../..

echo 'Commit directly to trunk.  This creates a revision 1.2 and'
echo 'changes the default branch back to trunk:'
cd wc/proj
cvs up -A
echo '1.2' >file.txt
cvs ci -m 'First explicit commit on trunk'
sleep 2
cd ../..

echo 'Import again.  This import is no longer on the non-trunk vendor'
echo 'branch, so it does not have any effect on trunk:'
cd proj
echo '1.1.1.3' >file.txt
cvs -d $CVSROOT import -m "Third import" proj vendorbranch vendortag3
sleep 2
cd ..

echo 'Create a tag and a branch explicitly from the vendor branch, and'
echo 'commit a revision on the branch:'
cd wc/proj
cvs up -r vendorbranch
cvs tag tag3
cvs tag -b branch3
cvs up -r branch3
echo 1.1.1.3.2.1 >file.txt
cvs ci -m 'Commit on branch branch3'
sleep 2
cd ../..

