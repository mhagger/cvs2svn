#!/usr/bin/python

import sys, os, os.path, string

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
    pieces = line.split(' ')
    num_tags = int(pieces[6])
    max_tags = (num_tags > max_tags) and num_tags or max_tags
    total_tags = total_tags + num_tags
    for i in range(num_tags):
      tags[pieces[6 + i + 1]] = None
    num_branches = int(pieces[6 + num_tags + 1])
    max_branches = (num_branches > max_branches) \
                   and num_branches or max_branches
    total_branches = total_branches + num_branches
    for i in range(num_branches):
      branches[pieces[6 + num_tags + 1 + i + 1]] = None

  symbols = {}
  symbols.update(tags)
  symbols.update(branches)

  num_symbols = len(symbols.keys())
  num_tags = len(tags.keys())
  num_branches = len(branches.keys())
  avg_tags = total_tags * 100.0 / line_count
  avg_branches = total_branches * 100.0 / line_count
  
  print '       Total Revisions: %d\n' \
        '     Total Unique Tags: %d\n' \
        '    Peak Revision Tags: %d\n' \
        '    Avg. Tags/Revision: %2.1f%%\n' \
        ' Total Unique Branches: %d\n' \
        'Peak Revision Branches: %d\n' \
        'Avg. Branches/Revision: %2.1f%%\n' \
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
    print 'Usage: %s /path/to/CVS/cvs2svn-data.[c-|s-|]revs' \
        % (os.path.basename(sys.argv[0]))
    print
    print 'Report information about CVS revisions, tags, and branches in a by'
    print 'CVS repository by examining the results of running pass 1 of'
    print 'cvs2svn.py on that repository.  NOTE:  You have to run the con-'
    print 'version passes yourself!'
    print
    sys.exit(0)
  do_it(sys.argv[1])
  
