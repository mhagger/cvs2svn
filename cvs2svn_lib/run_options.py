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

"""This module contains classes to set cvs2svn run options."""


import sys
import os
import re
import optparse
import time

from cvs2svn_lib.version import VERSION
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import CVSTextDecoder
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_output_option import DumpfileOutputOption
from cvs2svn_lib.svn_output_option import NewRepositoryOutputOption
from cvs2svn_lib.svn_output_option import ExistingRepositoryOutputOption
from cvs2svn_lib.project import Project
from cvs2svn_lib.pass_manager import InvalidPassError
from cvs2svn_lib.revision_manager import NullRevisionRecorder
from cvs2svn_lib.revision_manager import NullRevisionExcluder
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.checkout_internal import InternalRevisionRecorder
from cvs2svn_lib.checkout_internal import InternalRevisionExcluder
from cvs2svn_lib.checkout_internal import InternalRevisionReader
from cvs2svn_lib.symbol_strategy import AllBranchRule
from cvs2svn_lib.symbol_strategy import AllTagRule
from cvs2svn_lib.symbol_strategy import BranchIfCommitsRule
from cvs2svn_lib.symbol_strategy import ExcludeRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceBranchRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceTagRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ExcludeTrivialImportBranchRule
from cvs2svn_lib.symbol_strategy import HeuristicStrategyRule
from cvs2svn_lib.symbol_strategy import UnambiguousUsageRule
from cvs2svn_lib.symbol_strategy import HeuristicPreferredParentRule
from cvs2svn_lib.symbol_strategy import SymbolHintsFileRule
from cvs2svn_lib.symbol_strategy import TrunkPathRule
from cvs2svn_lib.symbol_strategy import BranchesPathRule
from cvs2svn_lib.symbol_strategy import TagsPathRule
from cvs2svn_lib.symbol_transform import ReplaceSubstringsSymbolTransform
from cvs2svn_lib.symbol_transform import RegexpSymbolTransform
from cvs2svn_lib.symbol_transform import NormalizePathsSymbolTransform
from cvs2svn_lib.property_setters import AutoPropsPropertySetter
from cvs2svn_lib.property_setters import CVSBinaryFileDefaultMimeTypeSetter
from cvs2svn_lib.property_setters import CVSBinaryFileEOLStyleSetter
from cvs2svn_lib.property_setters import CVSRevisionNumberSetter
from cvs2svn_lib.property_setters import DefaultEOLStyleSetter
from cvs2svn_lib.property_setters import EOLStyleFromMimeTypeSetter
from cvs2svn_lib.property_setters import ExecutablePropertySetter
from cvs2svn_lib.property_setters import KeywordsPropertySetter
from cvs2svn_lib.property_setters import MimeMapper
from cvs2svn_lib.property_setters import SVNBinaryFileKeywordsPropertySetter


class GetoptOptions(object):
  """Backwards compatibility adapter for getopt-style options.

  optparse-compatible options can be created with the __call__()
  method.  When such an option is seen, it appends (opt, value) tuples
  to self.opts.  These can be processed in a getopt-style option
  processing loop."""

  def __init__(self, opts):
    self.opts = opts

  def __call__(self, *args, **kw):
    """Create an optparse-compatible Option object.

    The arguments are compatible with those of the optparse.Options
    constructor, except that action is allways set to 'callback' and
    the callback is always set to self.callback.  In particular, if
    the option should take an argument, then the 'type' keyword
    argument should be used."""

    kw['action'] = 'callback'
    kw['callback'] = self.callback
    return optparse.Option(*args, **kw)

  def callback(self, option, opt_str, value, parser):
    self.opts.append((opt_str, value,))


usage = """\
Usage: %prog --options OPTIONFILE
       %prog [OPTION...] OUTPUT-OPTION CVS-REPOS-PATH"""

description="""\
Convert a CVS repository into a Subversion repository, including history.
"""


class IncompatibleOption(optparse.Option):
  """An optparse.Option that is incompatible with the --options option.

  Record that the option was used so that error checking can later be
  done."""

  def __init__(self, *args, **kw):
    optparse.Option.__init__(self, *args, **kw)

  def take_action(self, action, dest, opt, value, values, parser):
    oio = parser.values.options_incompatible_options
    if opt not in oio:
      oio.append(opt)
    return optparse.Option.take_action(
        self, action, dest, opt, value, values, parser
        )


class RunOptions:
  """A place to store meta-options that are used to start the conversion."""

  def __init__(self, progname, cmd_args, pass_manager):
    """Process the command-line options, storing run options to SELF.

    PROGNAME is the name of the program, used in the usage string.
    CMD_ARGS is the list of command-line arguments passed to the
    program.  PASS_MANAGER is an instance of PassManager, needed to
    help process the -p and --help-passes options."""

    self.pass_manager = pass_manager
    self.start_pass = 1
    self.end_pass = self.pass_manager.num_passes
    self.profiling = False
    self.progname = progname

    self.projects = []

    # A list of one list of SymbolStrategyRules for each project:
    self.project_symbol_strategy_rules = []

    self.opts = []
    go = GetoptOptions(self.opts)

    parser = self.parser = optparse.OptionParser(
        usage=usage,
        description=description,
        add_help_option=False,
        )
    # A place to record any options used that are incompatible with
    # --options:
    parser.set_default('options_incompatible_options', [])

    group = parser.add_option_group('Configuration via options file')
    parser.set_default('options_files', [])
    group.add_option(
        '--options', type='string',
        action='append', dest='options_files',
        help=(
            'read the conversion options from PATH.  This '
            'method allows more flexibility than using '
            'command-line options.  See documentation for info'
            ),
        metavar='PATH',
        )


    group = parser.add_option_group('Output options')
    group.add_option(IncompatibleOption(
        '--svnrepos', '-s', type='string',
        action='store',
        help='path where SVN repos should be created',
        metavar='PATH',
        ))
    parser.set_default('existing_svnrepos', False)
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
    parser.set_default('bdb_txn_nosync', False)
    group.add_option(IncompatibleOption(
        '--bdb-txn-nosync',
        action='store_true',
        help=(
            'pass --bdb-txn-nosync to "svnadmin create" (for use with '
            '--svnrepos)'
            ),
        ))
    parser.set_default('create_options', [])
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
    group.add_option(
        '--dry-run',
        action='callback', callback=self.callback_dry_run,
        help=(
            'do not create a repository or a dumpfile; just print what '
            'would happen.'
            ),
        )

    # Deprecated options:
    parser.set_default('dump_only', False)
    group.add_option(IncompatibleOption(
        '--dump-only',
        action='callback', callback=self.callback_dump_only,
        help=optparse.SUPPRESS_HELP
        ))
    group.add_option(go('--create', help=optparse.SUPPRESS_HELP))


    group = parser.add_option_group('Conversion options')
    group.add_option(go(
        '--trunk-only',
        help='convert only trunk commits, not tags nor branches',
        ))
    group.add_option(go(
        '--trunk', type='string',
        help=(
            'path for trunk (default: %s)'
            % (config.DEFAULT_TRUNK_BASE,)
            ),
        metavar='PATH',
        ))
    group.add_option(go(
        '--branches', type='string',
        help=(
            'path for branches (default: %s)'
            % (config.DEFAULT_BRANCHES_BASE,)
            ),
        metavar='PATH',
        ))
    group.add_option(go(
        '--tags', type='string',
        help=(
            'path for tags (default: %s)'
            % (config.DEFAULT_TAGS_BASE,)
            ),
        metavar='PATH',
        ))
    group.add_option(go(
        '--no-prune',
        help='don\'t prune empty directories',
        ))
    group.add_option(go(
        '--encoding', type='string',
        help=(
            'encoding for paths and log messages in CVS repos.  '
            'If option is specified multiple times, encoders '
            'are tried in order until one succeeds.  See '
            'http://docs.python.org/lib/standard-encodings.html '
            'for a list of standard Python encodings.'
            ),
        metavar='ENC',
        ))
    group.add_option(go(
        '--fallback-encoding', type='string',
        help='If all --encodings fail, use lossy encoding with ENC',
        metavar='ENC',
        ))
    group.add_option(go(
        '--symbol-transform', type='string',
        help=(
            'transform symbol names from P to S, where P and S '
            'use Python regexp and reference syntax '
            'respectively.  P must match the whole symbol name'
            ),
        metavar='P:S',
        ))
    group.add_option(go(
        '--symbol-hints', type='string',
        help='read symbol conversion hints from PATH',
        metavar='PATH',
        ))
    group.add_option(go(
        '--force-branch', type='string',
        help='force symbols matching REGEXP to be branches',
        metavar='REGEXP',
        ))
    group.add_option(go(
        '--force-tag', type='string',
        help='force symbols matching REGEXP to be tags',
        metavar='REGEXP',
        ))
    group.add_option(go(
        '--exclude', type='string',
        help='exclude branches and tags matching REGEXP',
        metavar='REGEXP',
        ))
    parser.set_default('keep_trivial_imports', False)
    group.add_option(IncompatibleOption(
        '--keep-trivial-imports',
        action='store_true',
        help=(
            'do not exclude branches that were only used for '
            'a single import (usually these are unneeded)'
            ),
        ))
    parser.set_default('symbol_default', 'heuristic')
    group.add_option(IncompatibleOption(
        '--symbol-default', type='choice',
        choices=['heuristic', 'strict', 'branch', 'tag'],
        help=(
            'specify how ambiguous symbols are converted.  '
            'OPT is "heuristic" (default), "strict", "branch", '
            'or "tag"'
            ),
        metavar='OPT',
        ))
    group.add_option(go(
        '--keep-cvsignore',
        help=(
            'keep .cvsignore files (in addition to creating '
            'the analogous svn:ignore properties)'
            ),
        ))
    group.add_option(go(
        '--no-cross-branch-commits',
        help='prevent the creation of cross-branch commits',
        ))
    group.add_option(go(
        '--retain-conflicting-attic-files',
        help=(
            'if a file appears both in and out of '
            'the CVS Attic, then leave the attic version in a '
            'SVN directory called "Attic"'
            ),
        ))
    group.add_option(go(
        '--username', type='string',
        help='username for cvs2svn-synthesized commits',
        metavar='NAME',
        ))
    group.add_option(go(
        '--cvs-revnums',
        help='record CVS revision numbers as file properties',
        ))
    parser.set_default('mime_types_files', [])
    group.add_option(IncompatibleOption(
        '--mime-types', type='string',
        action='append', dest='mime_types_files',
        help=(
            'specify an apache-style mime.types file for setting '
            'svn:mime-type'
            ),
        metavar='FILE',
        ))
    parser.set_default('eol_from_mime_type', False)
    group.add_option(IncompatibleOption(
        '--eol-from-mime-type',
        action='store_true',
        help='set svn:eol-style from mime type if known',
        ))
    parser.set_default('auto_props_files', [])
    group.add_option(IncompatibleOption(
        '--auto-props', type='string',
        action='append', dest='auto_props_files',
        help=(
            'set file properties from the auto-props section '
            'of a file in svn config format'
            ),
        metavar='FILE',
        ))
    group.add_option(IncompatibleOption(
        '--default-eol', type='choice',
        choices=['binary', 'native', 'CRLF', 'LF', 'CR'],
        help=(
            'default svn:eol-style for non-binary files with '
            'undetermined mime types.  VALUE is "binary" '
            '(default), "native", "CRLF", "LF", or "CR"'
            ),
        metavar='VALUE',
        ))
    parser.set_default('keywords_off', False)
    group.add_option(IncompatibleOption(
        '--keywords-off',
        action='store_true',
        help=(
            'don\'t set svn:keywords on any files (by default, '
            'cvs2svn sets svn:keywords on non-binary files to "%s")'
            % (config.SVN_KEYWORDS_VALUE,)
            ),
        ))

    # Deprecated options:
    group.add_option(go('--no-default-eol', help=optparse.SUPPRESS_HELP))
    parser.set_default('auto_props_ignore_case', True)
    # True is the default now, so this option has no effect:
    group.add_option(IncompatibleOption(
        '--auto-props-ignore-case',
        action='store_true',
        help=optparse.SUPPRESS_HELP,
        ))


    group = parser.add_option_group('Extraction options')
    parser.set_default('use_rcs', False)
    group.add_option(IncompatibleOption(
        '--use-rcs',
        action='store_true',
        help='use RCS to extract revision contents',
        ))
    parser.set_default('use_cvs', False)
    group.add_option(IncompatibleOption(
        '--use-cvs',
        action='store_true',
        help=(
            'use CVS to extract revision contents '
            '(only use this if having problems with RCS)'
            ),
        ))
    parser.set_default('use_internal_co', False)
    group.add_option(IncompatibleOption(
        '--use-internal-co',
        action='store_true',
        help=(
            'use internal code to extract revision contents '
            '(very fast but disk space intensive) (default)'
            ),
        ))


    group = parser.add_option_group('Environment options')
    group.add_option(go(
        '--tmpdir', type='string',
        help=(
            'directory to use for temporary data files '
            '(default "cvs2svn-tmp")'
            ),
        metavar='PATH',
        ))
    group.add_option(go(
        '--svnadmin', type='string',
        help='path to the "svnadmin" program',
        metavar='PATH',
        ))
    parser.set_default('co_executable', config.CO_EXECUTABLE)
    group.add_option(IncompatibleOption(
        '--co', type='string',
        action='store', dest='co_executable',
        help='path to the "co" program (required if --use-rcs)',
        metavar='PATH',
        ))
    group.add_option(go(
        '--cvs', type='string',
        help='path to the "cvs" program (required if --use-cvs)',
        metavar='PATH',
        ))
    group.add_option(go(
        '--sort', type='string',
        help='path to the GNU "sort" program',
        metavar='PATH',
        ))


    group = parser.add_option_group('Partial conversions')
    group.add_option(
        '--pass', type='string',
        action='callback', callback=self.callback_passes,
        help='execute only specified PASS of conversion',
        metavar='PASS',
        )
    group.add_option(
        '--passes', '-p', type='string',
        action='callback', callback=self.callback_passes,
        help=(
            'execute passes START through END, inclusive (PASS, '
            'START, and END can be pass names or numbers)'
            ),
        metavar='[START]:[END]',
        )


    group = parser.add_option_group('Information options')
    group.add_option(
        '--version',
        action='callback', callback=self.callback_version,
        help='print the version number',
        )
    group.add_option(
        '--help', '-h',
        action="help",
        help='print this usage message and exit with success',
        )
    group.add_option(
        '--help-passes',
        action='callback', callback=self.callback_help_passes,
        help='list the available passes and their numbers',
        )
    group.add_option(
        '--verbose', '-v',
        action='callback', callback=self.callback_verbose,
        help='verbose (may be specified twice for debug output)',
        )
    group.add_option(
        '--quiet', '-q',
        action='callback', callback=self.callback_quiet,
        help='quiet (may be specified twice for very quiet)',
        )
    group.add_option(go(
        '--write-symbol-info', type='string',
        help='write information and statistics about CVS symbols to PATH.',
        metavar='PATH',
        ))
    group.add_option(go(
        '--skip-cleanup',
        help='prevent the deletion of intermediate files',
        ))
    group.add_option(
        '--profile',
        action='callback', callback=self.callback_profile,
        help='profile with \'hotshot\' (into file cvs2svn.hotshot)',
        )

    (self.options, self.args) = parser.parse_args()

    # Next look for any --options options, process them, and remove
    # them from the list, as they affect the processing of other
    # options:
    options_file_found = False
    for value in self.options.options_files:
      self.process_options_file(value)
      options_file_found = True

    # Now the log level has been set; log the time when the run started:
    Log().verbose(
        time.strftime(
            'Conversion start time: %Y-%m-%d %I:%M:%S %Z',
            time.localtime(Log().start_time)
            )
        )

    if options_file_found:
      # All of the options that are compatible with --options have
      # been consumed above.  It is an error if any other options or
      # arguments are left:
      self.verify_options_consumed()
    else:
      # --options was not specified.  So we can process other options
      # that are not compatible with --options.
      self.process_remaining_options()

    # Check for problems with the options:
    self.check_options()

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

  def callback_help_passes(self, option, opt_str, value, parser):
    self.pass_manager.help_passes()
    sys.exit(0)

  def callback_version(self, option, opt_str, value, parser):
    sys.stdout.write(
        '%s version %s\n' % (os.path.basename(self.progname), VERSION)
        )
    sys.exit(0)

  def callback_verbose(self, option, opt_str, value, parser):
    Log().increase_verbosity()

  def callback_quiet(self, option, opt_str, value, parser):
    Log().decrease_verbosity()

  def callback_passes(self, option, opt_str, value, parser):
    if value.find(':') >= 0:
      start_pass, end_pass = value.split(':')
      self.start_pass = self.pass_manager.get_pass_number(start_pass, 1)
      self.end_pass = self.pass_manager.get_pass_number(
          end_pass, self.pass_manager.num_passes
          )
    else:
      self.end_pass = \
          self.start_pass = \
          self.pass_manager.get_pass_number(value)

  def callback_dry_run(self, option, opt_str, value, parser):
    Ctx().dry_run = True

  def callback_profile(self, option, opt_str, value, parser):
    self.profiling = True

  def callback_dump_only(self, option, opt_str, value, parser):
    parser.values.dump_only = True
    Log().error(
        warning_prefix +
        ': The --dump-only option is deprecated (it is implied '
        'by --dumpfile).\n'
        )

  def process_remaining_options(self):
    """Process the options that are not compatible with --options."""

    # Convenience var, so we don't have to keep instantiating this Borg.
    ctx = Ctx()

    options = self.options

    options.cvs_executable = config.CVS_EXECUTABLE
    options.trunk_base = config.DEFAULT_TRUNK_BASE
    options.branches_base = config.DEFAULT_BRANCHES_BASE
    options.tags_base = config.DEFAULT_TAGS_BASE
    options.encodings = ['ascii']
    options.fallback_encoding = None
    options.force_branch = False
    options.force_tag = False
    options.symbol_transforms = []
    options.symbol_strategy_rules = []

    for opt, value in self.opts:
      if opt == '--trunk-only':
        ctx.trunk_only = True
      elif opt == '--trunk':
        options.trunk_base = value
      elif opt == '--branches':
        options.branches_base = value
      elif opt == '--tags':
        options.tags_base = value
      elif opt == '--no-prune':
        ctx.prune = False
      elif opt == '--encoding':
        options.encodings.insert(-1, value)
      elif opt == '--fallback-encoding':
        options.fallback_encoding = value
      elif opt == '--symbol-hints':
        options.symbol_strategy_rules.append(SymbolHintsFileRule(value))
      elif opt == '--force-branch':
        options.symbol_strategy_rules.append(
            ForceBranchRegexpStrategyRule(value)
            )
        options.force_branch = True
      elif opt == '--force-tag':
        options.symbol_strategy_rules.append(
            ForceTagRegexpStrategyRule(value)
            )
        options.force_tag = True
      elif opt == '--exclude':
        options.symbol_strategy_rules.append(ExcludeRegexpStrategyRule(value))
      elif opt == '--keep-cvsignore':
        ctx.keep_cvsignore = True
      elif opt == '--no-cross-branch-commits':
        ctx.cross_branch_commits = False
      elif opt == '--retain-conflicting-attic-files':
        ctx.retain_conflicting_attic_files = True
      elif opt == '--symbol-transform':
        [pattern, replacement] = value.split(":")
        try:
          options.symbol_transforms.append(
              RegexpSymbolTransform(pattern, replacement))
        except re.error:
          raise FatalError("'%s' is not a valid regexp." % (pattern,))
      elif opt == '--username':
        ctx.username = value
      elif opt == '--cvs-revnums':
        ctx.svn_property_setters.append(CVSRevisionNumberSetter())
      elif opt == '--no-default-eol':
        # For backwards compatibility:
        options.default_eol = None
      elif opt == '--tmpdir':
        ctx.tmpdir = value
      elif opt == '--write-symbol-info':
        ctx.symbol_info_filename = value
      elif opt == '--skip-cleanup':
        ctx.skip_cleanup = True
      elif opt == '--svnadmin':
        ctx.svnadmin_executable = value
      elif opt == '--cvs':
        options.cvs_executable = value
      elif opt == '--sort':
        ctx.sort_executable = value
      elif opt == '--create':
        Log().error(
            warning_prefix +
            ': The behaviour produced by the --create option is now the '
            'default,\nand passing the option is deprecated.\n'
            )

    # Consistency check for options and arguments.
    if len(self.args) == 0:
      self.usage()
      sys.exit(1)

    if len(self.args) > 1:
      Log().error(error_prefix + ": must pass only one CVS repository.\n")
      self.usage()
      sys.exit(1)

    cvsroot = self.args[0]

    if options.dump_only and not options.dumpfile:
      raise FatalError("'--dump-only' requires '--dumpfile' to be specified.")

    if not options.svnrepos and not options.dumpfile and not ctx.dry_run:
      raise FatalError("must pass one of '-s' or '--dumpfile'.")

    def not_both(opt1val, opt1name, opt2val, opt2name):
      if opt1val and opt2val:
        raise FatalError("cannot pass both '%s' and '%s'."
                         % (opt1name, opt2name,))

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

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    not_both(options.use_rcs, '--use-rcs',
             options.use_internal_co, '--use-internal-co')

    not_both(options.use_cvs, '--use-cvs',
             options.use_internal_co, '--use-internal-co')

    not_both(ctx.trunk_only, '--trunk-only',
             options.force_branch, '--force-branch')

    not_both(ctx.trunk_only, '--trunk-only',
             options.force_tag, '--force-tag')

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

    try:
      ctx.cvs_author_decoder = CVSTextDecoder(
          options.encodings, options.fallback_encoding
          )
      ctx.cvs_log_decoder = CVSTextDecoder(
          options.encodings, options.fallback_encoding
          )
      # Don't use fallback_encoding for filenames:
      ctx.cvs_filename_decoder = CVSTextDecoder(options.encodings)
    except LookupError, e:
      raise FatalError(str(e))

    # Add the standard symbol name cleanup rules:
    options.symbol_transforms.extend([
        ReplaceSubstringsSymbolTransform('\\','/'),
        # Remove leading, trailing, and repeated slashes:
        NormalizePathsSymbolTransform(),
        ])

    if not options.keep_trivial_imports:
      options.symbol_strategy_rules.append(ExcludeTrivialImportBranchRule())

    options.symbol_strategy_rules.append(UnambiguousUsageRule())
    if options.symbol_default == 'strict':
      pass
    elif options.symbol_default == 'branch':
      options.symbol_strategy_rules.append(AllBranchRule())
    elif options.symbol_default == 'tag':
      options.symbol_strategy_rules.append(AllTagRule())
    elif options.symbol_default == 'heuristic':
      options.symbol_strategy_rules.append(BranchIfCommitsRule())
      options.symbol_strategy_rules.append(HeuristicStrategyRule())
    else:
      assert False

    # Now add a rule whose job it is to pick the preferred parents of
    # branches and tags:
    options.symbol_strategy_rules.append(HeuristicPreferredParentRule())

    for value in options.auto_props_files:
      ctx.svn_property_setters.append(
          AutoPropsPropertySetter(value, options.auto_props_ignore_case)
          )

    for value in options.mime_types_files:
      ctx.svn_property_setters.append(MimeMapper(value))

    ctx.svn_property_setters.append(CVSBinaryFileEOLStyleSetter())

    ctx.svn_property_setters.append(CVSBinaryFileDefaultMimeTypeSetter())

    if options.eol_from_mime_type:
      ctx.svn_property_setters.append(EOLStyleFromMimeTypeSetter())

    ctx.svn_property_setters.append(
        DefaultEOLStyleSetter(options.default_eol)
        )

    ctx.svn_property_setters.append(SVNBinaryFileKeywordsPropertySetter())

    if not options.keywords_off:
      ctx.svn_property_setters.append(
          KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE))

    ctx.svn_property_setters.append(ExecutablePropertySetter())

    # Create the default project (using ctx.trunk, ctx.branches, and
    # ctx.tags):
    self.add_project(
        cvsroot,
        trunk_path=options.trunk_base,
        branches_path=options.branches_base,
        tags_path=options.tags_base,
        symbol_transforms=options.symbol_transforms,
        symbol_strategy_rules=options.symbol_strategy_rules,
        )

  def check_options(self):
    """Check the the run options are OK.

    This should only be called after all options have been processed."""

    # Convenience var, so we don't have to keep instantiating this Borg.
    ctx = Ctx()

    if not self.start_pass <= self.end_pass:
      raise InvalidPassError(
          'Ending pass must not come before starting pass.')

    if not ctx.dry_run and ctx.output_option is None:
      raise FatalError('No output option specified.')

    if ctx.output_option is not None:
      ctx.output_option.check()

    if not self.projects:
      raise FatalError('No project specified.')

  def get_options(self, *names):
    """Return a list of (option,value) pairs for options in NAMES.

    Return a list containing any (opt, value) pairs from self.opts
    where opt is in NAMES.  The matching options are removed from
    self.opts."""

    retval = []
    i = 0
    while i < len(self.opts):
      (opt, value) = self.opts[i]
      if opt in names:
        del self.opts[i]
        retval.append( (opt, value) )
      else:
        i += 1
    return retval

  def verify_options_consumed(self):
    """Verify that all command line options and arguments have been used.

    The --options option was specified, and all options that are
    compatible with that option have already been consumed.  Verify
    that there are no remaining (i.e., incompatible) options or
    arguments."""

    if self.options.options_incompatible_options or self.opts or self.args:
      if self.options.options_incompatible_options or self.opts:
        oio = (
          self.options.options_incompatible_options
          + [opt for (opt,value) in self.opts]
          )
        Log().error(
            '%s: The following options cannot be used in combination with '
            'the --options\n'
            'option:\n'
            '    %s\n'
            % (error_prefix, '\n    '.join(oio))
            )
      if self.args:
        Log().error(
            '%s: No cvs-repos-path arguments are allowed with the --options '
            'option.\n'
            % (error_prefix,)
            )
      sys.exit(1)

  def process_options_file(self, options_filename):
    """Read options from the file named OPTIONS_FILENAME.

    Store the run options to SELF."""

    g = {}
    l = {
      'ctx' : Ctx(),
      'run_options' : self,
      }
    execfile(options_filename, g, l)

  def usage(self):
    self.parser.print_help()


