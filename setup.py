#!/usr/bin/env python

import os
import sys
from distutils.core import setup

assert sys.version >= '2', "Install Python 2.0 or greater"

### This duplicates logic already found in dist.sh.  We could change
### dist.sh to pass the revnum in, but setup.py already parses a
### standard set of arguments thanks to distutils.core, and it might
### get messy if we interfered with that.
def get_version():
  "Return a distribution version number based on this working copy."
  major = open('.version').readline().strip()
  p = os.popen('svnversion -n .')
  minor = ''
  while 1:
    new_data = p.read()
    if new_data:
      minor = minor + new_data
    else:
      break
  return major + "." + minor

setup(
    # Metadata.
    name = "cvs2svn",
    version = get_version(),
    description = "CVS-to-Subversion repository converter",
    author = "The cvs2svn Team",
    author_email = "<dev@cvs2svn.tigris.org>",
    url = "http://cvs2svn.tigris.org/",
    license = "Apache-style",
    # Data.
    packages = ["cvs2svn_rcsparse"],
    scripts = ["cvs2svn.py"]
    )
