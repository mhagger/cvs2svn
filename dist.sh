#!/bin/sh

# Build a cvs2svn distribution.

VERSION=1.0.0
WC_REV=`svnversion -n .`
DIST_BASE=cvs2svn-${VERSION}
DIST_FULL=${DIST_BASE}.tar.gz

if echo ${WC_REV} | grep -q -e '[^0-9]'; then
   echo "Packaging requires a single-revision, pristine working copy."
   echo ""
   echo "Run 'svn update' to get a working copy without mixed revisions,"
   echo "and make sure there are no local modifications."
   exit 1
fi

# Clean up anything that might have been left from a previous run.
rm -rf dist MANIFEST cvs2svn-${VERSION} ${DIST_FULL}

# Build the dist, Python's way.
./setup.py sdist
mv dist/${DIST_FULL} .

# Unfortunately, building the dist Python's way doesn't seem to give
# us an obvious method for including subdirs.  So, we rewire it! 
tar zxf ${DIST_FULL}
rm ${DIST_FULL}
svn export -q test-data ${DIST_BASE}/test-data
svn export -q svntest ${DIST_BASE}/svntest
svn export -q www ${DIST_BASE}/www
# Oh, and while we're at it, let's fix cvs2svn's version number.
sed -e "s/^VERSION = .*/VERSION = '${VERSION}'/" < cvs2svn > cvs2svn.tmp
mv cvs2svn.tmp ${DIST_BASE}/cvs2svn
chmod a+x ${DIST_BASE}/cvs2svn
cp cvs2svn.1 ${DIST_BASE}
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
