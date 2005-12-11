#!/bin/sh

set -ex

VIEWVC_REPOS="http://viewvc.tigris.org/svn/viewvc"

# Update the rcsparse library from ViewVC
svn export --force "$VIEWVC_REPOS/trunk/lib/vclib/ccvs/rcsparse" .

# Now update compat.py (which is not in this directory, in the upstream source)
svn export "$VIEWVC_REPOS/trunk/lib/compat.py"

