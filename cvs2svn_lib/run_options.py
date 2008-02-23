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


from __future__ import generators

import sys
import os
import re
import getopt
import time
try:
  my_getopt = getopt.gnu_getopt
except AttributeError:
  my_getopt = getopt.getopt

from cvs2svn_lib.boolean import *
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


usage_message_template = """\
Usage: %(progname)s --options OPTIONFILE
       %(progname)s [OPTION...] OUTPUT-OPTION CVS-REPOS-PATH
%(progname)s converts a CVS repository into a Subversion repository, including
history.

 Configuration via options file:

      --options=PATH         read the conversion options from PATH.  This
                             method allows more flexibility than using
                             command-line options.  See documentation for info

 Output options:

  -s, --svnrepos=PATH        path where SVN repos should be created
      --existing-svnrepos    load into existing SVN repository (for use with
                             --svnrepos)
      --fs-type=TYPE         pass --fs-type=TYPE to "svnadmin create" (for use
                             with --svnrepos)
      --bdb-txn-nosync       pass --bdb-txn-nosync to "svnadmin create" (for
                             use with --svnrepos)
      --dumpfile=PATH        just produce a dumpfile; don't commit to a repos
      --dry-run              do not create a repository or a dumpfile;
                             just print what would happen.

 Conversion options:

      --trunk-only           convert only trunk commits, not tags nor branches
      --trunk=PATH           path for trunk (default: %(trunk_base)s)
      --branches=PATH        path for branches (default: %(branches_base)s)
      --tags=PATH            path for tags (default: %(tags_base)s)
      --no-prune             don't prune empty directories
      --encoding=ENC         encoding for paths and log messages in CVS repos.
                             If option is specified multiple times, encoders
                             are tried in order until one succeeds.  See
                             http://docs.python.org/lib/standard-encodings.html
                             for a list of standard Python encodings.
      --fallback-encoding=ENC   If all --encodings fail, use lossy encoding
                             with ENC
      --symbol-transform=P:S transform symbol names from P to S, where P and S
                             use Python regexp and reference syntax
                             respectively.  P must match the whole symbol name
      --symbol-hints=PATH    read symbol conversion hints from PATH
      --force-branch=REGEXP  force symbols matching REGEXP to be branches
      --force-tag=REGEXP     force symbols matching REGEXP to be tags
      --exclude=REGEXP       exclude branches and tags matching REGEXP
      --symbol-default=OPT   specify how ambiguous symbols are converted.
                             OPT is "heuristic" (default), "strict", "branch",
                             or "tag"
      --no-cross-branch-commits   Prevent the creation of cross-branch commits
      --retain-conflicting-attic-files   if a file appears both in and out of
                             the CVS Attic, then leave the attic version in a
                             SVN directory called "Attic".
      --username=NAME        username for cvs2svn-synthesized commits
      --cvs-revnums          record CVS revision numbers as file properties
      --mime-types=FILE      specify an apache-style mime.types file for
                             setting svn:mime-type
      --eol-from-mime-type   set svn:eol-style from mime type if known
      --auto-props=FILE      set file properties from the auto-props section
                             of a file in svn config format
      --default-eol=VALUE    default svn:eol-style for non-binary files with
                             undetermined mime types.  VALUE is "binary"
                             (default), "native", "CRLF", "LF", or "CR"
      --keywords-off         don't set svn:keywords on any files (by default,
                             cvs2svn sets svn:keywords on non-binary files to
                             "%(svn_keywords_value)s")

 Extraction options:

      --use-rcs              use RCS to extract revision contents (default)
      --use-cvs              use CVS to extract revision contents
                             (only use this if having problems with RCS)
      --use-internal-co      use internal code to extract revision contents
                             (very fast but disk space intensive)

 Environment options:

      --tmpdir=PATH          directory to use for temporary data files
                             (default "cvs2svn-tmp")
      --svnadmin=PATH        path to the "svnadmin" program
      --co=PATH              path to the "co" program (required if --use-rcs)
      --cvs=PATH             path to the "cvs" program (required if --use-cvs)
      --sort=PATH            path to the GNU "sort" program

 Partial conversions:

  -p, --pass PASS            execute only specified PASS of conversion
  -p, --passes [START]:[END] execute passes START through END, inclusive (PASS,
                             START, and END can be pass names or numbers)

 Information options:

      --version              print the version number
  -h, --help                 print this usage message and exit with success
      --help-passes          list the available passes and their numbers
  -v, --verbose              verbose (may be specified twice for debug output)
  -q, --quiet                quiet (may be specified twice for very quiet)
      --write-symbol-info=PATH write information and statistics about CVS
                             symbols to PATH.
      --skip-cleanup         prevent the deletion of intermediate files
      --profile              profile with 'hotshot' (into file cvs2svn.hotshot)
"""

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

    try:
      self.opts, self.args = my_getopt(cmd_args, 'hvqs:p:', [
          "options=",

          "svnrepos=", "existing-svnrepos", "fs-type=", "bdb-txn-nosync",
          "dumpfile=",
          "dry-run",

          "trunk-only",
          "trunk=", "branches=", "tags=",
          "no-prune",
          "encoding=", "fallback-encoding=",
          "symbol-transform=",
          "symbol-hints=",
          "force-branch=", "force-tag=", "exclude=", "symbol-default=",
          "no-cross-branch-commits",
          "retain-conflicting-attic-files",
          "username=",
          "cvs-revnums",
          "mime-types=",
          "auto-props=",
          "eol-from-mime-type", "default-eol=",
          "keywords-off",

          "use-rcs", "use-cvs", "use-internal-co",

          "tmpdir=",
          "svnadmin=", "co=", "cvs=", "sort=",

          "pass=", "passes=",

          "version", "help", "help-passes",
          "verbose", "quiet",
          "write-symbol-info=",
          "skip-cleanup",
          "profile",

          # These options are deprecated and are only included for
          # backwards compatibility:
          "dump-only", "create", "no-default-eol", "auto-props-ignore-case",
          ])
    except getopt.GetoptError, e:
      Log().error('%s: %s\n\n' % (error_prefix, e))
      self.usage()
      sys.exit(1)

    # First look for any 'help'-type options, as they just cause the
    # program to print help and ignore any other options:
    self.process_help_options()

    # Next look for any --options options, process them, and remove
    # them from the list, as they affect the processing of other
    # options:
    options_file_found = False
    for (opt, value) in self.get_options('--options'):
      self.process_options_file(value)
      options_file_found = True

    # Now process options that can be used either with or without
    # --options:
    self.process_common_options()

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
    self.project_symbol_strategy_rules.append(list(symbol_strategy_rules))

  def clear_projects(self):
    """Clear the list of projects to be converted.

    This method is for the convenience of options files, which may
    want to import one another."""

    del self.projects[:]
    del self.project_symbol_strategy_rules[:]

  def process_help_options(self):
    """Process any help-type options."""

    if self.get_options('-h', '--help'):
      self.usage()
      sys.exit(0)
    elif self.get_options('--help-passes'):
      self.pass_manager.help_passes()
      sys.exit(0)
    elif self.get_options('--version'):
      print '%s version %s' % (os.path.basename(self.progname), VERSION)
      sys.exit(0)

  def process_common_options(self):
    """Process the options that are compatible with --options."""

    # Adjust level of verbosity:
    for (opt, value) in self.get_options('--verbose', '-v'):
      Log().increase_verbosity()

    for (opt, value) in self.get_options('--quiet', '-q'):
      Log().decrease_verbosity()

    for (opt, value) in self.get_options('--pass', '--passes', '-p'):
      if value.find(':') >= 0:
        start_pass, end_pass = value.split(':')
        self.start_pass = self.pass_manager.get_pass_number(
            start_pass, 1)
        self.end_pass = self.pass_manager.get_pass_number(
            end_pass, self.pass_manager.num_passes)
      else:
        self.end_pass = \
            self.start_pass = \
            self.pass_manager.get_pass_number(value)

    if self.get_options('--dry-run'):
      Ctx().dry_run = True

    if self.get_options('--profile'):
      self.profiling = True

  def process_remaining_options(self):
    """Process the options that are not compatible with --options."""

    # Convenience var, so we don't have to keep instantiating this Borg.
    ctx = Ctx()

    target = None
    existing_svnrepos = False
    fs_type = None
    bdb_txn_nosync = False
    dump_only = False
    dumpfile = None
    use_rcs = False
    use_cvs = False
    use_internal_co = False
    symbol_strategy_default = 'heuristic'
    mime_types_file = None
    auto_props_file = None
    auto_props_ignore_case = True
    eol_from_mime_type = False
    default_eol = None
    keywords_off = False
    co_executable = config.CO_EXECUTABLE
    cvs_executable = config.CVS_EXECUTABLE
    trunk_base = config.DEFAULT_TRUNK_BASE
    branches_base = config.DEFAULT_BRANCHES_BASE
    tags_base = config.DEFAULT_TAGS_BASE
    encodings = ['ascii']
    fallback_encoding = None
    force_branch = False
    force_tag = False
    symbol_transforms = []
    symbol_strategy_rules = []

    for opt, value in self.opts:
      if opt  in ['-s', '--svnrepos']:
        target = value
      elif opt == '--existing-svnrepos':
        existing_svnrepos = True
      elif opt == '--dumpfile':
        dumpfile = value
      elif opt == '--use-rcs':
        use_rcs = True
      elif opt == '--use-cvs':
        use_cvs = True
      elif opt == '--use-internal-co':
        use_internal_co = True
      elif opt == '--trunk-only':
        ctx.trunk_only = True
      elif opt == '--trunk':
        trunk_base = value
      elif opt == '--branches':
        branches_base = value
      elif opt == '--tags':
        tags_base = value
      elif opt == '--no-prune':
        ctx.prune = False
      elif opt == '--encoding':
        encodings.insert(-1, value)
      elif opt == '--fallback-encoding':
        fallback_encoding = value
      elif opt == '--symbol-hints':
        symbol_strategy_rules.append(SymbolHintsFileRule(value))
      elif opt == '--force-branch':
        symbol_strategy_rules.append(ForceBranchRegexpStrategyRule(value))
        force_branch = True
      elif opt == '--force-tag':
        symbol_strategy_rules.append(ForceTagRegexpStrategyRule(value))
        force_tag = True
      elif opt == '--exclude':
        symbol_strategy_rules.append(ExcludeRegexpStrategyRule(value))
      elif opt == '--symbol-default':
        if value not in ['branch', 'tag', 'heuristic', 'strict']:
          raise FatalError(
              '%r is not a valid option for --symbol_default.' % (value,))
        symbol_strategy_default = value
      elif opt == '--no-cross-branch-commits':
        ctx.cross_branch_commits = False
      elif opt == '--retain-conflicting-attic-files':
        ctx.retain_conflicting_attic_files = True
      elif opt == '--symbol-transform':
        [pattern, replacement] = value.split(":")
        try:
          symbol_transforms.append(
              RegexpSymbolTransform(pattern, replacement))
        except re.error:
          raise FatalError("'%s' is not a valid regexp." % (pattern,))
      elif opt == '--username':
        ctx.username = value
      elif opt == '--fs-type':
        fs_type = value
      elif opt == '--bdb-txn-nosync':
        bdb_txn_nosync = True
      elif opt == '--cvs-revnums':
        ctx.svn_property_setters.append(CVSRevisionNumberSetter())
      elif opt == '--mime-types':
        mime_types_file = value
      elif opt == '--auto-props':
        auto_props_file = value
      elif opt == '--auto-props-ignore-case':
        # "ignore case" is now the default, so this option doesn't
        # affect anything.
        auto_props_ignore_case = True
      elif opt == '--eol-from-mime-type':
        eol_from_mime_type = True
      elif opt == '--default-eol':
        try:
          # Check that value is valid, and translate it to the proper case
          default_eol = {
              'binary' : None, 'native' : 'native',
              'crlf' : 'CRLF', 'lf' : 'LF', 'cr' : 'CR',
              }[value.lower()]
        except KeyError:
          raise FatalError(
              'Illegal value specified for --default-eol: %s' % (value,)
              )
      elif opt == '--no-default-eol':
        # For backwards compatibility:
        default_eol = None
      elif opt == '--keywords-off':
        keywords_off = True
      elif opt == '--tmpdir':
        ctx.tmpdir = value
      elif opt == '--write-symbol-info':
        ctx.symbol_info_filename = value
      elif opt == '--skip-cleanup':
        ctx.skip_cleanup = True
      elif opt == '--svnadmin':
        ctx.svnadmin_executable = value
      elif opt == '--co':
        co_executable = value
      elif opt == '--cvs':
        cvs_executable = value
      elif opt == '--sort':
        ctx.sort_executable = value
      elif opt == '--dump-only':
        dump_only = True
        Log().error(
            warning_prefix +
            ': The --dump-only option is deprecated (it is implied\n'
            'by --dumpfile).\n'
            )
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

    if dump_only and not dumpfile:
      raise FatalError("'--dump-only' requires '--dumpfile' to be specified.")

    if (not target) and (not dumpfile) and (not ctx.dry_run):
      raise FatalError("must pass one of '-s' or '--dumpfile'.")

    def not_both(opt1val, opt1name, opt2val, opt2name):
      if opt1val and opt2val:
        raise FatalError("cannot pass both '%s' and '%s'."
                         % (opt1name, opt2name,))

    not_both(target, '-s',
             dumpfile, '--dumpfile')

    not_both(dumpfile, '--dumpfile',
             existing_svnrepos, '--existing-svnrepos')

    not_both(bdb_txn_nosync, '--bdb-txn-nosync',
             existing_svnrepos, '--existing-svnrepos')

    not_both(dumpfile, '--dumpfile',
             bdb_txn_nosync, '--bdb-txn-nosync')

    not_both(fs_type, '--fs-type',
             existing_svnrepos, '--existing-svnrepos')

    not_both(use_rcs, '--use-rcs',
             use_cvs, '--use-cvs')

    not_both(use_rcs, '--use-rcs',
             use_internal_co, '--use-internal-co')

    not_both(use_cvs, '--use-cvs',
             use_internal_co, '--use-internal-co')

    not_both(ctx.trunk_only, '--trunk-only',
             force_branch, '--force-branch')

    not_both(ctx.trunk_only, '--trunk-only',
             force_tag, '--force-tag')

    if fs_type and fs_type != 'bdb' and bdb_txn_nosync:
      raise FatalError("cannot pass --bdb-txn-nosync with --fs-type=%s."
                       % fs_type)

    if target:
      if existing_svnrepos:
        ctx.output_option = ExistingRepositoryOutputOption(target)
      else:
        ctx.output_option = NewRepositoryOutputOption(
            target, fs_type=fs_type, bdb_txn_nosync=bdb_txn_nosync)
    else:
      ctx.output_option = DumpfileOutputOption(dumpfile)

    if use_rcs:
      ctx.revision_recorder = NullRevisionRecorder()
      ctx.revision_excluder = NullRevisionExcluder()
      ctx.revision_reader = RCSRevisionReader(co_executable)
    elif use_cvs:
      ctx.revision_recorder = NullRevisionRecorder()
      ctx.revision_excluder = NullRevisionExcluder()
      ctx.revision_reader = CVSRevisionReader(cvs_executable)
    else:
      # --use-internal-co is the default:
      ctx.revision_recorder = InternalRevisionRecorder(compress=True)
      ctx.revision_excluder = InternalRevisionExcluder()
      ctx.revision_reader = InternalRevisionReader(compress=True)

    try:
      ctx.cvs_author_decoder = CVSTextDecoder(encodings, fallback_encoding)
      ctx.cvs_log_decoder = CVSTextDecoder(encodings, fallback_encoding)
      # Don't use fallback_encoding for filenames:
      ctx.cvs_filename_decoder = CVSTextDecoder(encodings)
    except LookupError, e:
      raise FatalError(str(e))

    # Add the standard symbol name cleanup rules:
    symbol_transforms.extend([
        ReplaceSubstringsSymbolTransform('\\','/'),
        # Remove leading, trailing, and repeated slashes:
        NormalizePathsSymbolTransform(),
        ])

    symbol_strategy_rules.append(UnambiguousUsageRule())
    if symbol_strategy_default == 'strict':
      pass
    elif symbol_strategy_default == 'branch':
      symbol_strategy_rules.append(AllBranchRule())
    elif symbol_strategy_default == 'tag':
      symbol_strategy_rules.append(AllTagRule())
    elif symbol_strategy_default == 'heuristic':
      symbol_strategy_rules.append(BranchIfCommitsRule())
      symbol_strategy_rules.append(HeuristicStrategyRule())
    else:
      assert False

    # Now add a rule whose job it is to pick the preferred parents of
    # branches and tags:
    symbol_strategy_rules.append(HeuristicPreferredParentRule())

    if auto_props_file:
      ctx.svn_property_setters.append(AutoPropsPropertySetter(
          auto_props_file, auto_props_ignore_case))

    if mime_types_file:
      ctx.svn_property_setters.append(MimeMapper(mime_types_file))

    ctx.svn_property_setters.append(CVSBinaryFileEOLStyleSetter())

    ctx.svn_property_setters.append(CVSBinaryFileDefaultMimeTypeSetter())

    if eol_from_mime_type:
      ctx.svn_property_setters.append(EOLStyleFromMimeTypeSetter())

    ctx.svn_property_setters.append(DefaultEOLStyleSetter(default_eol))

    ctx.svn_property_setters.append(SVNBinaryFileKeywordsPropertySetter())

    if not keywords_off:
      ctx.svn_property_setters.append(
          KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE))

    ctx.svn_property_setters.append(ExecutablePropertySetter())

    # Create the default project (using ctx.trunk, ctx.branches, and
    # ctx.tags):
    self.add_project(
        cvsroot,
        trunk_path=trunk_base,
        branches_path=branches_base,
        tags_path=tags_base,
        symbol_transforms=symbol_transforms,
        symbol_strategy_rules=symbol_strategy_rules,
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

    if self.opts or self.args:
      if self.opts:
        Log().error(
            '%s: The following options cannot be used in combination with '
            'the --options\n'
            'option:\n'
            '    %s\n'
            % (
                error_prefix,
                '\n    '.join([opt for (opt,value) in self.opts])
                )
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
    Log().write(usage_message_template % {
        'progname' : self.progname,
        'trunk_base' : config.DEFAULT_TRUNK_BASE,
        'branches_base' : config.DEFAULT_BRANCHES_BASE,
        'tags_base' : config.DEFAULT_TAGS_BASE,
        'svn_keywords_value' : config.SVN_KEYWORDS_VALUE,
        })


