# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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
import gc

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.stats_keeper import StatsKeeper
from cvs2svn_lib.stats_keeper import read_stats_keeper
from cvs2svn_lib.artifact_manager import artifact_manager


class InvalidPassError(FatalError):
  def __init__(self, msg):
    FatalError.__init__(
        self, msg + '\nUse --help-passes for more information.')


def check_for_garbage():
  # We've turned off the garbage collector because we shouldn't
  # need it (we don't create circular dependencies) and because it
  # is therefore a waste of time.  So here we check for any
  # unreachable objects and generate a debug-level warning if any
  # occur:
  gc.set_debug(gc.DEBUG_SAVEALL)
  gc_count = gc.collect()
  if gc_count:
    if Log().is_on(Log.DEBUG):
      Log().debug(
          'INTERNAL: %d unreachable object(s) were garbage collected:'
          % (gc_count,)
          )
      for g in gc.garbage:
        Log().debug('    %s' % (g,))
    del gc.garbage[:]


class Pass(object):
  """Base class for one step of the conversion."""

  def __init__(self):
    # By default, use the pass object's class name as the pass name:
    self.name = self.__class__.__name__

  def register_artifacts(self):
    """Register artifacts (created and needed) in artifact_manager."""

    raise NotImplementedError

  def _register_temp_file(self, basename):
    """Helper method; for brevity only."""

    artifact_manager.register_temp_file(basename, self)

  def _register_temp_file_needed(self, basename):
    """Helper method; for brevity only."""

    artifact_manager.register_temp_file_needed(basename, self)

  def run(self, run_options, stats_keeper):
    """Carry out this step of the conversion.

    RUN_OPTIONS is an instance of RunOptions.  STATS_KEEPER is an
    instance of StatsKeeper."""

    raise NotImplementedError


class PassManager:
  """Manage a list of passes that can be executed separately or all at once.

  Passes are numbered starting with 1."""

  def __init__(self, passes):
    """Construct a PassManager with the specified PASSES.

    Internally, passes are numbered starting with 1.  So PASSES[0] is
    considered to be pass number 1."""

    self.passes = passes
    self.num_passes = len(self.passes)

  def get_pass_number(self, pass_name, default=None):
    """Return the number of the pass indicated by PASS_NAME.

    PASS_NAME should be a string containing the name or number of a
    pass.  If a number, it should be in the range 1 <= value <=
    self.num_passes.  Return an integer in the same range.  If
    PASS_NAME is the empty string and DEFAULT is specified, return
    DEFAULT.  Raise InvalidPassError if PASS_NAME cannot be converted
    into a valid pass number."""

    if not pass_name and default is not None:
      assert 1 <= default <= self.num_passes
      return default

    try:
      # Does pass_name look like an integer?
      pass_number = int(pass_name)
      if not 1 <= pass_number <= self.num_passes:
        raise InvalidPassError(
            'illegal value (%d) for pass number.  Must be 1 through %d or\n'
            'the name of a known pass.'
            % (pass_number,self.num_passes,))
      return pass_number
    except ValueError:
      # Is pass_name the name of one of the passes?
      for i in range(len(self.passes)):
        if self.passes[i].name == pass_name:
          return i + 1
      raise InvalidPassError('Unknown pass name (%r).' % (pass_name,))

  def run(self, run_options):
    """Run the specified passes, one after another.

    START_PASS is the number of the first pass that should be run.
    END_PASS is the number of the last pass that should be run.  It
    must be that 1 <= START_PASS <= END_PASS <= self.num_passes."""

    # Convert start_pass and end_pass into the indices of the passes
    # to execute, using the Python index range convention (i.e., first
    # pass executed and first pass *after* the ones that should be
    # executed).
    index_start = run_options.start_pass - 1
    index_end = run_options.end_pass

    artifact_manager.register_temp_file(config.STATISTICS_FILE, self)

    # Inform the artifact manager when artifacts are created and used:
    for the_pass in self.passes:
      the_pass.register_artifacts()

    # Consider self to be running during the whole conversion, to keep
    # STATISTICS_FILE alive:
    artifact_manager.pass_started(self)

    if index_start == 0:
      stats_keeper = StatsKeeper()
    else:
      stats_keeper = read_stats_keeper()

    stats_keeper.set_start_time(time.time())

    # Tell the artifact manager about passes that are being skipped this run:
    for the_pass in self.passes[0:index_start]:
      artifact_manager.pass_skipped(the_pass)

    start_time = time.time()
    for i in range(index_start, index_end):
      the_pass = self.passes[i]
      Log().quiet('----- pass %d (%s) -----' % (i + 1, the_pass.name,))
      artifact_manager.pass_started(the_pass)
      the_pass.run(run_options, stats_keeper)
      end_time = time.time()
      stats_keeper.log_duration_for_pass(
          end_time - start_time, i + 1, the_pass.name)
      start_time = end_time
      Ctx().clean()
      # Allow the artifact manager to clean up artifacts that are no
      # longer needed:
      artifact_manager.pass_done(the_pass)

      check_for_garbage()

    # Tell the artifact manager about passes that are being deferred:
    for the_pass in self.passes[index_end:]:
      artifact_manager.pass_deferred(the_pass)

    stats_keeper.set_end_time(time.time())

    Log().quiet(stats_keeper)
    Log().normal(stats_keeper.timings())

    if index_end == self.num_passes:
      # The overall conversion is done:
      artifact_manager.pass_done(self)
    else:
      # The end is yet to come:
      artifact_manager.pass_continued(self)

    # Consistency check:
    artifact_manager.check_clean()

  def help_passes(self):
    """Output (to sys.stdout) the indices and names of available passes."""

    print 'PASSES:'
    for i in range(len(self.passes)):
      print '%5d : %s' % (i + 1, self.passes[i].name,)


