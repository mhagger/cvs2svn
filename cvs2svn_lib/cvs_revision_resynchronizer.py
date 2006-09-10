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

"""This module contains the CVSRevisionResynchronizer class."""


from __future__ import generators

import time

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager


class CVSRevisionResynchronizer:
  def __init__(self, cvs_items_db):
    self.cvs_items_db = cvs_items_db

    self.resync = self._read_resync()

    self.output = open(
        artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DATAFILE), 'w')

  def _read_resync(self):
    """Read RESYNC_DATAFILE and return its contents.

    Return a map that maps a metadata_id to a sequence of lists which
    specify a lower and upper time bound for matching up the commit:

    { metadata_id -> [[old_time_lower, old_time_upper, new_time], ...] }

    Each triplet is a list because we will dynamically expand the
    lower/upper bound as we find commits that fall into a particular
    msg and time range.  We keep a sequence of these for each
    metadata_id because a number of checkins with the same log message
    (e.g. an empty log message) could need to be remapped.  The lists
    of triplets are sorted by old_time_lower.

    Note that we assume that we can hold the entire resync file in
    memory.  Really large repositories with wacky timestamps could
    bust this assumption.  Should that ever happen, then it is
    possible to split the resync file into pieces and make multiple
    passes, using each piece."""

    DELTA = config.COMMIT_THRESHOLD/2

    resync = { }
    for line in file(artifact_manager.get_temp_file(config.RESYNC_DATAFILE)):
      [t1, metadata_id, t2] = line.strip().split()
      t1 = int(t1, 16)
      metadata_id = int(metadata_id, 16)
      t2 = int(t2, 16)
      resync.setdefault(metadata_id, []).append([t1 - DELTA, t1 + DELTA, t2])

    # For each metadata_id, sort the resync items:
    for val in resync.values():
      val.sort()

    return resync

  def resynchronize(self, cvs_rev):
    if cvs_rev.prev_id is not None:
      prev_cvs_rev = self.cvs_items_db[cvs_rev.prev_id]
    else:
      prev_cvs_rev = None

    if cvs_rev.next_id is not None:
      next_cvs_rev = self.cvs_items_db[cvs_rev.next_id]
    else:
      next_cvs_rev = None

    # see if this is "near" any of the resync records we have recorded
    # for this metadata_id [of the log message].
    for record in self.resync.get(cvs_rev.metadata_id, []):
      if record[2] == cvs_rev.timestamp:
        # This means that either cvs_rev is the same revision that
        # caused the resync record to exist, or cvs_rev is a different
        # CVS revision that happens to have the same timestamp.  In
        # either case, we don't have to do anything, so we...
        continue

      if record[0] <= cvs_rev.timestamp <= record[1]:
        # bingo!  We probably want to remap the time on this cvs_rev,
        # unless the remapping would be useless because the new time
        # would fall outside the COMMIT_THRESHOLD window for this
        # commit group.
        new_timestamp = record[2]
        # If the new timestamp is earlier than that of our previous
        # revision
        if prev_cvs_rev and new_timestamp < prev_cvs_rev.timestamp:
          Log().warn(
              "%s: Attempt to set timestamp of revision %s on file %s"
              " to time %s, which is before previous the time of"
              " revision %s (%s):"
              % (warning_prefix, cvs_rev.rev, cvs_rev.cvs_path, new_timestamp,
                 prev_cvs_rev.rev, prev_cvs_rev.timestamp))

          # If resyncing our rev to prev_cvs_rev.timestamp + 1 will
          # place the timestamp of cvs_rev within COMMIT_THRESHOLD of
          # the attempted resync time, then sync back to
          # prev_cvs_rev.timestamp + 1...
          if ((prev_cvs_rev.timestamp + 1) - new_timestamp) \
                 < config.COMMIT_THRESHOLD:
            new_timestamp = prev_cvs_rev.timestamp + 1
            Log().warn("%s: Time set to %s"
                       % (warning_prefix, new_timestamp))
          else:
            Log().warn("%s: Timestamp left untouched" % warning_prefix)
            continue

        # If the new timestamp is later than that of our next revision
        elif next_cvs_rev and new_timestamp > next_cvs_rev.timestamp:
          Log().warn(
              "%s: Attempt to set timestamp of revision %s on file %s"
              " to time %s, which is after time of next"
              " revision %s (%s):"
              % (warning_prefix, cvs_rev.rev, cvs_rev.cvs_path, new_timestamp,
                 next_cvs_rev.rev, next_cvs_rev.timestamp))

          # If resyncing our rev to next_cvs_rev.timestamp - 1 will place
          # the timestamp of cvs_rev within COMMIT_THRESHOLD of the
          # attempted resync time, then sync forward to
          # next_cvs_rev.timestamp - 1...
          if (new_timestamp - (next_cvs_rev.timestamp - 1)) \
                 < config.COMMIT_THRESHOLD:
            new_timestamp = next_cvs_rev.timestamp - 1
            Log().warn("%s: Time set to %s"
                       % (warning_prefix, new_timestamp))
          else:
            Log().warn("%s: Timestamp left untouched" % warning_prefix)
            continue

        # Fix for Issue #71: Avoid resyncing two consecutive revisions
        # to the same timestamp.
        elif (prev_cvs_rev and new_timestamp == prev_cvs_rev.timestamp
              or next_cvs_rev and new_timestamp == next_cvs_rev.timestamp):
          continue

        # adjust the time range. we want the COMMIT_THRESHOLD from the
        # bounds of the earlier/latest commit in this group.
        record[0] = min(record[0],
                        cvs_rev.timestamp - config.COMMIT_THRESHOLD/2)
        record[1] = max(record[1],
                        cvs_rev.timestamp + config.COMMIT_THRESHOLD/2)

        msg = "PASS3 RESYNC: '%s' (%s): old time='%s' delta=%ds" \
              % (cvs_rev.cvs_path, cvs_rev.rev, time.ctime(cvs_rev.timestamp),
                 new_timestamp - cvs_rev.timestamp)
        Log().verbose(msg)

        cvs_rev.timestamp = new_timestamp

        # stop looking for hits
        break

    self.output.write(
        '%08lx %x %x\n'
        % (cvs_rev.timestamp, cvs_rev.metadata_id, cvs_rev.id,))


