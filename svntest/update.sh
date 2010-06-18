#!/bin/sh
set -ex
# Update the svntest library from Subversion's subversion
svn export --force http://svn.apache.org/repos/asf/subversion/trunk/subversion/tests/cmdline/svntest .
