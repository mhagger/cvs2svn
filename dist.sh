#!/bin/sh
set -e

# Build a cvs2svn distribution.

VERSION=`python cvs2svn_lib/version.py`
echo "Building cvs2svn ${VERSION}"
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
rm -rf dist MANIFEST ${DIST_FULL}
make clean

# Build the dist, Python's way.
./setup.py sdist
mv dist/${DIST_FULL} .

# Clean up after this run.
rm -rf dist MANIFEST

# We're outta here.
echo ""
echo "Done:"
echo ""
ls -l ${DIST_FULL}
md5sum ${DIST_FULL}
echo ""
