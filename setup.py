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
    description = "CVS to Subversion/git/Bazaar/Mercurial repository converter",
    author = "The cvs2svn team",
    author_email = "dev@cvs2svn.tigris.org",
    url = "http://cvs2svn.tigris.org/",
    download_url = "http://cvs2svn.tigris.org/servlets/ProjectDocumentList?folderID=2976",
    license = "Apache-style",
    long_description = """\
cvs2svn_ is a tool for migrating a CVS repository to Subversion_, git_,
Bazaar_, or Mercurial_. The main design goals are robustness and 100% data
preservation. cvs2svn can convert just about any CVS repository we've ever
seen, including gcc, Mozilla, FreeBSD, KDE, GNOME...

.. _cvs2svn: http://cvs2svn.tigris.org/
.. _Subversion: http://svn.tigris.org/
.. _git: http://git-scm.com/
.. _Bazaar: http://bazaar-vcs.org/
.. _Mercurial: http://mercurial.selenic.com/

cvs2svn infers what happened in the history of your CVS repository and
replicates that history as accurately as possible in the target SCM. All
revisions, branches, tags, log messages, author names, and commit dates are
converted. cvs2svn deduces what CVS modifications were made at the same time,
and outputs these modifications grouped together as changesets in the target
SCM. cvs2svn also deals with many CVS quirks and is highly configurable.
See the comprehensive `feature list`_.

.. _feature list: http://cvs2svn.tigris.org/features.html
.. _documentation: http://cvs2svn.tigris.org/cvs2svn.html

Please read the documentation_ carefully before using cvs2svn.


Latest development version
--------------------------

For general use, the most recent released version of cvs2svn is usually the
best choice. However, if you want to use the newest cvs2svn features or if
you're debugging or patching cvs2svn, you might want to use the trunk version
(which is usually quite stable). To do so, use Subversion to check out a
working copy from http://cvs2svn.tigris.org/svn/cvs2svn/trunk/ using a command
like::

  svn co --username=guest --password="" http://cvs2svn.tigris.org/svn/cvs2svn/trunk cvs2svn-trunk
""",
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
    scripts = ["cvs2svn", "cvs2git", "cvs2bzr"],
    )


