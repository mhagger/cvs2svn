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

"""This module contains the StatsKeeper class."""


import os
import time
import cPickle

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.artifact_manager import artifact_manager


class StatsKeeper:
  def __init__(self):
    self.filename = artifact_manager.get_temp_file(config.STATISTICS_FILE)
    # This can get kinda large, so we don't store it in our data dict.
    self._repos_files = set()

    if os.path.exists(self.filename):
      self.unarchive()
    else:
      self.data = { 'cvs_revs_count' : 0,
                    'tags': set(),
                    'branches' : set(),
                    'repos_size' : 0,
                    'repos_file_count' : 0,
                    'svn_rev_count' : None,
                    'first_rev_date' : 1L<<32,
                    'last_rev_date' : 0,
                    'pass_timings' : { },
                    'start_time' : 0,
                    'end_time' : 0,
                    'stats_reflect_exclude' : False,
                    }

  def log_duration_for_pass(self, duration, pass_num):
    self.data['pass_timings'][pass_num] = duration

  def set_start_time(self, start):
    self.data['start_time'] = start

  def set_end_time(self, end):
    self.data['end_time'] = end

  def set_stats_reflect_exclude(self, value):
    self.data['stats_reflect_exclude'] = value

  def reset_c_rev_info(self):
    self.data['cvs_revs_count'] = 0
    self.data['tags'] = set()
    self.data['branches'] = set()

  def _record_cvs_file(self, cvs_file):
    # Only add the size if this is the first time we see the file.
    if cvs_file.id not in self._repos_files:
      self.data['repos_size'] += cvs_file.file_size
    self._repos_files.add(cvs_file.id)

    self.data['repos_file_count'] = len(self._repos_files)

  def record_c_rev(self, c_rev):
    self.data['cvs_revs_count'] += 1

    for tag in c_rev.tags:
      self.data['tags'].add(tag)
    for branch in c_rev.branches:
      self.data['branches'].add(branch)

    if c_rev.timestamp < self.data['first_rev_date']:
      self.data['first_rev_date'] = c_rev.timestamp

    if c_rev.timestamp > self.data['last_rev_date']:
      self.data['last_rev_date'] = c_rev.timestamp

    self._record_cvs_file(c_rev.cvs_file)

  def set_svn_rev_count(self, count):
    self.data['svn_rev_count'] = count

  def svn_rev_count(self):
    return self.data['svn_rev_count']

  def archive(self):
    open(self.filename, 'wb').write(cPickle.dumps(self.data))

  def unarchive(self):
    self.data = cPickle.loads(open(self.filename, 'rb').read())

  def __str__(self):
    svn_revs_str = ""
    if self.data['svn_rev_count'] is not None:
      svn_revs_str = ('Total SVN Commits:      %10s\n'
                      % self.data['svn_rev_count'])

    caveat_str = ''
    if not self.data['stats_reflect_exclude']:
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
            % (self.data['repos_file_count'],
               self.data['cvs_revs_count'],
               len(self.data['tags']),
               len(self.data['branches']),
               (self.data['repos_size'] / 1024),
               svn_revs_str,
               time.ctime(self.data['first_rev_date']),
               time.ctime(self.data['last_rev_date']),
               caveat_str,
               ))

  def timings(self):
    passes = self.data['pass_timings'].keys()
    passes.sort()
    output = 'Timings:\n------------------\n'

    def desc(val):
      if val == 1: return "second"
      return "seconds"

    for pass_num in passes:
      duration = int(self.data['pass_timings'][pass_num])
      p_str = ('pass %d:%6d %s\n'
               % (pass_num, duration, desc(duration)))
      output += p_str

    total = int(self.data['end_time'] - self.data['start_time'])
    output += ('total: %6d %s' % (total, desc(total)))
    return output


