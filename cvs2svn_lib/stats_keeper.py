# (Be in -*- python -*- mode.)
#
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

"""This module contains the StatsKeeper class.

A StatsKeeper can pickle itself to STATISTICS_FILE.  This module also
includes a function to read a StatsKeeper from STATISTICS_FILE."""


import time
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag


class StatsKeeper:
  def __init__(self):
    self._cvs_revs_count = 0
    self._cvs_branches_count = 0
    self._cvs_tags_count = 0
    # A set of tag_ids seen:
    self._tag_ids = set()
    # A set of branch_ids seen:
    self._branch_ids = set()
    self._repos_size = 0
    self._repos_file_count = 0
    self._svn_rev_count = None
    self._first_rev_date = 1L<<32
    self._last_rev_date = 0
    self._pass_timings = { }
    self._start_time = 0
    self._end_time = 0
    self._stats_reflect_exclude = False
    self._repos_files = set()

  def log_duration_for_pass(self, duration, pass_num, pass_name):
    self._pass_timings[pass_num] = (pass_name, duration,)

  def set_start_time(self, start):
    self._start_time = start

  def set_end_time(self, end):
    self._end_time = end

  def set_stats_reflect_exclude(self, value):
    self._stats_reflect_exclude = value

  def reset_cvs_rev_info(self):
    self._cvs_revs_count = 0
    self._cvs_branches_count = 0
    self._cvs_tags_count = 0
    self._tag_ids = set()
    self._branch_ids = set()

  def _record_cvs_file(self, cvs_file):
    # Only add the size if this is the first time we see the file.
    if cvs_file.id not in self._repos_files:
      self._repos_size += cvs_file.file_size
    self._repos_files.add(cvs_file.id)

    self._repos_file_count = len(self._repos_files)

  def _record_cvs_rev(self, cvs_rev):
    self._cvs_revs_count += 1

    if cvs_rev.timestamp < self._first_rev_date:
      self._first_rev_date = cvs_rev.timestamp

    if cvs_rev.timestamp > self._last_rev_date:
      self._last_rev_date = cvs_rev.timestamp

    self._record_cvs_file(cvs_rev.cvs_file)

  def _record_cvs_branch(self, cvs_branch):
    self._cvs_branches_count += 1
    self._branch_ids.add(cvs_branch.symbol.id)

  def _record_cvs_tag(self, cvs_tag):
    self._cvs_tags_count += 1
    self._tag_ids.add(cvs_tag.symbol.id)

  def record_cvs_item(self, cvs_item):
    if isinstance(cvs_item, CVSRevision):
      self._record_cvs_rev(cvs_item)
    elif isinstance(cvs_item, CVSBranch):
      self._record_cvs_branch(cvs_item)
    elif isinstance(cvs_item, CVSTag):
      self._record_cvs_tag(cvs_item)
    else:
      raise RuntimeError('Unknown CVSItem type')

  def set_svn_rev_count(self, count):
    self._svn_rev_count = count

  def svn_rev_count(self):
    return self._svn_rev_count

  def __getstate__(self):
    state = self.__dict__.copy()
    # This can get kinda large, so we don't store it:
    state['_repos_files'] = set()
    return state

  def archive(self):
    filename = artifact_manager.get_temp_file(config.STATISTICS_FILE)
    open(filename, 'wb').write(cPickle.dumps(self))

  def __str__(self):
    svn_revs_str = ""
    if self._svn_rev_count is not None:
      svn_revs_str = ('Total SVN Commits:      %10s\n'
                      % self._svn_rev_count)

    caveat_str = ''
    if not self._stats_reflect_exclude:
      caveat_str = (
          '\n'
          '(These are unaltered CVS repository stats and do not\n'
          ' reflect tags or branches excluded via --exclude)\n')
    return ('\n'                                \
            'cvs2svn Statistics:\n'             \
            '------------------\n'              \
            'Total CVS Files:        %10i\n'    \
            'Total CVS Revisions:    %10i\n'    \
            'Total CVS Branches:     %10i\n'    \
            'Total CVS Tags:         %10i\n'    \
            'Total Unique Tags:      %10i\n'    \
            'Total Unique Branches:  %10i\n'    \
            'CVS Repos Size in KB:   %10i\n'    \
            '%s'                                \
            'First Revision Date:    %s\n'      \
            'Last Revision Date:     %s\n'      \
            '------------------'                \
            '%s'
            % (self._repos_file_count,
               self._cvs_revs_count,
               self._cvs_branches_count,
               self._cvs_tags_count,
               len(self._tag_ids),
               len(self._branch_ids),
               (self._repos_size / 1024),
               svn_revs_str,
               time.ctime(self._first_rev_date),
               time.ctime(self._last_rev_date),
               caveat_str,
               ))

  def timings(self):
    passes = self._pass_timings.keys()
    passes.sort()
    output = 'Timings (seconds):\n------------------\n'

    total = self._end_time - self._start_time

    # Output times with up to 3 decimal places:
    decimals = max(0, 4 - len('%d' % int(total)))
    length = len(('%%.%df' % decimals) % total)
    format = '%%%d.%df' % (length, decimals,)

    for pass_num in passes:
      (pass_name, duration,) = self._pass_timings[pass_num]
      p_str = ((format + '   pass%-2d   %s\n')
               % (duration, pass_num, pass_name,))
      output += p_str

    output += ((format + '   total') % total)
    return output


def read_stats_keeper():
  """Factory function: Return a _StatsKeeper instance.

  If STATISTICS_FILE exists, read the instance from the file;
  otherwise, create and return a new instance."""

  filename = artifact_manager.get_temp_file(config.STATISTICS_FILE)
  return cPickle.loads(open(filename, 'rb').read())


