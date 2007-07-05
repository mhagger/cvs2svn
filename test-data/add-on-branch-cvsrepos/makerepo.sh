#! /bin/sh

# This is the script used to create the add-on-branch CVS repository.
# (The repository is checked into svn; this script is only here for
# its documentation value.)  The script should be started from the
# main cvs2svn directory.

# The output of this script depends on the CVS version.  Newer CVS
# versions add dead revisions (b.txt:1.1.2.1 and c.txt:1.2.2.1) on the
# branch, presumably to indicate that the file didn't exist on the
# branch during the period of time between the branching point and
# when the 1.x.2.2 revisions were committed.  Older versions of CVS do
# not add these extra revisions.  The point of this test is to handle
# the new CVS behavior, so set this variable to point at a newish CVS
# executable:

cvs=$HOME/download/cvs-1.11.21/src/cvs

name=add-on-branch
repo=`pwd`/test-data/$name-cvsrepos
wc=`pwd`/cvs2svn-tmp/$name-wc
[ -e $repo/CVSROOT ] && rm -rf $repo/CVSROOT
[ -e $repo/proj ] && rm -rf $repo/proj
[ -e $wc ] && rm -rf $wc

$cvs -d $repo init
$cvs -d $repo co -d $wc .
cd $wc
mkdir proj
$cvs add proj
cd $wc/proj

echo "Create a file a.txt on trunk:"
echo '1.1' >a.txt
$cvs add a.txt
$cvs commit -m 'Adding a.txt:1.1' .

echo "Create BRANCH1 on file a.txt:"
$cvs tag -b BRANCH1

echo "Create BRANCH2 on file a.txt:"
$cvs tag -b BRANCH2

echo "Create BRANCH3 on file a.txt:"
$cvs tag -b BRANCH3



f=b.txt
b=BRANCH1

echo "Add file $f on trunk:"
$cvs up -A
echo "1.1" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.1"


echo "Add file $f on $b:"
$cvs up -r $b

# Ensure that times are distinct:
sleep 2
echo "1.1.2.2" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.1.2.2"



f=c.txt
b=BRANCH2

echo "Add file $f on trunk:"
$cvs up -A
echo "1.1" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.1"


echo "Delete file $f on trunk:"
rm $f
$cvs remove $f
$cvs commit -m "Removing $f:1.2"


echo "Add file $f on $b:"
$cvs up -r $b

# Ensure that times are distinct:
sleep 2
echo "1.2.2.2" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.2.2.2"



f=d.txt
b=BRANCH3

echo "Add file $f on trunk:"
$cvs up -A
echo "1.1" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.1"


echo "Add file $f on $b:"
$cvs up -r $b

# Ensure that times are distinct:
sleep 2
echo "1.1.2.2" >$f
$cvs add $f
$cvs commit -m "Adding $f:1.1.2.2"


echo "Modify file $f on trunk:"
$cvs up -A
echo "1.2" >$f
$cvs commit -m "Changing $f:1.2"


# Erase the unneeded stuff out of CVSROOT:
rm -rf $repo/CVSROOT
mkdir $repo/CVSROOT


