# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
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
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.output_option import DumpfileOutputOption
from cvs2svn_lib.output_option import NewRepositoryOutputOption
from cvs2svn_lib.output_option import ExistingRepositoryOutputOption
from cvs2svn_lib.project import Project
from cvs2svn_lib.pass_manager import InvalidPassError
from cvs2svn_lib.revision_reader import RCSRevisionReader
from cvs2svn_lib.revision_reader import CVSRevisionReader
from cvs2svn_lib.symbol_strategy import AllBranchRule
from cvs2svn_lib.symbol_strategy import AllTagRule
from cvs2svn_lib.symbol_strategy import BranchIfCommitsRule
from cvs2svn_lib.symbol_strategy import ExcludeRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceBranchRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceTagRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import HeuristicStrategyRule
from cvs2svn_lib.symbol_strategy import RuleBasedSymbolStrategy
from cvs2svn_lib.symbol_strategy import UnambiguousUsageRule
from cvs2svn_lib.symbol_transform import RegexpSymbolTransform
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
USAGE: %(progname)s [-v] [-s svn-repos-path] [-p pass] cvs-repos-path
  --help, -h           print this usage message and exit with success
  --help-passes        list the available passes and their numbers
  --version            print the version number
  --verbose, -v        verbose
  --quiet, -q          quiet
  --options=PATH       read the conversion options from the specified path
  -s PATH              path for SVN repos
  -p PASS              execute only specified PASS
  -p [START]:[END]     execute passes START through END, inclusive
                       (PASS, START, and END can be pass names or numbers)
  --existing-svnrepos  load into existing SVN repository
  --dumpfile=PATH      just produce a dumpfile; don't commit to a repos
  --dry-run            do not create a repository or a dumpfile;
                       just print what would happen.
  --use-cvs            use CVS instead of RCS 'co' to extract data
                       (only use this if having problems with RCS)
  --trunk-only         convert only trunk commits, not tags nor branches
  --trunk=PATH         path for trunk (default: %(trunk_base)s)
  --branches=PATH      path for branches (default: %(branches_base)s)
  --tags=PATH          path for tags (default: %(tags_base)s)
  --no-prune           don't prune empty directories
  --encoding=ENC       encoding for paths and log messages in CVS repos.
                       If option is specified multiple times, the encoders
                       will be tried in order until one succeeds.
  --fallback-encoding=ENC If all --encodings fail, use lossy encoding with ENC
  --force-branch=REGEXP force symbols matching REGEXP to be branches
  --force-tag=REGEXP   force symbols matching REGEXP to be tags
  --exclude=REGEXP     exclude branches and tags matching REGEXP
  --symbol-default=OPT choose how ambiguous symbols are converted.  OPT is
                       "branch", "tag", or "heuristic", or "strict" (default)
  --no-cross-branch-commits Prevent the creation of cross-branch commits
  --retain-conflicting-attic-files if a file appears both in and out of the
                       CVS Attic, then leave the attic version in a SVN
                       directory called "Attic".
  --symbol-transform=P:S transform symbol names from P to S where P and S
                       use Python regexp and reference syntax respectively
  --username=NAME      username for cvs2svn-synthesized commits
  --fs-type=TYPE       pass --fs-type=TYPE to "svnadmin create"
  --bdb-txn-nosync     pass --bdb-txn-nosync to "svnadmin create"
  --cvs-revnums        record CVS revision numbers as file properties
  --mime-types=FILE    specify an apache-style mime.types file for
                       setting svn:mime-type
  --auto-props=FILE    set file properties from the auto-props section
                       of a file in svn config format
  --auto-props-ignore-case Ignore case when matching auto-props patterns
  --eol-from-mime-type set svn:eol-style from mime type if known
  --no-default-eol     don't set svn:eol-style to 'native' for
                       non-binary files with undetermined mime types
  --keywords-off       don't set svn:keywords on any files (by default,
                       cvs2svn sets svn:keywords on non-binary files to
                       "%(svn_keywords_value)s")
  --tmpdir=PATH        directory to use for tmp data (default to cwd)
  --skip-cleanup       prevent the deletion of intermediate files
  --profile            profile with 'hotshot' (into file cvs2svn.hotshot)
  --svnadmin=PATH      path to the "svnadmin" program
  --co=PATH            path to the "co" program (required if not --use-cvs)
  --cvs=PATH           path to the "cvs" program (required if --use-cvs)
  --sort=PATH          path to the GNU "sort" program
"""

def usage(progname):
  sys.stdout.write(usage_message_template % {
      'progname' : progname,
      'trunk_base' : config.DEFAULT_TRUNK_BASE,
      'branches_base' : config.DEFAULT_BRANCHES_BASE,
      'tags_base' : config.DEFAULT_TAGS_BASE,
      'svn_keywords_value' : config.SVN_KEYWORDS_VALUE,
      })


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

    try:
      self.opts, self.args = my_getopt(cmd_args, 'hvqs:p:', [
          "help", "help-passes", "version",
          "verbose", "quiet",
          "existing-svnrepos", "dumpfile=", "dry-run",
          "use-cvs",
          "trunk-only",
          "trunk=", "branches=", "tags=",
          "no-prune",
          "encoding=", "fallback-encoding=",
          "force-branch=", "force-tag=", "exclude=", "symbol-default=",
          "no-cross-branch-commits",
          "retain-conflicting-attic-files",
          "symbol-transform=",
          "username=",
          "fs-type=", "bdb-txn-nosync",
          "cvs-revnums",
          "mime-types=",
          "auto-props=", "auto-props-ignore-case",
          "eol-from-mime-type", "no-default-eol",
          "keywords-off",
          "tmpdir=",
          "skip-cleanup",
          "profile",
          "svnadmin=", "co=", "cvs=", "sort=",
          "dump-only", "create",
          "options=",
          ])
    except getopt.GetoptError, e:
      sys.stderr.write(error_prefix + ': ' + str(e) + '\n\n')
      usage(self.progname)
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

  def process_help_options(self):
    """Process any help-type options."""

    if self.get_options('-h', '--help'):
      usage(self.progname)
      sys.exit(0)
    elif self.get_options('--help-passes'):
      self.pass_manager.help_passes()
      sys.exit(0)
    elif self.get_options('--version'):
      print '%s version %s' % (os.path.basename(self.progname), Ctx().VERSION)
      sys.exit(0)

  def process_common_options(self):
    """Process the options that are compatible with --options."""

    # Adjust level of verbosity:
    for (opt, value) in self.get_options('--verbose', '-v'):
      Log().increase_verbosity()

    for (opt, value) in self.get_options('--quiet', '-q'):
      Log().decrease_verbosity()

    for (opt, value) in self.get_options('-p'):
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
    use_cvs = False
    symbol_strategy_default = 'strict'
    mime_types_file = None
    auto_props_file = None
    auto_props_ignore_case = False
    eol_from_mime_type = False
    no_default_eol = False
    keywords_off = False
    co_executable = config.CO_EXECUTABLE
    cvs_executable = config.CVS_EXECUTABLE
    trunk_base = config.DEFAULT_TRUNK_BASE
    branches_base = config.DEFAULT_BRANCHES_BASE
    tags_base = config.DEFAULT_TAGS_BASE
    symbol_transforms = []

    ctx.symbol_strategy = RuleBasedSymbolStrategy()

    for opt, value in self.opts:
      if opt == '-s':
        target = value
      elif opt == '--existing-svnrepos':
        existing_svnrepos = True
      elif opt == '--dumpfile':
        dumpfile = value
      elif opt == '--use-cvs':
        use_cvs = True
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
        ctx.encoding.insert(-1, value)
      elif opt == '--fallback-encoding':
        ctx.fallback_encoding = value
      elif opt == '--force-branch':
        ctx.symbol_strategy.add_rule(ForceBranchRegexpStrategyRule(value))
      elif opt == '--force-tag':
        ctx.symbol_strategy.add_rule(ForceTagRegexpStrategyRule(value))
      elif opt == '--exclude':
        ctx.symbol_strategy.add_rule(ExcludeRegexpStrategyRule(value))
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
        auto_props_ignore_case = True
      elif opt == '--eol-from-mime-type':
        eol_from_mime_type = True
      elif opt == '--no-default-eol':
        no_default_eol = True
      elif opt == '--keywords-off':
        keywords_off = True
      elif opt == '--tmpdir':
        ctx.tmpdir = value
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
        sys.stderr.write(warning_prefix +
            ': The --dump-only option is deprecated (it is implied\n'
            'by --dumpfile).\n')
      elif opt == '--create':
        sys.stderr.write(warning_prefix +
            ': The behaviour produced by the --create option is now the '
            'default,\nand passing the option is deprecated.\n')

    # Consistency check for options and arguments.
    if len(self.args) == 0:
      usage(self.progname)
      sys.exit(1)

    if len(self.args) > 1:
      sys.stderr.write(error_prefix +
                       ": must pass only one CVS repository.\n")
      usage(self.progname)
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

    if use_cvs:
      ctx.revision_reader = CVSRevisionReader(cvs_executable)
    else:
      ctx.revision_reader = RCSRevisionReader(co_executable)

    # Create the default project (using ctx.trunk, ctx.branches, and
    # ctx.tags):
    ctx.add_project(Project(
        cvsroot, trunk_base, branches_base, tags_base,
        symbol_transforms=symbol_transforms))

    ctx.symbol_strategy.add_rule(UnambiguousUsageRule())
    if symbol_strategy_default == 'strict':
      pass
    elif symbol_strategy_default == 'branch':
      ctx.symbol_strategy.add_rule(AllBranchRule())
    elif symbol_strategy_default == 'tag':
      ctx.symbol_strategy.add_rule(AllTagRule())
    elif symbol_strategy_default == 'heuristic':
      ctx.symbol_strategy.add_rule(BranchIfCommitsRule())
      ctx.symbol_strategy.add_rule(HeuristicStrategyRule())
    else:
      assert False

    if auto_props_file:
      ctx.svn_property_setters.append(AutoPropsPropertySetter(
          auto_props_file, auto_props_ignore_case))

    if mime_types_file:
      ctx.svn_property_setters.append(MimeMapper(mime_types_file))

    ctx.svn_property_setters.append(CVSBinaryFileEOLStyleSetter())

    ctx.svn_property_setters.append(CVSBinaryFileDefaultMimeTypeSetter())

    if eol_from_mime_type:
      ctx.svn_property_setters.append(EOLStyleFromMimeTypeSetter())

    if no_default_eol:
      ctx.svn_property_setters.append(DefaultEOLStyleSetter(None))
    else:
      ctx.svn_property_setters.append(DefaultEOLStyleSetter('native'))

    ctx.svn_property_setters.append(SVNBinaryFileKeywordsPropertySetter())

    if not keywords_off:
      ctx.svn_property_setters.append(
          KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE))

    ctx.svn_property_setters.append(ExecutablePropertySetter())

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

    if not ctx.projects:
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
        sys.stderr.write(
            '%s: The following options cannot be used in combination with '
            'the --options\n'
            'option:\n'
            '    %s\n'
            % (error_prefix,
               '\n    '.join([opt for (opt,value) in self.opts])))
      if self.args:
        sys.stderr.write(
            '%s: No cvs-repos-path arguments are allowed with the --options '
            'option.\n'
            % (error_prefix,))
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


