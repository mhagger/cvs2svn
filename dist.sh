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

SPURIA=`svn status --no-ignore`

SAVED_IFS_1=${IFS}
IFS='
'

rm -rf ${DISTNAME}
mkdir ${DISTNAME}

cd ${DISTNAME}

# Ignore the error about copying '..' into '.'.
cp -f -a .. . 2>/dev/null

# Clean out unversioned files.
for line in ${SPURIA}; do
   if echo ${line} | grep -q -e '^Performing status on external item'; then
     /bin/true
   elif echo ${line} | grep -q -e '^X '; then
     /bin/true
   else
     junk=`echo ${line} | cut -b8-`
     rm ${junk}
   fi
done

# Clean out svn metadata.
find . -name ".svn" | xargs rm -rf

cd ..

rm -f ${DISTNAME}.tar.gz
tar zcf ${DISTNAME}.tar.gz ${DISTNAME}
rm -rf ${DISTNAME}

ls -l ${DISTNAME}.tar.gz
