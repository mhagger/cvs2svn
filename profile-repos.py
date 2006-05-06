#!/usr/bin/env python
# ====================================================================
# Copyright (c) 2000-2004 CollabNet.  All rights reserved.
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
repository by examining the results of running pass 1 of cvs2svn on
that repository.  NOTE: You have to run the conversion passes
yourself!
"""

import sys, os, os.path

# Fix things so we can import cvs2svn despite it not having a .py extension
import imp
imp.load_module('cvs2svn', open('cvs2svn', 'r'), 'cvs2svn',
    ('', 'r', imp.PY_SOURCE))

from cvs2svn_lib.cvs_revision import parse_cvs_revision

def do_it(revs_file):
  fp = open(revs_file, 'r')
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

    # Get a CVSRevision to describe this line
    c_rev = parse_cvs_revision(line)

    # Handle tags
    num_tags = len(c_rev.tags)
    max_tags = (num_tags > max_tags) \
               and num_tags or max_tags
    total_tags = total_tags + num_tags
    for tag in c_rev.tags:
      tags[tag] = None

    # Handle branches
    num_branches = len(c_rev.branches)
    max_branches = (num_branches > max_branches) \
                   and num_branches or max_branches
    total_branches = total_branches + num_branches
    for branch in c_rev.branches:
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
    print 'Usage: %s /path/to/cvs2svn-data.[c-|s-|]revs' \
        % (os.path.basename(sys.argv[0]))
    print __doc__
    sys.exit(0)
  do_it(sys.argv[1])
