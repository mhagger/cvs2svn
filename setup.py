#!/usr/bin/env python

import sys
from distutils.core import setup

assert 0x02040000 <= sys.hexversion < 0x03000000, \
       "Install Python 2, version 2.4 or greater"


def get_version():
  "Return the version number of cvs2svn."

  from cvs2svn_lib.version import VERSION
  return VERSION


setup(
    # Metadata.
    name = "cvs2svn",
    version = get_version(),
    description = "CVS to Subversion or git repository converter",
    author = "The cvs2svn team",
    author_email = "<dev@cvs2svn.tigris.org>",
    url = "http://cvs2svn.tigris.org/",
    license = "Apache-style",
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Software Development :: Version Control',
        'Topic :: Software Development :: Version Control :: CVS',
        'Topic :: Utilities',
        ],
    # Data.
    packages = ["cvs2svn_lib", "cvs2svn_rcsparse"],
    scripts = ["cvs2svn", "cvs2git"],
    )


