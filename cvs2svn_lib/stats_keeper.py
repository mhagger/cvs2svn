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

"""This module contains the _StatsKeeper class and a factory function."""


import os
import time
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager


class _StatsKeeper:
  def __init__(self):
    self._cvs_revs_count = 0
    self._tags = set()
    self._branches = set()
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

  def log_duration_for_pass(self, duration, pass_num):
    self._pass_timings[pass_num] = duration

  def set_start_time(self, start):
    self._start_time = start

  def set_end_time(self, end):
    self._end_time = end

  def set_stats_reflect_exclude(self, value):
    self._stats_reflect_exclude = value

  def reset_c_rev_info(self):
    self._cvs_revs_count = 0
    self._tags = set()
    self._branches = set()

  def _record_cvs_file(self, cvs_file):
    # Only add the size if this is the first time we see the file.
    if cvs_file.id not in self._repos_files:
      self._repos_size += cvs_file.file_size
    self._repos_files.add(cvs_file.id)

    self._repos_file_count = len(self._repos_files)

  def record_c_rev(self, c_rev):
    self._cvs_revs_count += 1

    for tag in c_rev.tags:
      self._tags.add(tag)
    for branch in c_rev.branches:
      self._branches.add(branch)

    if c_rev.timestamp < self._first_rev_date:
      self._first_rev_date = c_rev.timestamp

    if c_rev.timestamp > self._last_rev_date:
      self._last_rev_date = c_rev.timestamp

    self._record_cvs_file(c_rev.cvs_file)

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
               len(self._tags),
               len(self._branches),
               (self._repos_size / 1024),
               svn_revs_str,
               time.ctime(self._first_rev_date),
               time.ctime(self._last_rev_date),
               caveat_str,
               ))

  def timings(self):
    passes = self._pass_timings.keys()
    passes.sort()
    output = 'Timings:\n------------------\n'

    def desc(val):
      if val == 1: return "second"
      return "seconds"

    for pass_num in passes:
      duration = int(self._pass_timings[pass_num])
      p_str = ('pass %d:%6d %s\n'
               % (pass_num, duration, desc(duration)))
      output += p_str

    total = int(self._end_time - self._start_time)
    output += ('total: %6d %s' % (total, desc(total)))
    return output


def StatsKeeper():
  """Factory function: Return a _StatsKeeper instance.

  If STATISTICS_FILE exists, read the instance from the file;
  otherwise, create and return a new instance."""

  filename = artifact_manager.get_temp_file(config.STATISTICS_FILE)
  if os.path.exists(filename):
    return cPickle.loads(open(filename, 'rb').read())
  else:
    return _StatsKeeper()


