#!/bin/sh

# Build a cvs2svn distribution.  For now, we ship cvs2svn-0.NNN.tar.gz,
# where NNN is the revision number of the working copy.

REV=`svnversion .`
DISTNAME=cvs2svn-0.${REV}

if echo ${REV} | grep -q -e '[^0-9]'; then
   echo "Packaging requires a single-revision, pristine working copy."
   echo "Run 'svn update' to get a working copy without mixed revisions."
   exit 1
fi

echo -n "Creating distribution directory ${DISTNAME}..."
rm -rf ${DISTNAME} 2>/dev/null
echo "done."

echo -n "Exporting data..."
svn export . ${DISTNAME} > /dev/null
echo "done."

rm -f ${DISTNAME}.tar.gz
tar zcf ${DISTNAME}.tar.gz ${DISTNAME}
rm -rf ${DISTNAME}

ls -l ${DISTNAME}.tar.gz
