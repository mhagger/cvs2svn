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

"""This module manages cvs2svn run options."""


import optparse

from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.project import Project
from cvs2svn_lib.svn_output_option import DumpfileOutputOption
from cvs2svn_lib.svn_output_option import ExistingRepositoryOutputOption
from cvs2svn_lib.svn_output_option import NewRepositoryOutputOption
from cvs2svn_lib.revision_manager import NullRevisionRecorder
from cvs2svn_lib.revision_manager import NullRevisionExcluder
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.checkout_internal import InternalRevisionRecorder
from cvs2svn_lib.checkout_internal import InternalRevisionExcluder
from cvs2svn_lib.checkout_internal import InternalRevisionReader
from cvs2svn_lib.symbol_strategy import TrunkPathRule
from cvs2svn_lib.symbol_strategy import BranchesPathRule
from cvs2svn_lib.symbol_strategy import TagsPathRule


class SVNRunOptions(RunOptions):
  def _get_output_options_group(self):
    group = RunOptions._get_output_options_group(self)

    group.add_option(IncompatibleOption(
        '--svnrepos', '-s', type='string',
        action='store',
        help='path where SVN repos should be created',
        metavar='PATH',
        ))
    self.parser.set_default('existing_svnrepos', False)
    group.add_option(IncompatibleOption(
        '--existing-svnrepos',
        action='store_true',
        help='load into existing SVN repository (for use with --svnrepos)',
        ))
    group.add_option(IncompatibleOption(
        '--fs-type', type='string',
        action='store',
        help=(
            'pass --fs-type=TYPE to "svnadmin create" (for use with '
            '--svnrepos)'
            ),
        metavar='TYPE',
        ))
    self.parser.set_default('bdb_txn_nosync', False)
    group.add_option(IncompatibleOption(
        '--bdb-txn-nosync',
        action='store_true',
        help=(
            'pass --bdb-txn-nosync to "svnadmin create" (for use with '
            '--svnrepos)'
            ),
        ))
    self.parser.set_default('create_options', [])
    group.add_option(IncompatibleOption(
        '--create-option', type='string',
        action='append', dest='create_options',
        help='pass OPT to "svnadmin create" (for use with --svnrepos)',
        metavar='OPT',
        ))
    group.add_option(IncompatibleOption(
        '--dumpfile', type='string',
        action='store',
        help='just produce a dumpfile; don\'t commit to a repos',
        metavar='PATH',
        ))

    group.add_option(ContextOption(
        '--dry-run',
        action='store_true',
        help=(
            'do not create a repository or a dumpfile; just print what '
            'would happen.'
            ),
        ))

    # Deprecated options:
    self.parser.set_default('dump_only', False)
    group.add_option(IncompatibleOption(
        '--dump-only',
        action='callback', callback=self.callback_dump_only,
        help=optparse.SUPPRESS_HELP,
        ))
    group.add_option(IncompatibleOption(
        '--create',
        action='callback', callback=self.callback_create,
        help=optparse.SUPPRESS_HELP,
        ))

    return group

  def _get_conversion_options_group(self):
    group = RunOptions._get_conversion_options_group(self)

    self.parser.set_default('trunk_base', config.DEFAULT_TRUNK_BASE)
    group.add_option(IncompatibleOption(
        '--trunk', type='string',
        action='store', dest='trunk_base',
        help=(
            'path for trunk (default: %s)'
            % (config.DEFAULT_TRUNK_BASE,)
            ),
        metavar='PATH',
        ))
    self.parser.set_default('branches_base', config.DEFAULT_BRANCHES_BASE)
    group.add_option(IncompatibleOption(
        '--branches', type='string',
        action='store', dest='branches_base',
        help=(
            'path for branches (default: %s)'
            % (config.DEFAULT_BRANCHES_BASE,)
            ),
        metavar='PATH',
        ))
    self.parser.set_default('tags_base', config.DEFAULT_TAGS_BASE)
    group.add_option(IncompatibleOption(
        '--tags', type='string',
        action='store', dest='tags_base',
        help=(
            'path for tags (default: %s)'
            % (config.DEFAULT_TAGS_BASE,)
            ),
        metavar='PATH',
        ))
    group.add_option(ContextOption(
        '--no-prune',
        action='store_false', dest='prune',
        help='don\'t prune empty directories',
        ))
    group.add_option(ContextOption(
        '--no-cross-branch-commits',
        action='store_false', dest='cross_branch_commits',
        help='prevent the creation of cross-branch commits',
        ))

    return group

  def _get_extraction_options_group(self):
    group = RunOptions._get_extraction_options_group(self)

    self.parser.set_default('use_internal_co', False)
    group.add_option(IncompatibleOption(
        '--use-internal-co',
        action='store_true',
        help=(
            'use internal code to extract revision contents '
            '(very fast but disk space intensive) (default)'
            ),
        ))

    return group

  def _get_environment_options_group(self):
    group = RunOptions._get_environment_options_group(self)

    group.add_option(ContextOption(
        '--svnadmin', type='string',
        action='store', dest='svnadmin_executable',
        help='path to the "svnadmin" program',
        metavar='PATH',
        ))

    return group

  def callback_dump_only(self, option, opt_str, value, parser):
    parser.values.dump_only = True
    Log().error(
        warning_prefix +
        ': The --dump-only option is deprecated (it is implied '
        'by --dumpfile).\n'
        )

  def callback_create(self, option, opt_str, value, parser):
    Log().error(
        warning_prefix +
        ': The behaviour produced by the --create option is now the '
        'default;\n'
        'passing the option is deprecated.\n'
        )

  def process_output_options(self):
    """Process the options related to SVN output."""

    RunOptions.process_output_options(self)

    ctx = Ctx()
    options = self.options

    if options.dump_only and not options.dumpfile:
      raise FatalError("'--dump-only' requires '--dumpfile' to be specified.")

    if not options.svnrepos and not options.dumpfile and not ctx.dry_run:
      raise FatalError("must pass one of '-s' or '--dumpfile'.")

    not_both(options.svnrepos, '-s',
             options.dumpfile, '--dumpfile')

    not_both(options.dumpfile, '--dumpfile',
             options.existing_svnrepos, '--existing-svnrepos')

    not_both(options.bdb_txn_nosync, '--bdb-txn-nosync',
             options.existing_svnrepos, '--existing-svnrepos')

    not_both(options.dumpfile, '--dumpfile',
             options.bdb_txn_nosync, '--bdb-txn-nosync')

    not_both(options.fs_type, '--fs-type',
             options.existing_svnrepos, '--existing-svnrepos')

    if (
          options.fs_type
          and options.fs_type != 'bdb'
          and options.bdb_txn_nosync
          ):
      raise FatalError("cannot pass --bdb-txn-nosync with --fs-type=%s."
                       % options.fs_type)

    if options.svnrepos:
      if options.existing_svnrepos:
        ctx.output_option = ExistingRepositoryOutputOption(options.svnrepos)
      else:
        ctx.output_option = NewRepositoryOutputOption(
            options.svnrepos,
            fs_type=options.fs_type, bdb_txn_nosync=options.bdb_txn_nosync,
            create_options=options.create_options)
    else:
      ctx.output_option = DumpfileOutputOption(options.dumpfile)

  def process_extraction_options(self):
    """Process options related to extracting data from the CVS repository."""

    ctx = Ctx()
    options = self.options

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    not_both(options.use_rcs, '--use-rcs',
             options.use_internal_co, '--use-internal-co')

    not_both(options.use_cvs, '--use-cvs',
             options.use_internal_co, '--use-internal-co')

    if options.use_rcs:
      ctx.revision_recorder = NullRevisionRecorder()
      ctx.revision_excluder = NullRevisionExcluder()
      ctx.revision_reader = RCSRevisionReader(options.co_executable)
    elif options.use_cvs:
      ctx.revision_recorder = NullRevisionRecorder()
      ctx.revision_excluder = NullRevisionExcluder()
      ctx.revision_reader = CVSRevisionReader(options.cvs_executable)
    else:
      # --use-internal-co is the default:
      ctx.revision_recorder = InternalRevisionRecorder(compress=True)
      ctx.revision_excluder = InternalRevisionExcluder()
      ctx.revision_reader = InternalRevisionReader(compress=True)

  def add_project(
        self,
        project_cvs_repos_path,
        trunk_path=None, branches_path=None, tags_path=None,
        initial_directories=[],
        symbol_transforms=None,
        symbol_strategy_rules=[],
        ):
    """Add a project to be converted.

    Most arguments are passed straight through to the Project
    constructor.  SYMBOL_STRATEGY_RULES is an iterable of
    SymbolStrategyRules that will be applied to symbols in this
    project."""

    initial_directories = [
        path
        for path in [trunk_path, branches_path, tags_path]
        if path
        ] + list(initial_directories)

    symbol_strategy_rules = list(symbol_strategy_rules)

    # Add rules to set the SVN paths for LODs depending on whether
    # they are the trunk, tags, or branches:
    if trunk_path is not None:
      symbol_strategy_rules.append(TrunkPathRule(trunk_path))
    if branches_path is not None:
      symbol_strategy_rules.append(BranchesPathRule(branches_path))
    if tags_path is not None:
      symbol_strategy_rules.append(TagsPathRule(tags_path))

    id = len(self.projects)
    project = Project(
        id,
        project_cvs_repos_path,
        initial_directories=initial_directories,
        symbol_transforms=symbol_transforms,
        )

    self.projects.append(project)
    self.project_symbol_strategy_rules.append(symbol_strategy_rules)

  def clear_projects(self):
    """Clear the list of projects to be converted.

    This method is for the convenience of options files, which may
    want to import one another."""

    del self.projects[:]
    del self.project_symbol_strategy_rules[:]


