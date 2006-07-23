#!/usr/bin/env python

import os
import sys
from distutils.core import setup

assert sys.hexversion >= 0x02020000, "Install Python 2.2 or greater"

def get_version():
  "Return the version number listed in cvs2svn."
  d = {}
  execfile('cvs2svn', d)
  return d['VERSION']

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
    packages = ["cvs2svn_lib", "cvs2svn_rcsparse"],
    scripts = ["cvs2svn"]
    )
