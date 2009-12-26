#!/usr/bin/env python
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at http://cvs2svn.tigris.org/.
# ====================================================================


"""
Report information about CVS revisions, tags, and branches in a CVS
repository by examining the temporary files output by pass 1 of cvs2svn
on that repository.  NOTE: You have to run the conversion pass yourself!
"""

import sys, os, os.path

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.config import CVS_PATHS_DB
from cvs2svn_lib.config import CVS_ITEMS_DB
from cvs2svn_lib.config import CVS_ITEMS_ALL_DATAFILE
from cvs2svn_lib.cvs_path_database import CVSPathDatabase
from cvs2svn_lib.cvs_item_database import CVSItemDatabase

def do_it():
  cvs_path_db = CVSPathDatabase(CVS_PATHS_DB, DB_OPEN_READ)
  cvs_items_db = CVSItemDatabase(cvs_path_db, CVS_ITEMS_DB, DB_OPEN_READ)
  fp = open(CVS_ITEMS_ALL_DATAFILE, 'r')

  tags = { }
  branches = { }

  max_tags = 0
  max_branches = 0
  line_count = 0
  total_tags = 0
  total_branches = 0

  while 1:
    line_count = line_count + 1
    line = fp.readline()
    if not line:
      break

    cvs_rev_key = line.strip()
    cvs_rev = cvs_items_db[cvs_rev_key]

    # Handle tags
    num_tags = len(cvs_rev.tags)
    max_tags = (num_tags > max_tags) \
               and num_tags or max_tags
    total_tags = total_tags + num_tags
    for tag in cvs_rev.tags:
      tags[tag] = None

    # Handle branches
    num_branches = len(cvs_rev.branches)
    max_branches = (num_branches > max_branches) \
                   and num_branches or max_branches
    total_branches = total_branches + num_branches
    for branch in cvs_rev.branches:
      branches[branch] = None

  symbols = {}
  symbols.update(tags)
  symbols.update(branches)

  num_symbols = len(symbols.keys())
  num_tags = len(tags.keys())
  num_branches = len(branches.keys())
  avg_tags = total_tags * 1.0 / line_count
  avg_branches = total_branches * 1.0 / line_count

  print '   Total CVS Revisions: %d\n' \
        '     Total Unique Tags: %d\n' \
        '    Peak Revision Tags: %d\n' \
        '    Avg. Tags/Revision: %2.1f\n' \
        ' Total Unique Branches: %d\n' \
        'Peak Revision Branches: %d\n' \
        'Avg. Branches/Revision: %2.1f\n' \
        '  Total Unique Symbols: %d%s\n' \
        % (line_count,
           num_tags,
           max_tags,
           avg_tags,
           num_branches,
           max_branches,
           avg_branches,
           num_symbols,
           num_symbols == num_tags + num_branches and ' ' or ' (!)',
           )


if __name__ == "__main__":
  argc = len(sys.argv)
  if argc < 2:
    print 'Usage: %s /path/to/cvs2svn-temporary-directory' \
        % (os.path.basename(sys.argv[0]))
    print __doc__
    sys.exit(0)
  os.chdir(sys.argv[1])
  do_it()
