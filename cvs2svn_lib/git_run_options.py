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


import sys

from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.project import Project


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

  def set_project(
        self,
        project_cvs_repos_path,
        symbol_transforms=None,
        symbol_strategy_rules=[],
        ):
    """Set the project to be converted.

    If a project had already been set, overwrite it.

    Most arguments are passed straight through to the Project
    constructor.  SYMBOL_STRATEGY_RULES is an iterable of
    SymbolStrategyRules that will be applied to symbols in this
    project."""

    symbol_strategy_rules = list(symbol_strategy_rules)

    project = Project(
        0,
        project_cvs_repos_path,
        symbol_transforms=symbol_transforms,
        )

    self.projects = [project]
    self.project_symbol_strategy_rules = [symbol_strategy_rules]

  def process_options(self):
    # Consistency check for options and arguments.
    if len(self.args) == 0:
      self.usage()
      sys.exit(1)

    if len(self.args) > 1:
      Log().error(error_prefix + ": must pass only one CVS repository.\n")
      self.usage()
      sys.exit(1)

    cvsroot = self.args[0]

    RunOptions.process_options(self)

    # Create the project:
    self.set_project(
        cvsroot,
        symbol_transforms=self.options.symbol_transforms,
        symbol_strategy_rules=self.options.symbol_strategy_rules,
        )


