# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

A StatsKeeper can pickle itself to a STATISTICS_FILE.  This module
also includes a function to read a StatsKeeper from a STATISTICS_FILE."""


import time
import cPickle
from cStringIO import StringIO

from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag


class StatsKeeper:
  def __init__(self):
    self._svn_rev_count = None
    self._first_rev_date = 1L<<32
    self._last_rev_date = 0
    self._pass_timings = { }
    self._stats_reflect_exclude = False
    self.reset_cvs_rev_info()

  def log_duration_for_pass(self, duration, pass_num, pass_name):
    self._pass_timings[pass_num] = (pass_name, duration,)

  def set_stats_reflect_exclude(self, value):
    self._stats_reflect_exclude = value

  def reset_cvs_rev_info(self):
    self._repos_file_count = 0
    self._repos_size = 0
    self._cvs_revs_count = 0
    self._cvs_branches_count = 0
    self._cvs_tags_count = 0

    # A set of tag_ids seen:
    self._tag_ids = set()

    # A set of branch_ids seen:
    self._branch_ids = set()

  def record_cvs_file(self, cvs_file):
    self._repos_file_count += 1
    self._repos_size += cvs_file.file_size

  def _record_cvs_rev(self, cvs_rev):
    self._cvs_revs_count += 1

    if cvs_rev.timestamp < self._first_rev_date:
      self._first_rev_date = cvs_rev.timestamp

    if cvs_rev.timestamp > self._last_rev_date:
      self._last_rev_date = cvs_rev.timestamp

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
    return state

  def archive(self, filename):
    f = open(filename, 'wb')
    cPickle.dump(self, f)
    f.close()

  def __str__(self):
    f = StringIO()
    f.write('\n')
    f.write('cvs2svn Statistics:\n')
    f.write('------------------\n')
    f.write('Total CVS Files:        %10i\n' % (self._repos_file_count,))
    f.write('Total CVS Revisions:    %10i\n' % (self._cvs_revs_count,))
    f.write('Total CVS Branches:     %10i\n' % (self._cvs_branches_count,))
    f.write('Total CVS Tags:         %10i\n' % (self._cvs_tags_count,))
    f.write('Total Unique Tags:      %10i\n' % (len(self._tag_ids),))
    f.write('Total Unique Branches:  %10i\n' % (len(self._branch_ids),))
    f.write('CVS Repos Size in KB:   %10i\n' % ((self._repos_size / 1024),))

    if self._svn_rev_count is not None:
      f.write('Total SVN Commits:      %10i\n' % self._svn_rev_count)

    f.write(
        'First Revision Date:    %s\n' % (time.ctime(self._first_rev_date),)
        )
    f.write(
        'Last Revision Date:     %s\n' % (time.ctime(self._last_rev_date),)
        )
    f.write('------------------')

    if not self._stats_reflect_exclude:
      f.write(
          '\n'
          '(These are unaltered CVS repository stats and do not\n'
          ' reflect tags or branches excluded via --exclude)\n'
          )

    return f.getvalue()

  @staticmethod
  def _get_timing_format(value):
    # Output times with up to 3 decimal places:
    decimals = max(0, 4 - len('%d' % int(value)))
    length = len(('%%.%df' % decimals) % value)
    return '%%%d.%df' % (length, decimals,)

  def single_pass_timing(self, pass_num):
    (pass_name, duration,) = self._pass_timings[pass_num]
    format = self._get_timing_format(duration)
    time_string = format % (duration,)
    return (
        'Time for pass%d (%s): %s seconds.'
        % (pass_num, pass_name, time_string,)
        )

  def timings(self):
    passes = self._pass_timings.keys()
    passes.sort()
    f = StringIO()
    f.write('Timings (seconds):\n')
    f.write('------------------\n')

    total = 0.0
    for pass_num in passes:
      (pass_name, duration,) = self._pass_timings[pass_num]
      total += duration

    format = self._get_timing_format(total)

    for pass_num in passes:
      (pass_name, duration,) = self._pass_timings[pass_num]
      f.write(
          (format + '   pass%-2d   %s\n') % (duration, pass_num, pass_name,)
          )

    f.write((format + '   total') % total)
    return f.getvalue()


def read_stats_keeper(filename):
  """Factory function: Return a _StatsKeeper instance.

  Read the instance from FILENAME as written by StatsKeeper.archive()."""

  f = open(filename, 'rb')
  retval = cPickle.load(f)
  f.close()
  return retval

