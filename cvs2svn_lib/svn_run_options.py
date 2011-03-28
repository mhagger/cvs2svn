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

"""This module manages cvs2svn run options."""


import sys
import optparse

from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import normalize_svn_path
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.project import Project
from cvs2svn_lib.svn_output_option import DumpfileOutputOption
from cvs2svn_lib.svn_output_option import ExistingRepositoryOutputOption
from cvs2svn_lib.svn_output_option import NewRepositoryOutputOption
from cvs2svn_lib.symbol_strategy import TrunkPathRule
from cvs2svn_lib.symbol_strategy import BranchesPathRule
from cvs2svn_lib.symbol_strategy import TagsPathRule
from cvs2svn_lib.property_setters import FilePropertySetter


class SVNEOLFixPropertySetter(FilePropertySetter):
  """Set _eol_fix property.

  This keyword is used to tell the RevisionReader how to munge EOLs
  when generating the fulltext, based on how svn:eol-style is set.  If
  svn:eol-style is not set, it does _eol_style to None, thereby
  disabling any EOL munging."""

  # A mapping from the value of the svn:eol-style property to the EOL
  # string that should appear in a dumpfile:
  EOL_REPLACEMENTS = {
      'LF' : '\n',
      'CR' : '\r',
      'CRLF' : '\r\n',
      'native' : '\n',
      }

  def set_properties(self, cvs_file):
    # Fix EOLs if necessary:
    eol_style = cvs_file.properties.get('svn:eol-style', None)
    if eol_style:
      self.maybe_set_property(
          cvs_file, '_eol_fix', self.EOL_REPLACEMENTS[eol_style]
          )
    else:
      self.maybe_set_property(
          cvs_file, '_eol_fix', None
          )


class SVNKeywordHandlingPropertySetter(FilePropertySetter):
  """Set _keyword_handling property based on the file mode and svn:keywords.

  This setting tells the RevisionReader that it has to collapse RCS
  keywords when generating the fulltext."""

  def set_properties(self, cvs_file):
    if cvs_file.mode == 'b' or cvs_file.mode == 'o':
      # Leave keywords in the form that they were checked in.
      value = 'untouched'
    elif cvs_file.mode == 'k':
      # This mode causes CVS to collapse keywords on checkout, so we
      # do the same:
      value = 'collapsed'
    elif cvs_file.properties.get('svn:keywords'):
      # Subversion is going to expand the keywords, so they have to be
      # collapsed in the dumpfile:
      value = 'collapsed'
    else:
      # CVS expands keywords, so we will too.
      value = 'expanded'

    self.maybe_set_property(cvs_file, '_keyword_handling', value)


class SVNRunOptions(RunOptions):
  short_desc = 'convert a CVS repository into a Subversion repository'

  synopsis = """\
.B cvs2svn
[\\fIOPTION\\fR]... \\fIOUTPUT-OPTION CVS-REPOS-PATH\\fR
.br
.B cvs2svn
[\\fIOPTION\\fR]... \\fI--options=PATH\\fR
"""

  long_desc = """\
Create a new Subversion repository based on the version history stored in a
CVS repository. Each CVS commit will be mirrored in the Subversion
repository, including such information as date of commit and id of the
committer.
.P
\\fICVS-REPOS-PATH\\fR is the filesystem path of the part of the CVS
repository that you want to convert.  It is not possible to convert a
CVS repository to which you only have remote access; see the FAQ for
more information.  This path doesn't have to be the top level
directory of a CVS repository; it can point at a project within a
repository, in which case only that project will be converted.  This
path or one of its parent directories has to contain a subdirectory
called CVSROOT (though the CVSROOT directory can be empty).
.P
Multiple CVS repositories can be converted into a single Subversion
repository in a single run of cvs2svn, but only by using an
\\fB--options\\fR file.
"""

  files = """\
A directory called \\fIcvs2svn-tmp\\fR (or the directory specified by
\\fB--tmpdir\\fR) is used as scratch space for temporary data files.
"""

  see_also = [
    ('cvs', '1'),
    ('svn', '1'),
    ('svnadmin', '1'),
    ]

  def _get_output_options_group(self):
    group = super(SVNRunOptions, self)._get_output_options_group()

    group.add_option(IncompatibleOption(
        '--svnrepos', '-s', type='string',
        action='store',
        help='path where SVN repos should be created',
        man_help=(
            'Write the output of the conversion into a Subversion repository '
            'located at \\fIpath\\fR.  This option causes a new Subversion '
            'repository to be created at \\fIpath\\fR unless the '
            '\\fB--existing-svnrepos\\fR option is also used.'
            ),
        metavar='PATH',
        ))
    self.parser.set_default('existing_svnrepos', False)
    group.add_option(IncompatibleOption(
        '--existing-svnrepos',
        action='store_true',
        help='load into existing SVN repository (for use with --svnrepos)',
        man_help=(
            'Load the converted CVS repository into an existing Subversion '
            'repository, instead of creating a new repository.  (This option '
            'should be used in combination with '
            '\\fB-s\\fR/\\fB--svnrepos\\fR.)  The repository must either be '
            'empty or contain no paths that overlap with those that will '
            'result from the conversion.  Please note that you need write '
            'permission for the repository files.'
            ),
        ))
    group.add_option(IncompatibleOption(
        '--fs-type', type='string',
        action='store',
        help=(
            'pass --fs-type=TYPE to "svnadmin create" (for use with '
            '--svnrepos)'
            ),
        man_help=(
            'Pass \\fI--fs-type\\fR=\\fItype\\fR to "svnadmin create" when '
            'creating a new repository.'
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
        man_help=(
            'Pass \\fI--bdb-txn-nosync\\fR to "svnadmin create" when '
            'creating a new BDB-style Subversion repository.'
            ),
        ))
    self.parser.set_default('create_options', [])
    group.add_option(IncompatibleOption(
        '--create-option', type='string',
        action='append', dest='create_options',
        help='pass OPT to "svnadmin create" (for use with --svnrepos)',
        man_help=(
            'Pass \\fIopt\\fR to "svnadmin create" when creating a new '
            'Subversion repository (can be specified multiple times to '
            'pass multiple options).'
            ),
        metavar='OPT',
        ))
    group.add_option(IncompatibleOption(
        '--dumpfile', type='string',
        action='store',
        help='just produce a dumpfile; don\'t commit to a repos',
        man_help=(
            'Just produce a dumpfile; don\'t commit to an SVN repository. '
            'Write the dumpfile to \\fIpath\\fR.'
            ),
        metavar='PATH',
        ))

    group.add_option(ContextOption(
        '--dry-run',
        action='store_true',
        help=(
            'do not create a repository or a dumpfile; just print what '
            'would happen.'
            ),
        man_help=(
            'Do not create a repository or a dumpfile; just print the '
            'details of what cvs2svn would do if it were really converting '
            'your repository.'
            ),
        ))

    # Deprecated options:
    self.parser.set_default('dump_only', False)
    group.add_option(IncompatibleOption(
        '--dump-only',
        action='callback', callback=self.callback_dump_only,
        help=optparse.SUPPRESS_HELP,
        man_help=optparse.SUPPRESS_HELP,
        ))
    group.add_option(IncompatibleOption(
        '--create',
        action='callback', callback=self.callback_create,
        help=optparse.SUPPRESS_HELP,
        man_help=optparse.SUPPRESS_HELP,
        ))

    return group

  def _get_conversion_options_group(self):
    group = super(SVNRunOptions, self)._get_conversion_options_group()

    self.parser.set_default('trunk_base', config.DEFAULT_TRUNK_BASE)
    group.add_option(IncompatibleOption(
        '--trunk', type='string',
        action='store', dest='trunk_base',
        help=(
            'path for trunk (default: %s)'
            % (config.DEFAULT_TRUNK_BASE,)
            ),
        man_help=(
            'Set the top-level path to use for trunk in the Subversion '
            'repository. The default is \\fI%s\\fR.'
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
        man_help=(
            'Set the top-level path to use for branches in the Subversion '
            'repository.  The default is \\fI%s\\fR.'
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
        man_help=(
            'Set the top-level path to use for tags in the Subversion '
            'repository. The default is \\fI%s\\fR.'
            % (config.DEFAULT_TAGS_BASE,)
            ),
        metavar='PATH',
        ))
    group.add_option(ContextOption(
        '--include-empty-directories',
        action='store_true', dest='include_empty_directories',
        help=(
            'include empty directories within the CVS repository '
            'in the conversion'
            ),
        man_help=(
            'Treat empty subdirectories within the CVS repository as actual '
            'directories, creating them when the parent directory is created '
            'and removing them if and when the parent directory is pruned.'
            ),
        ))
    group.add_option(ContextOption(
        '--no-prune',
        action='store_false', dest='prune',
        help='don\'t prune empty directories',
        man_help=(
            'When all files are deleted from a directory in the Subversion '
            'repository, don\'t delete the empty directory (the default is '
            'to delete any empty directories).'
            ),
        ))
    group.add_option(ContextOption(
        '--no-cross-branch-commits',
        action='store_false', dest='cross_branch_commits',
        help='prevent the creation of cross-branch commits',
        man_help=(
            'Prevent the creation of commits that affect files on multiple '
            'branches at once.'
            ),
        ))

    return group

  def _get_extraction_options_group(self):
    group = super(SVNRunOptions, self)._get_extraction_options_group()
    self._add_use_internal_co_option(group)
    self._add_use_cvs_option(group)
    self._add_use_rcs_option(group)
    return group

  def _get_environment_options_group(self):
    group = super(SVNRunOptions, self)._get_environment_options_group()

    group.add_option(ContextOption(
        '--svnadmin', type='string',
        action='store', dest='svnadmin_executable',
        help='path to the "svnadmin" program',
        man_help=(
            'Path to the \\fIsvnadmin\\fR program.  (\\fIsvnadmin\\fR is '
            'needed when the \\fB-s\\fR/\\fB--svnrepos\\fR output option is '
            'used.)'
            ),
        metavar='PATH',
        compatible_with_option=True,
        ))

    return group

  def callback_dump_only(self, option, opt_str, value, parser):
    parser.values.dump_only = True
    logger.error(
        warning_prefix +
        ': The --dump-only option is deprecated (it is implied '
        'by --dumpfile).\n'
        )

  def callback_create(self, option, opt_str, value, parser):
    logger.error(
        warning_prefix +
        ': The behaviour produced by the --create option is now the '
        'default;\n'
        'passing the option is deprecated.\n'
        )

  def process_extraction_options(self):
    """Process options related to extracting data from the CVS repository."""
    self.process_all_extraction_options()

  def process_output_options(self):
    """Process the options related to SVN output."""

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

  def add_project(
        self,
        project_cvs_repos_path,
        trunk_path=None, branches_path=None, tags_path=None,
        initial_directories=[],
        symbol_transforms=None,
        symbol_strategy_rules=[],
        exclude_paths=[],
        ):
    """Add a project to be converted.

    Most arguments are passed straight through to the Project
    constructor.  SYMBOL_STRATEGY_RULES is an iterable of
    SymbolStrategyRules that will be applied to symbols in this
    project."""

    if trunk_path is not None:
      trunk_path = normalize_svn_path(trunk_path, allow_empty=True)
    if branches_path is not None:
      branches_path = normalize_svn_path(branches_path, allow_empty=False)
    if tags_path is not None:
      tags_path = normalize_svn_path(tags_path, allow_empty=False)

    initial_directories = [
        path
        for path in [trunk_path, branches_path, tags_path]
        if path
        ] + [
        normalize_svn_path(path)
        for path in initial_directories
        ]

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
        exclude_paths=exclude_paths,
        )

    self.projects.append(project)
    self.project_symbol_strategy_rules.append(symbol_strategy_rules)

  def clear_projects(self):
    """Clear the list of projects to be converted.

    This method is for the convenience of options files, which may
    want to import one another."""

    del self.projects[:]
    del self.project_symbol_strategy_rules[:]

  def process_property_setter_options(self):
    super(SVNRunOptions, self).process_property_setter_options()

    # Property setters for internal use:
    Ctx().file_property_setters.append(SVNEOLFixPropertySetter())
    Ctx().file_property_setters.append(SVNKeywordHandlingPropertySetter())

  def process_options(self):
    # Consistency check for options and arguments.
    if len(self.args) == 0:
      self.usage()
      sys.exit(1)

    if len(self.args) > 1:
      logger.error(error_prefix + ": must pass only one CVS repository.\n")
      self.usage()
      sys.exit(1)

    cvsroot = self.args[0]

    self.process_extraction_options()
    self.process_output_options()
    self.process_symbol_strategy_options()
    self.process_property_setter_options()

    # Create the default project (using ctx.trunk, ctx.branches, and
    # ctx.tags):
    self.add_project(
        cvsroot,
        trunk_path=self.options.trunk_base,
        branches_path=self.options.branches_base,
        tags_path=self.options.tags_base,
        symbol_transforms=self.options.symbol_transforms,
        symbol_strategy_rules=self.options.symbol_strategy_rules,
        )


