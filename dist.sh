#!/bin/sh

# Build a cvs2svn distribution.  For now, we ship cvs2svn-X.NNN.tar.gz,
# where X is the major version number, and NNN is the revision number
# of the working copy, which serves as the minor version number.

MAJOR=`head -1 .version`
MINOR=`svnversion -n .`
VN=${MAJOR}.${MINOR}
DIST_BASE=cvs2svn-${VN}
DIST_FULL=${DIST_BASE}.tar.gz

if echo ${MINOR} | grep -q -e '[^0-9]'; then
   echo "Packaging requires a single-revision, pristine working copy."
   echo ""
   echo "Run 'svn update' to get a working copy without mixed revisions,"
   echo "and make sure there are no local modifications."
   exit 1
fi

# Clean up anything that might have been left from a previous run.
rm -rf dist MANIFEST cvs2svn-${VN} ${DIST_FULL}

# Build the dist, Python's way.
./setup.py sdist
mv dist/${DIST_FULL} .

# Unfortunately, building the dist Python's way doesn't seem to give
# us an obvious method for including the svntest/ and test-data/
# subdirs.  So, we rewire it! 
tar zxf ${DIST_FULL}
rm ${DIST_FULL}
svn export -q test-data ${DIST_BASE}/test-data
svn export -q svntest ${DIST_BASE}/svntest
# Oh, and while we're at it, let's fix cvs2svn.py's version number.
sed -e "s/^VERSION = .*/VERSION = '${VN}'/" < cvs2svn.py > cvs2svn.py.tmp
mv cvs2svn.py.tmp ${DIST_BASE}/cvs2svn.py
chmod a+x ${DIST_BASE}/cvs2svn.py
tar zcf ${DIST_FULL} ${DIST_BASE}
rm -rf ${DIST_BASE}

# Clean up after this run.
rm -rf dist MANIFEST

# We're outta here.
echo ""
echo "Done:"
echo ""
ls -l ${DIST_FULL}
md5sum ${DIST_FULL}
echo ""
