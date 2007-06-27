#!/bin/sh

set -ex

VIEWVC_REPOS="http://viewvc.tigris.org/svn/viewvc"

# Update the rcsparse library from ViewVC
svn export --force "$VIEWVC_REPOS/trunk/lib/vclib/ccvs/rcsparse" .

