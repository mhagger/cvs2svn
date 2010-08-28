# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import logger
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
    if logger.is_on(logger.DEBUG):
      logger.debug(
          'INTERNAL: %d unreachable object(s) were garbage collected:'
          % (gc_count,)
          )
      for g in gc.garbage:
        logger.debug('    %s' % (g,))
    del gc.garbage[:]


class Pass(object):
  """Base class for one step of the conversion."""

  def __init__(self):
    # By default, use the pass object's class name as the pass name:
    self.name = self.__class__.__name__

  def register_artifacts(self):
    """Register artifacts (created and needed) in artifact_manager."""

    raise NotImplementedError()

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

    raise NotImplementedError()


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
      for (i, the_pass) in enumerate(self.passes):
        if the_pass.name == pass_name:
          return i + 1
      raise InvalidPassError('Unknown pass name (%r).' % (pass_name,))

  def run(self, run_options):
    """Run the specified passes, one after another.

    RUN_OPTIONS will be passed to the Passes' run() methods.
    RUN_OPTIONS.start_pass is the number of the first pass that should
    be run.  RUN_OPTIONS.end_pass is the number of the last pass that
    should be run.  It must be that 1 <= RUN_OPTIONS.start_pass <=
    RUN_OPTIONS.end_pass <= self.num_passes."""

    # Convert start_pass and end_pass into the indices of the passes
    # to execute, using the Python index range convention (i.e., first
    # pass executed and first pass *after* the ones that should be
    # executed).
    index_start = run_options.start_pass - 1
    index_end = run_options.end_pass

    # Inform the artifact manager when artifacts are created and used:
    for (i, the_pass) in enumerate(self.passes):
      the_pass.register_artifacts()
      # Each pass creates a new version of the statistics file:
      artifact_manager.register_temp_file(
          config.STATISTICS_FILE % (i + 1,), the_pass
          )
      if i != 0:
        # Each pass subsequent to the first reads the statistics file
        # from the preceding pass:
        artifact_manager.register_temp_file_needed(
            config.STATISTICS_FILE % (i + 1 - 1,), the_pass
            )

    # Tell the artifact manager about passes that are being skipped this run:
    for the_pass in self.passes[0:index_start]:
      artifact_manager.pass_skipped(the_pass)

    start_time = time.time()
    for i in range(index_start, index_end):
      the_pass = self.passes[i]
      logger.quiet('----- pass %d (%s) -----' % (i + 1, the_pass.name,))
      artifact_manager.pass_started(the_pass)

      if i == 0:
        stats_keeper = StatsKeeper()
      else:
        stats_keeper = read_stats_keeper(
            artifact_manager.get_temp_file(
                config.STATISTICS_FILE % (i + 1 - 1,)
                )
            )

      the_pass.run(run_options, stats_keeper)
      end_time = time.time()
      stats_keeper.log_duration_for_pass(
          end_time - start_time, i + 1, the_pass.name
          )
      logger.normal(stats_keeper.single_pass_timing(i + 1))
      stats_keeper.archive(
          artifact_manager.get_temp_file(config.STATISTICS_FILE % (i + 1,))
          )
      start_time = end_time
      Ctx().clean()
      # Allow the artifact manager to clean up artifacts that are no
      # longer needed:
      artifact_manager.pass_done(the_pass, Ctx().skip_cleanup)

      check_for_garbage()

    # Tell the artifact manager about passes that are being deferred:
    for the_pass in self.passes[index_end:]:
      artifact_manager.pass_deferred(the_pass)

    logger.quiet(stats_keeper)
    logger.normal(stats_keeper.timings())

    # Consistency check:
    artifact_manager.check_clean()

  def help_passes(self):
    """Output (to sys.stdout) the indices and names of available passes."""

    print 'PASSES:'
    for (i, the_pass) in enumerate(self.passes):
      print '%5d : %s' % (i + 1, the_pass.name,)


