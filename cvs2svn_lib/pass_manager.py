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

"""This module contains tools to manage the passes of a conversion."""


import time

from boolean import *
import config
from context import Ctx
from log import Log
from stats_keeper import StatsKeeper
from artifact_manager import artifact_manager


def convert(passes, start_pass, end_pass):
  """Convert a CVS repository to an SVN repository."""

  artifact_manager.register_temp_file(config.STATISTICS_FILE, convert)

  StatsKeeper().set_start_time(time.time())

  # Inform the artifact manager when artifacts are created and used:
  for the_pass in passes:
    # The statistics object is needed for every pass:
    artifact_manager.register_temp_file_needed(
        config.STATISTICS_FILE, the_pass)
    the_pass.register_artifacts()

  # Tell the artifact manager about passes that are being skipped this run:
  for the_pass in passes[0:start_pass - 1]:
    artifact_manager.pass_skipped(the_pass)

  times = [ None ] * (end_pass + 1)
  times[start_pass - 1] = time.time()
  for i in range(start_pass - 1, end_pass):
    the_pass = passes[i]
    Log().write(Log.QUIET,
                '----- pass %d (%s) -----' % (i + 1, the_pass.name,))
    the_pass.run()
    times[i + 1] = time.time()
    StatsKeeper().log_duration_for_pass(times[i + 1] - times[i], i + 1)
    # Dispose of items in Ctx() not intended to live past the end of the pass
    # (Identified by exactly one leading underscore)
    for attr in dir(Ctx()):
      if (len(attr) > 2 and attr[0] == '_' and attr[1] != '_'
          and attr[:6] != "_Ctx__"):
        delattr(Ctx(), attr)
    StatsKeeper().set_end_time(time.time())
    # Allow the artifact manager to clean up artifacts that are no
    # longer needed:
    artifact_manager.pass_done(the_pass)

  # Tell the artifact manager about passes that are being deferred:
  for the_pass in passes[end_pass:]:
    artifact_manager.pass_deferred(the_pass)

  Log().write(Log.QUIET, StatsKeeper())
  Log().write(Log.NORMAL, StatsKeeper().timings())

  # The overall conversion is done:
  artifact_manager.pass_done(convert)

  # Consistency check:
  artifact_manager.check_clean()


