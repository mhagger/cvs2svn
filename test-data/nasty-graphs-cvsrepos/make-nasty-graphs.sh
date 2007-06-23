#! /bin/sh

# This script can be moved to the test-data directory and executed
# there to recreate nasty-graphs-cvsrepos.  (Well, approximately.  It
# doesn't clean up CVSROOT or add CVSROOT/README.)

CVSROOT=`pwd`/nasty-graphs-cvsrepos
export CVSROOT
rm -rf $CVSROOT

WC=`pwd`/cvs2svn-tmp
rm -rf $WC

cvs init

cvs co -d $WC .


# +-> A -> B --+
# |            |
# +------------+
#
# A: a.txt<1.1> b.txt<1.2>
# B: a.txt<1.2> b.txt<1.1>

TEST=AB-loop
D=$WC/$TEST

mkdir $D
cvs add $D

echo "1.1" >$D/a.txt
cvs add $D/a.txt
cvs commit -m "$TEST-A" $D/a.txt

echo "1.2" >$D/a.txt
cvs commit -m "$TEST-B" $D/a.txt

echo "1.1" >$D/b.txt
cvs add $D/b.txt
cvs commit -m "$TEST-B" $D/b.txt

echo "1.2" >$D/b.txt
cvs commit -m "$TEST-A" $D/b.txt


# +-> A -> B -> C --+
# |                 |
# +-----------------+
#
# A: a.txt<1.1>            c.txt<1.2>
# B: a.txt<1.2> b.txt<1.1>
# C:            b.txt<1.2> c.txt<1.1>

TEST=ABC-loop
D=$WC/$TEST

mkdir $D
cvs add $D

echo "1.1" >$D/a.txt
cvs add $D/a.txt
cvs commit -m "$TEST-A" $D/a.txt

echo "1.2" >$D/a.txt
cvs commit -m "$TEST-B" $D/a.txt

echo "1.1" >$D/b.txt
cvs add $D/b.txt
cvs commit -m "$TEST-B" $D/b.txt

echo "1.2" >$D/b.txt
cvs commit -m "$TEST-C" $D/b.txt

echo "1.1" >$D/c.txt
cvs add $D/c.txt
cvs commit -m "$TEST-C" $D/c.txt

echo "1.2" >$D/c.txt
cvs commit -m "$TEST-A" $D/c.txt


# A: a.txt<1.1> b.txt<1.3> c.txt<1.2>
# B: a.txt<1.2> b.txt<1.1> c.txt<1.3>
# C: a.txt<1.3> b.txt<1.2> c.txt<1.1>

TEST=ABC-passthru-loop
D=$WC/$TEST

mkdir $D
cvs add $D

echo "1.1" >$D/a.txt
cvs add $D/a.txt
cvs commit -m "$TEST-A" $D/a.txt

echo "1.2" >$D/a.txt
cvs commit -m "$TEST-B" $D/a.txt

echo "1.3" >$D/a.txt
cvs commit -m "$TEST-C" $D/a.txt

echo "1.1" >$D/b.txt
cvs add $D/b.txt
cvs commit -m "$TEST-B" $D/b.txt

echo "1.2" >$D/b.txt
cvs commit -m "$TEST-C" $D/b.txt

echo "1.3" >$D/b.txt
cvs commit -m "$TEST-A" $D/b.txt

echo "1.1" >$D/c.txt
cvs add $D/c.txt
cvs commit -m "$TEST-C" $D/c.txt

echo "1.2" >$D/c.txt
cvs commit -m "$TEST-A" $D/c.txt

echo "1.3" >$D/c.txt
cvs commit -m "$TEST-B" $D/c.txt


# A: a.txt<1.1>            c.txt<1.3> d.txt<1.2>
# B: a.txt<1.2> b.txt<1.1>            d.txt<1.3>
# C: a.txt<1.3> b.txt<1.2> c.txt<1.1>
# D:            b.txt<1.3> c.txt<1.2> d.txt<1.1>

TEST=ABCD-passthru-loop
D=$WC/$TEST

mkdir $D
cvs add $D

echo "1.1" >$D/a.txt
cvs add $D/a.txt
cvs commit -m "$TEST-A" $D/a.txt

echo "1.2" >$D/a.txt
cvs commit -m "$TEST-B" $D/a.txt

echo "1.3" >$D/a.txt
cvs commit -m "$TEST-C" $D/a.txt

echo "1.1" >$D/b.txt
cvs add $D/b.txt
cvs commit -m "$TEST-B" $D/b.txt

echo "1.2" >$D/b.txt
cvs commit -m "$TEST-C" $D/b.txt

echo "1.3" >$D/b.txt
cvs commit -m "$TEST-D" $D/b.txt

echo "1.1" >$D/c.txt
cvs add $D/c.txt
cvs commit -m "$TEST-C" $D/c.txt

echo "1.2" >$D/c.txt
cvs commit -m "$TEST-D" $D/c.txt

echo "1.3" >$D/c.txt
cvs commit -m "$TEST-A" $D/c.txt

echo "1.1" >$D/d.txt
cvs add $D/d.txt
cvs commit -m "$TEST-D" $D/d.txt

echo "1.2" >$D/d.txt
cvs commit -m "$TEST-A" $D/d.txt

echo "1.3" >$D/d.txt
cvs commit -m "$TEST-B" $D/d.txt


# The following test has the nasty property that each changeset has
# either one LINK_PREV or LINK_SUCC and also one LINK_PASSTHRU.
#
# A: a.txt<1.1> b.txt<1.3>
# B: a.txt<1.2> b.txt<1.4>
# C: a.txt<1.3> b.txt<1.1>
# D: a.txt<1.4> b.txt<1.2>

TEST=AB-double-passthru-loop
D=$WC/$TEST

mkdir $D
cvs add $D

echo "1.1" >$D/a.txt
cvs add $D/a.txt
cvs commit -m "$TEST-A" $D/a.txt

echo "1.2" >$D/a.txt
cvs commit -m "$TEST-B" $D/a.txt

echo "1.3" >$D/a.txt
cvs commit -m "$TEST-C" $D/a.txt

echo "1.4" >$D/a.txt
cvs commit -m "$TEST-D" $D/a.txt

echo "1.1" >$D/b.txt
cvs add $D/b.txt
cvs commit -m "$TEST-C" $D/b.txt

echo "1.2" >$D/b.txt
cvs commit -m "$TEST-D" $D/b.txt

echo "1.3" >$D/b.txt
cvs commit -m "$TEST-A" $D/b.txt

echo "1.4" >$D/b.txt
cvs commit -m "$TEST-B" $D/b.txt


