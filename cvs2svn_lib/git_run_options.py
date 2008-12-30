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

"""This module manages cvs2git run options."""


from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption


class GitRunOptions(RunOptions):
  def _get_output_options_group(self):
    group = RunOptions._get_output_options_group(self)

    group.add_option(ContextOption(
        '--dry-run',
        action='store_true',
        help=(
            'do not create any output; just print what would happen.'
            ),
        ))

    return group

  def process_extraction_options(self):
    """Process options related to extracting data from the CVS repository."""

    ctx = Ctx()
    options = self.options

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    if options.use_rcs:
      raise NotImplementedError()
    elif options.use_cvs:
      raise NotImplementedError()
    else:
      # --use-cvs is the default:
      pass


