#!/usr/bin/env python
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

import os
import errno
import gc

try:
  # Try to get access to a bunch of encodings for use with --encoding.
  # See http://cjkpython.i18n.org/ for details.
  import iconv_codec
except ImportError:
  pass

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.svn_run_options import SVNRunOptions
from cvs2svn_lib.git_run_options import GitRunOptions
from cvs2svn_lib.bzr_run_options import BzrRunOptions
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.pass_manager import PassManager
from cvs2svn_lib.passes import passes


def main(progname, run_options, pass_manager):
  # Disable garbage collection, as we try not to create any circular
  # data structures:
  gc.disable()

  # Convenience var, so we don't have to keep instantiating this Borg.
  ctx = Ctx()

  # Make sure the tmp directory exists.  Note that we don't check if
  # it's empty -- we want to be able to use, for example, "." to hold
  # tempfiles.
  if not os.path.exists(ctx.tmpdir):
    erase_tmpdir = True
    os.mkdir(ctx.tmpdir)
  elif not os.path.isdir(ctx.tmpdir):
    raise FatalError(
        "cvs2svn tried to use '%s' for temporary files, but that path\n"
        "  exists and is not a directory.  Please make it be a directory,\n"
        "  or specify some other directory for temporary files."
        % (ctx.tmpdir,))
  else:
    erase_tmpdir = False

  # But do lock the tmpdir, to avoid process clash.
  try:
    os.mkdir(os.path.join(ctx.tmpdir, 'cvs2svn.lock'))
  except OSError, e:
    if e.errno == errno.EACCES:
      raise FatalError("Permission denied:"
                       + " No write access to directory '%s'." % ctx.tmpdir)
    if e.errno == errno.EEXIST:
      raise FatalError(
          "cvs2svn is using directory '%s' for temporary files, but\n"
          "  subdirectory '%s/cvs2svn.lock' exists, indicating that another\n"
          "  cvs2svn process is currently using '%s' as its temporary\n"
          "  workspace.  If you are certain that is not the case,\n"
          "  then remove the '%s/cvs2svn.lock' subdirectory."
          % (ctx.tmpdir, ctx.tmpdir, ctx.tmpdir, ctx.tmpdir,))
    raise

  try:
    if run_options.profiling:
      try:
        import cProfile
      except ImportError:
        # Old version of Python without cProfile.  Use hotshot instead.
        import hotshot
        prof = hotshot.Profile('cvs2svn.hotshot')
        prof.runcall(pass_manager.run, run_options)
        prof.close()
      else:
        # Recent version of Python (2.5+) with cProfile.
        def run_with_profiling():
          pass_manager.run(run_options)
        cProfile.runctx(
            'run_with_profiling()', globals(), locals(), 'cvs2svn.cProfile'
            )
    else:
      pass_manager.run(run_options)
  finally:
    try:
      os.rmdir(os.path.join(ctx.tmpdir, 'cvs2svn.lock'))
    except:
      pass

    if erase_tmpdir:
      try:
        os.rmdir(ctx.tmpdir)
      except:
        pass


def svn_main(progname, cmd_args):
  pass_manager = PassManager(passes)
  run_options = SVNRunOptions(progname, cmd_args, pass_manager)
  main(progname, run_options, pass_manager)


def git_main(progname, cmd_args):
  pass_manager = PassManager(passes)
  run_options = GitRunOptions(progname, cmd_args, pass_manager)
  main(progname, run_options, pass_manager)


def bzr_main(progname, cmd_args):
  pass_manager = PassManager(passes)
  run_options = BzrRunOptions(progname, cmd_args, pass_manager)
  main(progname, run_options, pass_manager)


def hg_main(progname, cmd_args):
  # Import late so cvs2{svn,git} do not depend on being able to import
  # the Mercurial API.
  from cvs2svn_lib.hg_run_options import HgRunOptions

  pass_manager = PassManager(passes)
  run_options = HgRunOptions(progname, cmd_args, pass_manager)
  main(progname, run_options, pass_manager)
