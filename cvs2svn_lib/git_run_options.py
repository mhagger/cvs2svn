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
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.project import Project
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.git_revision_recorder import GitRevisionRecorder
from cvs2svn_lib.git_output_option import GitRevisionMarkWriter
from cvs2svn_lib.git_output_option import GitOutputOption
from cvs2svn_lib.revision_manager import NullRevisionRecorder
from cvs2svn_lib.revision_manager import NullRevisionExcluder
from cvs2svn_lib.fulltext_revision_recorder \
     import SimpleFulltextRevisionRecorderAdapter


class GitRunOptions(RunOptions):
  def __init__(self, progname, cmd_args, pass_manager):
    Ctx().cross_project_commits = False
    Ctx().cross_branch_commits = False
    RunOptions.__init__(self, progname, cmd_args, pass_manager)

  def _get_output_options_group(self):
    group = RunOptions._get_output_options_group(self)

    group.add_option(IncompatibleOption(
        '--blobfile', type='string',
        action='store',
        help='path to which the "blob" data should be written',
        metavar='PATH',
        ))
    group.add_option(IncompatibleOption(
        '--dumpfile', type='string',
        action='store',
        help='path to which the revision data should be written',
        metavar='PATH',
        ))
    group.add_option(ContextOption(
        '--dry-run',
        action='store_true',
        help=(
            'do not create any output; just print what would happen.'
            ),
        ))

    return group

  def process_io_options(self):
    """Process input/output options.

    Process options related to extracting data from the CVS repository
    and writing to 'git fast-import'-formatted files."""

    ctx = Ctx()
    options = self.options

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    if options.use_rcs:
      revision_reader = RCSRevisionReader(
          co_executable=options.co_executable
          )
    else:
      # --use-cvs is the default:
      revision_reader = CVSRevisionReader(
          cvs_executable=options.cvs_executable
          )

    if ctx.dry_run:
      ctx.revision_recorder = NullRevisionRecorder()
    else:
      if not (options.blobfile and options.dumpfile):
        raise FatalError("must pass '--blobfile' and '--dumpfile' options.")
      ctx.revision_recorder = SimpleFulltextRevisionRecorderAdapter(
          revision_reader,
          GitRevisionRecorder(options.blobfile),
          )

    ctx.revision_excluder = NullRevisionExcluder()
    ctx.revision_reader = None

    ctx.output_option = GitOutputOption(
        options.dumpfile,
        GitRevisionMarkWriter(),
        max_merges=None,
        # Optional map from CVS author names to git author names:
        author_transforms={}, # FIXME
        )

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

    self.process_io_options()
    self.process_encoding_options()
    self.process_symbol_strategy_options()
    self.process_property_setter_options()

    # Create the project:
    self.set_project(
        cvsroot,
        symbol_transforms=self.options.symbol_transforms,
        symbol_strategy_rules=self.options.symbol_strategy_rules,
        )


