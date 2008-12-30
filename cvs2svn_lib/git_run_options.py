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
from cvs2svn_lib.run_options import RunOptions


class GitRunOptions(RunOptions):
  def _get_output_options_group(self):
    group = RunOptions._get_output_options_group(self)

    group.add_option(
        '--dry-run',
        action='callback', callback=self.callback_dry_run,
        help=(
            'do not create any output; just print what would happen.'
            ),
        )

    return group

  def callback_dry_run(self, option, opt_str, value, parser):
    Ctx().dry_run = True


