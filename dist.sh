#!/bin/sh
set -e

# Build a cvs2svn distribution.

VERSION=1.4.0-dev
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
rm -rf dist MANIFEST ${DIST_BASE} ${DIST_FULL} cvs2svn-dist.sh-backup

# Tweak cvs2svn to embed the proper version number.
mv cvs2svn cvs2svn-dist.sh-backup
sed -e "s/^VERSION = .*/VERSION = '${VERSION}'/" \
  < cvs2svn-dist.sh-backup > cvs2svn

# Build the dist, Python's way.
./setup.py sdist
mv dist/${DIST_FULL} .

# Clean up after this run.
mv cvs2svn-dist.sh-backup cvs2svn
rm -rf dist MANIFEST

# We're outta here.
echo ""
echo "Done:"
echo ""
ls -l ${DIST_FULL}
md5sum ${DIST_FULL}
echo ""
