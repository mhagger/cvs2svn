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

"""This module contains classes to set common cvs2xxx run options."""

import sys
import re
import optparse
from optparse import OptionGroup
import datetime
import codecs
import time

from cvs2svn_lib.version import VERSION
from cvs2svn_lib import config
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.man_writer import ManWriter
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.man_writer import ManOption
from cvs2svn_lib.pass_manager import InvalidPassError
from cvs2svn_lib.revision_manager import NullRevisionCollector
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.checkout_internal import InternalRevisionCollector
from cvs2svn_lib.checkout_internal import InternalRevisionReader
from cvs2svn_lib.symbol_strategy import AllBranchRule
from cvs2svn_lib.symbol_strategy import AllExcludedRule
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
from cvs2svn_lib.property_setters import DescriptionPropertySetter
from cvs2svn_lib.property_setters import KeywordsPropertySetter
from cvs2svn_lib.property_setters import MimeMapper
from cvs2svn_lib.property_setters import SVNBinaryFileKeywordsPropertySetter


usage = """\
Usage: %prog --options OPTIONFILE
       %prog [OPTION...] OUTPUT-OPTION CVS-REPOS-PATH"""

description="""\
Convert a CVS repository into a Subversion repository, including history.
"""


class IncompatibleOption(ManOption):
  """A ManOption that is incompatible with the --options option.

  Record that the option was used so that error checking can later be
  done."""

  def __init__(self, *args, **kw):
    ManOption.__init__(self, *args, **kw)

  def take_action(self, action, dest, opt, value, values, parser):
    oio = parser.values.options_incompatible_options
    if opt not in oio:
      oio.append(opt)
    return ManOption.take_action(
        self, action, dest, opt, value, values, parser
        )


class ContextOption(ManOption):
  """A ManOption that stores its value to Ctx."""

  def __init__(self, *args, **kw):
    if kw.get('action') not in self.STORE_ACTIONS:
      raise ValueError('Invalid action: %s' % (kw['action'],))

    self.__compatible_with_option = kw.pop('compatible_with_option', False)
    self.__action = kw.pop('action')
    try:
      self.__dest = kw.pop('dest')
    except KeyError:
      opt = args[0]
      if not opt.startswith('--'):
        raise ValueError()
      self.__dest = opt[2:].replace('-', '_')
    if 'const' in kw:
      self.__const = kw.pop('const')

    kw['action'] = 'callback'
    kw['callback'] = self.__callback

    ManOption.__init__(self, *args, **kw)

  def __callback(self, option, opt_str, value, parser):
    if not self.__compatible_with_option:
      oio = parser.values.options_incompatible_options
      if opt_str not in oio:
        oio.append(opt_str)

    action = self.__action
    dest = self.__dest

    if action == "store":
        setattr(Ctx(), dest, value)
    elif action == "store_const":
        setattr(Ctx(), dest, self.__const)
    elif action == "store_true":
        setattr(Ctx(), dest, True)
    elif action == "store_false":
        setattr(Ctx(), dest, False)
    elif action == "append":
        getattr(Ctx(), dest).append(value)
    elif action == "count":
        setattr(Ctx(), dest, getattr(Ctx(), dest, 0) + 1)
    else:
        raise RuntimeError("unknown action %r" % self.__action)

    return 1


class IncompatibleOptionsException(FatalError):
  pass


# Options that are not allowed to be used with --trunk-only:
SYMBOL_OPTIONS = [
    '--symbol-transform',
    '--symbol-hints',
    '--force-branch',
    '--force-tag',
    '--exclude',
    '--keep-trivial-imports',
    '--symbol-default',
    '--no-cross-branch-commits',
    ]

class SymbolOptionsWithTrunkOnlyException(IncompatibleOptionsException):
  def __init__(self):
    IncompatibleOptionsException.__init__(
        self,
        'The following symbol-related options cannot be used together\n'
        'with --trunk-only:\n'
        '    %s'
        % ('\n    '.join(SYMBOL_OPTIONS),)
        )


def not_both(opt1val, opt1name, opt2val, opt2name):
  """Raise an exception if both opt1val and opt2val are set."""
  if opt1val and opt2val:
    raise IncompatibleOptionsException(
        "cannot pass both '%s' and '%s'." % (opt1name, opt2name,)
        )


class RunOptions(object):
  """A place to store meta-options that are used to start the conversion."""

  # Components of the man page.  Attributes set to None here must be set
  # by subclasses; others may be overridden/augmented by subclasses if
  # they wish.
  short_desc = None
  synopsis = None
  long_desc = None
  files = None
  authors = [
    u"C. Michael Pilato <cmpilato@collab.net>",
    u"Greg Stein <gstein@lyra.org>",
    u"Branko \u010cibej <brane@xbc.nu>",
    u"Blair Zajac <blair@orcaware.com>",
    u"Max Bowsher <maxb@ukf.net>",
    u"Brian Fitzpatrick <fitz@red-bean.com>",
    u"Tobias Ringstr\u00f6m <tobias@ringstrom.mine.nu>",
    u"Karl Fogel <kfogel@collab.net>",
    u"Erik H\u00fclsmann <e.huelsmann@gmx.net>",
    u"David Summers <david@summersoft.fay.ar.us>",
    u"Michael Haggerty <mhagger@alum.mit.edu>",
    ]
  see_also = None

  def __init__(self, progname, cmd_args, pass_manager):
    """Process the command-line options, storing run options to SELF.

    PROGNAME is the name of the program, used in the usage string.
    CMD_ARGS is the list of command-line arguments passed to the
    program.  PASS_MANAGER is an instance of PassManager, needed to
    help process the -p and --help-passes options."""

    self.progname = progname
    self.cmd_args = cmd_args
    self.pass_manager = pass_manager
    self.start_pass = 1
    self.end_pass = self.pass_manager.num_passes
    self.profiling = False

    self.projects = []

    # A list of one list of SymbolStrategyRules for each project:
    self.project_symbol_strategy_rules = []

    parser = self.parser = optparse.OptionParser(
        usage=usage,
        description=self.get_description(),
        add_help_option=False,
        )
    # A place to record any options used that are incompatible with
    # --options:
    parser.set_default('options_incompatible_options', [])

    # Populate the options parser with the options, one group at a
    # time:
    parser.add_option_group(self._get_options_file_options_group())
    parser.add_option_group(self._get_output_options_group())
    parser.add_option_group(self._get_conversion_options_group())
    parser.add_option_group(self._get_symbol_handling_options_group())
    parser.add_option_group(self._get_subversion_properties_options_group())
    parser.add_option_group(self._get_extraction_options_group())
    parser.add_option_group(self._get_environment_options_group())
    parser.add_option_group(self._get_partial_conversion_options_group())
    parser.add_option_group(self._get_information_options_group())

    (self.options, self.args) = parser.parse_args(args=self.cmd_args)

    # Now the log level has been set; log the time when the run started:
    logger.verbose(
        time.strftime(
            'Conversion start time: %Y-%m-%d %I:%M:%S %Z',
            time.localtime(logger.start_time)
            )
        )

    if self.options.options_file_found:
      # Check that no options that are incompatible with --options
      # were used:
      self.verify_option_compatibility()
    else:
      # --options was not specified.  So do the main initialization
      # based on other command-line options:
      self.process_options()

    # Check for problems with the options:
    self.check_options()

  def get_description(self):
    return description

  def _get_options_file_options_group(self):
    group = OptionGroup(
        self.parser, 'Configuration via options file'
        )
    self.parser.set_default('options_file_found', False)
    group.add_option(ManOption(
        '--options', type='string',
        action='callback', callback=self.callback_options,
        help=(
            'read the conversion options from PATH.  This '
            'method allows more flexibility than using '
            'command-line options.  See documentation for info'
            ),
        man_help=(
            'Read the conversion options from \\fIpath\\fR instead of from '
            'the command line.  This option allows far more conversion '
            'flexibility than can be achieved using the command-line alone. '
            'See the documentation for more information.  Only the following '
            'command-line options are allowed in combination with '
            '\\fB--options\\fR: \\fB-h\\fR/\\fB--help\\fR, '
            '\\fB--help-passes\\fR, \\fB--version\\fR, '
            '\\fB-v\\fR/\\fB--verbose\\fR, \\fB-q\\fR/\\fB--quiet\\fR, '
            '\\fB-p\\fR/\\fB--pass\\fR/\\fB--passes\\fR, \\fB--dry-run\\fR, '
            '\\fB--profile\\fR, \\fB--trunk-only\\fR, \\fB--encoding\\fR, '
            'and \\fB--fallback-encoding\\fR. '
            'Options are processed in the order specified on the command '
            'line.'
            ),
        metavar='PATH',
        ))
    return group

  def _get_output_options_group(self):
    group = OptionGroup(self.parser, 'Output options')
    return group

  def _get_conversion_options_group(self):
    group = OptionGroup(self.parser, 'Conversion options')
    group.add_option(ContextOption(
        '--trunk-only',
        action='store_true',
        compatible_with_option=True,
        help='convert only trunk commits, not tags nor branches',
        man_help=(
            'Convert only trunk commits, not tags nor branches.'
            ),
        ))
    group.add_option(ManOption(
        '--encoding', type='string',
        action='callback', callback=self.callback_encoding,
        help=(
            'encoding for paths and log messages in CVS repos.  '
            'If option is specified multiple times, encoders '
            'are tried in order until one succeeds.  See '
            'http://docs.python.org/lib/standard-encodings.html '
            'for a list of standard Python encodings.'
            ),
        man_help=(
            'Use \\fIencoding\\fR as the encoding for filenames, log '
            'messages, and author names in the CVS repos.  This option '
            'may be specified multiple times, in which case the encodings '
            'are tried in order until one succeeds.  Default: ascii.  See '
            'http://docs.python.org/lib/standard-encodings.html for a list '
            'of other standard encodings.'
            ),
        metavar='ENC',
        ))
    group.add_option(ManOption(
        '--fallback-encoding', type='string',
        action='callback', callback=self.callback_fallback_encoding,
        help='If all --encodings fail, use lossy encoding with ENC',
        man_help=(
            'If none of the encodings specified with \\fB--encoding\\fR '
            'succeed in decoding an author name or log message, then fall '
            'back to using \\fIencoding\\fR in lossy \'replace\' mode. '
            'Use of this option may cause information to be lost, but at '
            'least it allows the conversion to run to completion.  This '
            'option only affects the encoding of log messages and author '
            'names; there is no fallback encoding for filenames.  (By '
            'using an \\fB--options\\fR file, it is possible to specify '
            'a fallback encoding for filenames.)  Default: disabled.'
            ),
        metavar='ENC',
        ))
    group.add_option(ContextOption(
        '--retain-conflicting-attic-files',
        action='store_true',
        help=(
            'if a file appears both in and out of '
            'the CVS Attic, then leave the attic version in a '
            'SVN directory called "Attic"'
            ),
        man_help=(
            'If a file appears both inside an outside of the CVS attic, '
            'retain the attic version in an SVN subdirectory called '
            '\'Attic\'.  (Normally this situation is treated as a fatal '
            'error.)'
            ),
        ))

    return group

  def _get_symbol_handling_options_group(self):
    group = OptionGroup(self.parser, 'Symbol handling')
    self.parser.set_default('symbol_transforms', [])
    group.add_option(IncompatibleOption(
        '--symbol-transform', type='string',
        action='callback', callback=self.callback_symbol_transform,
        help=(
            'transform symbol names from P to S, where P and S '
            'use Python regexp and reference syntax '
            'respectively.  P must match the whole symbol name'
            ),
        man_help=(
            'Transform RCS/CVS symbol names before entering them into '
            'Subversion. \\fIpattern\\fR is a Python regexp pattern that '
            'is matches against the entire symbol name; \\fIreplacement\\fR '
            'is a replacement using Python\'s regexp reference syntax. '
            'You may specify any number of these options; they will be '
            'applied in the order given on the command line.'
            ),
        metavar='P:S',
        ))
    self.parser.set_default('symbol_strategy_rules', [])
    group.add_option(IncompatibleOption(
        '--symbol-hints', type='string',
        action='callback', callback=self.callback_symbol_hints,
        help='read symbol conversion hints from PATH',
        man_help=(
            'Read symbol conversion hints from \\fIpath\\fR.  The format of '
            '\\fIpath\\fR is the same as the format output by '
            '\\fB--write-symbol-info\\fR, namely a text file with four '
            'whitespace-separated columns: \\fIproject-id\\fR, '
            '\\fIsymbol\\fR, \\fIconversion\\fR, and '
            '\\fIparent-lod-name\\fR.  \\fIproject-id\\fR is the numerical '
            'ID of the project to which the symbol belongs, counting from '
            '0. \\fIproject-id\\fR can be set to \'.\' if '
            'project-specificity is not needed.  \\fIsymbol-name\\fR is the '
            'name of the symbol being specified.  \\fIconversion\\fR '
            'specifies how the symbol should be converted, and can be one '
            'of the values \'branch\', \'tag\', or \'exclude\'. If '
            '\\fIconversion\\fR is \'.\', then this rule does not affect '
            'how the symbol is converted.  \\fIparent-lod-name\\fR is the '
            'name of the symbol from which this symbol should sprout, or '
            '\'.trunk.\' if the symbol should sprout from trunk.  If '
            '\\fIparent-lod-name\\fR is omitted or \'.\', then this rule '
            'does not affect the preferred parent of this symbol. The file '
            'may contain blank lines or comment lines (lines whose first '
            'non-whitespace character is \'#\').'
            ),
        metavar='PATH',
        ))
    self.parser.set_default('symbol_default', 'heuristic')
    group.add_option(IncompatibleOption(
        '--symbol-default', type='choice',
        choices=['heuristic', 'strict', 'branch', 'tag', 'exclude'],
        action='store',
        help=(
            'specify how ambiguous symbols are converted.  '
            'OPT is "heuristic" (default), "strict", "branch", '
            '"tag" or "exclude"'
            ),
        man_help=(
            'Specify how to convert ambiguous symbols (those that appear in '
            'the CVS archive as both branches and tags).  \\fIopt\\fR must '
            'be \'heuristic\' (decide how to treat each ambiguous symbol '
            'based on whether it was used more often as a branch/tag in '
            'CVS), \'strict\' (no default; every ambiguous symbol has to be '
            'resolved manually using \\fB--force-branch\\fR, '
            '\\fB--force-tag\\fR, or \\fB--exclude\\fR), \'branch\' (treat '
            'every ambiguous symbol as a branch), \'tag\' (treat every '
            'ambiguous symbol as a tag), or \'exclude\' (do not convert '
            'ambiguous symbols).  The default is \'heuristic\'.'
            ),
        metavar='OPT',
        ))
    group.add_option(IncompatibleOption(
        '--force-branch', type='string',
        action='callback', callback=self.callback_force_branch,
        help='force symbols matching REGEXP to be branches',
        man_help=(
            'Force symbols whose names match \\fIregexp\\fR to be branches. '
            '\\fIregexp\\fR must match the whole symbol name.'
            ),
        metavar='REGEXP',
        ))
    group.add_option(IncompatibleOption(
        '--force-tag', type='string',
        action='callback', callback=self.callback_force_tag,
        help='force symbols matching REGEXP to be tags',
        man_help=(
            'Force symbols whose names match \\fIregexp\\fR to be tags. '
            '\\fIregexp\\fR must match the whole symbol name.'
            ),
        metavar='REGEXP',
        ))
    group.add_option(IncompatibleOption(
        '--exclude', type='string',
        action='callback', callback=self.callback_exclude,
        help='exclude branches and tags matching REGEXP',
        man_help=(
            'Exclude branches and tags whose names match \\fIregexp\\fR '
            'from the conversion.  \\fIregexp\\fR must match the whole '
            'symbol name.'
            ),
        metavar='REGEXP',
        ))
    self.parser.set_default('keep_trivial_imports', False)
    group.add_option(IncompatibleOption(
        '--keep-trivial-imports',
        action='store_true',
        help=(
            'do not exclude branches that were only used for '
            'a single import (usually these are unneeded)'
            ),
        man_help=(
            'Do not exclude branches that were only used for a single '
            'import. (By default such branches are excluded because they '
            'are usually created by the inappropriate use of \\fBcvs '
            'import\\fR.)'
            ),
        ))

    return group

  def _get_subversion_properties_options_group(self):
    group = OptionGroup(self.parser, 'Subversion properties')
    group.add_option(ContextOption(
        '--username', type='string',
        action='store',
        help='username for cvs2svn-synthesized commits',
        man_help=(
            'Set the default username to \\fIname\\fR when cvs2svn needs '
            'to generate a commit for which CVS does not record the '
            'original username. This happens when a branch or tag is '
            'created. The default is to use no author at all for such '
            'commits.'
            ),
        metavar='NAME',
        ))
    self.parser.set_default('auto_props_files', [])
    group.add_option(IncompatibleOption(
        '--auto-props', type='string',
        action='append', dest='auto_props_files',
        help=(
            'set file properties from the auto-props section '
            'of a file in svn config format'
            ),
        man_help=(
            'Specify a file in the format of Subversion\'s config file, '
            'whose [auto-props] section can be used to set arbitrary '
            'properties on files in the Subversion repository based on '
            'their filenames. (The [auto-props] section header must be '
            'present; other sections of the config file, including the '
            'enable-auto-props setting, are ignored.) Filenames are matched '
            'to the filename patterns case-insensitively.'

            ),
        metavar='FILE',
        ))
    self.parser.set_default('mime_types_files', [])
    group.add_option(IncompatibleOption(
        '--mime-types', type='string',
        action='append', dest='mime_types_files',
        help=(
            'specify an apache-style mime.types file for setting '
            'svn:mime-type'
            ),
        man_help=(
            'Specify an apache-style mime.types \\fIfile\\fR for setting '
            'svn:mime-type.'
            ),
        metavar='FILE',
        ))
    self.parser.set_default('eol_from_mime_type', False)
    group.add_option(IncompatibleOption(
        '--eol-from-mime-type',
        action='store_true',
        help='set svn:eol-style from mime type if known',
        man_help=(
            'For files that don\'t have the kb expansion mode but have a '
            'known mime type, set the eol-style based on the mime type. '
            'For such files, set svn:eol-style to "native" if the mime type '
            'begins with "text/", and leave it unset (i.e., no EOL '
            'translation) otherwise. Files with unknown mime types are '
            'not affected by this option.  This option has no effect '
            'unless the \\fB--mime-types\\fR option is also specified.'
            ),
        ))
    self.parser.set_default('default_eol', 'binary')
    group.add_option(IncompatibleOption(
        '--default-eol', type='choice',
        choices=['binary', 'native', 'CRLF', 'LF', 'CR'],
        action='store',
        help=(
            'default svn:eol-style for non-binary files with '
            'undetermined mime types.  STYLE is "binary" '
            '(default), "native", "CRLF", "LF", or "CR"'
            ),
        man_help=(
            'Set svn:eol-style to \\fIstyle\\fR for files that don\'t have '
            'the CVS \'kb\' expansion mode and whose end-of-line '
            'translation mode hasn\'t been determined by one of the other '
            'options. \\fIstyle\\fR must be \'binary\' (default), '
            '\'native\', \'CRLF\', \'LF\', or \'CR\'.'
            ),
        metavar='STYLE',
        ))
    self.parser.set_default('keywords_off', False)
    group.add_option(IncompatibleOption(
        '--keywords-off',
        action='store_true',
        help=(
            'don\'t set svn:keywords on any files (by default, '
            'cvs2svn sets svn:keywords on non-binary files to "%s")'
            % (config.SVN_KEYWORDS_VALUE,)
            ),
        man_help=(
            'By default, cvs2svn sets svn:keywords on CVS files to "author '
            'id date" if the mode of the RCS file in question is either kv, '
            'kvl or unset. If you use the --keywords-off switch, cvs2svn '
            'will not set svn:keywords for any file. While this will not '
            'touch the keywords in the contents of your files, Subversion '
            'will not expand them.'
            ),
        ))
    group.add_option(ContextOption(
        '--keep-cvsignore',
        action='store_true',
        help=(
            'keep .cvsignore files (in addition to creating '
            'the analogous svn:ignore properties)'
            ),
        man_help=(
            'Include \\fI.cvsignore\\fR files in the output.  (Normally '
            'they are unneeded because cvs2svn sets the corresponding '
            '\\fIsvn:ignore\\fR properties.)'
            ),
        ))
    group.add_option(IncompatibleOption(
        '--cvs-revnums',
        action='callback', callback=self.callback_cvs_revnums,
        help='record CVS revision numbers as file properties',
        man_help=(
            'Record CVS revision numbers as file properties in the '
            'Subversion repository. (Note that unless it is removed '
            'explicitly, the last CVS revision number will remain '
            'associated with the file even after the file is changed '
            'within Subversion.)'
            ),
        ))

    # Deprecated options:
    group.add_option(IncompatibleOption(
        '--no-default-eol',
        action='store_const', dest='default_eol', const=None,
        help=optparse.SUPPRESS_HELP,
        man_help=optparse.SUPPRESS_HELP,
        ))
    self.parser.set_default('auto_props_ignore_case', True)
    # True is the default now, so this option has no effect:
    group.add_option(IncompatibleOption(
        '--auto-props-ignore-case',
        action='store_true',
        help=optparse.SUPPRESS_HELP,
        man_help=optparse.SUPPRESS_HELP,
        ))

    return group

  def _get_extraction_options_group(self):
    group = OptionGroup(self.parser, 'Extraction options')

    return group

  def _add_use_internal_co_option(self, group):
    self.parser.set_default('use_internal_co', False)
    group.add_option(IncompatibleOption(
        '--use-internal-co',
        action='store_true',
        help=(
            'use internal code to extract revision contents '
            '(fastest but disk space intensive) (default)'
            ),
        man_help=(
            'Use internal code to extract revision contents.  This '
            'is up to 50% faster than using \\fB--use-rcs\\fR, but needs '
            'a lot of disk space: roughly the size of your CVS repository '
            'plus the peak size of a complete checkout of the repository '
            'with all branches that existed and still had commits pending '
            'at a given time.  This option is the default.'
            ),
        ))

  def _add_use_cvs_option(self, group):
    self.parser.set_default('use_cvs', False)
    group.add_option(IncompatibleOption(
        '--use-cvs',
        action='store_true',
        help=(
            'use CVS to extract revision contents (slower than '
            '--use-internal-co or --use-rcs)'
            ),
        man_help=(
            'Use CVS to extract revision contents.  This option is slower '
            'than \\fB--use-internal-co\\fR or \\fB--use-rcs\\fR.'
            ),
        ))

  def _add_use_rcs_option(self, group):
    self.parser.set_default('use_rcs', False)
    group.add_option(IncompatibleOption(
        '--use-rcs',
        action='store_true',
        help=(
            'use RCS to extract revision contents (faster than '
            '--use-cvs but fails in some cases)'
            ),
        man_help=(
            'Use RCS \'co\' to extract revision contents.  This option is '
            'faster than \\fB--use-cvs\\fR but fails in some cases.'
            ),
        ))

  def _get_environment_options_group(self):
    group = OptionGroup(self.parser, 'Environment options')
    group.add_option(ContextOption(
        '--tmpdir', type='string',
        action='store',
        help=(
            'directory to use for temporary data files '
            '(default "cvs2svn-tmp")'
            ),
        man_help=(
            'Set the \\fIpath\\fR to use for temporary data. Default '
            'is a directory called \\fIcvs2svn-tmp\\fR under the current '
            'directory.'
            ),
        metavar='PATH',
        ))
    self.parser.set_default('co_executable', config.CO_EXECUTABLE)
    group.add_option(IncompatibleOption(
        '--co', type='string',
        action='store', dest='co_executable',
        help='path to the "co" program (required if --use-rcs)',
        man_help=(
            'Path to the \\fIco\\fR program.  (\\fIco\\fR is needed if the '
            '\\fB--use-rcs\\fR option is used.)'
            ),
        metavar='PATH',
        ))
    self.parser.set_default('cvs_executable', config.CVS_EXECUTABLE)
    group.add_option(IncompatibleOption(
        '--cvs', type='string',
        action='store', dest='cvs_executable',
        help='path to the "cvs" program (required if --use-cvs)',
        man_help=(
            'Path to the \\fIcvs\\fR program.  (\\fIcvs\\fR is needed if the '
            '\\fB--use-cvs\\fR option is used.)'
            ),
        metavar='PATH',
        ))

    return group

  def _get_partial_conversion_options_group(self):
    group = OptionGroup(self.parser, 'Partial conversions')
    group.add_option(ManOption(
        '--pass', type='string',
        action='callback', callback=self.callback_passes,
        help='execute only specified PASS of conversion',
        man_help=(
            'Execute only pass \\fIpass\\fR of the conversion. '
            '\\fIpass\\fR can be specified by name or by number (see '
            '\\fB--help-passes\\fR).'
            ),
        metavar='PASS',
        ))
    group.add_option(ManOption(
        '--passes', '-p', type='string',
        action='callback', callback=self.callback_passes,
        help=(
            'execute passes START through END, inclusive (PASS, '
            'START, and END can be pass names or numbers)'
            ),
        man_help=(
            'Execute passes \\fIstart\\fR through \\fIend\\fR of the '
            'conversion (inclusive). \\fIstart\\fR and \\fIend\\fR can be '
            'specified by name or by number (see \\fB--help-passes\\fR). '
            'If \\fIstart\\fR or \\fIend\\fR is missing, it defaults to '
            'the first or last pass, respectively. For this to work the '
            'earlier passes must have been completed before on the '
            'same CVS repository, and the generated data files must be '
            'in the temporary directory (see \\fB--tmpdir\\fR).'
            ),
        metavar='[START]:[END]',
        ))

    return group

  def _get_information_options_group(self):
    group = OptionGroup(self.parser, 'Information options')
    group.add_option(ManOption(
        '--version',
        action='callback', callback=self.callback_version,
        help='print the version number',
        man_help='Print the version number.',
        ))
    group.add_option(ManOption(
        '--help', '-h',
        action="help",
        help='print this usage message and exit with success',
        man_help='Print the usage message and exit with success.',
        ))
    group.add_option(ManOption(
        '--help-passes',
        action='callback', callback=self.callback_help_passes,
        help='list the available passes and their numbers',
        man_help=(
            'Print the numbers and names of the conversion passes and '
            'exit with success.'
            ),
        ))
    group.add_option(ManOption(
        '--man',
        action='callback', callback=self.callback_manpage,
        help='write the manpage for this program to standard output',
        man_help=(
            'Output the unix-style manpage for this program to standard '
            'output.'
            ),
        ))
    group.add_option(ManOption(
        '--verbose', '-v',
        action='callback', callback=self.callback_verbose,
        help='verbose (may be specified twice for debug output)',
        man_help=(
            'Print more information while running. This option may be '
            'specified twice to output voluminous debugging information.'
            ),
        ))
    group.add_option(ManOption(
        '--quiet', '-q',
        action='callback', callback=self.callback_quiet,
        help='quiet (may be specified twice for very quiet)',
        man_help=(
            'Print less information while running. This option may be '
            'specified twice to suppress all non-error output.'
            ),
        ))
    group.add_option(ContextOption(
        '--write-symbol-info', type='string',
        action='store', dest='symbol_info_filename',
        help='write information and statistics about CVS symbols to PATH.',
        man_help=(
            'Write to \\fIpath\\fR symbol statistics and information about '
            'how symbols were converted during CollateSymbolsPass.'
            ),
        metavar='PATH',
        ))
    group.add_option(ContextOption(
        '--skip-cleanup',
        action='store_true',
        help='prevent the deletion of intermediate files',
        man_help='Prevent the deletion of temporary files.',
        ))
    prof = 'cProfile'
    try:
        import cProfile
    except ImportError:
        prof = 'hotshot'
    group.add_option(ManOption(
        '--profile',
        action='callback', callback=self.callback_profile,
        help='profile with \'' + prof + '\' (into file cvs2svn.' + prof + ')',
        man_help=(
            'Profile with \'' + prof + '\' (into file \\fIcvs2svn.' + prof + '\\fR).'
            ),
        ))

    return group

  def callback_options(self, option, opt_str, value, parser):
    parser.values.options_file_found = True
    self.process_options_file(value)

  def callback_encoding(self, option, opt_str, value, parser):
    ctx = Ctx()

    try:
      ctx.cvs_author_decoder.add_encoding(value)
      ctx.cvs_log_decoder.add_encoding(value)
      ctx.cvs_filename_decoder.add_encoding(value)
    except LookupError, e:
      raise FatalError(str(e))

  def callback_fallback_encoding(self, option, opt_str, value, parser):
    ctx = Ctx()

    try:
      ctx.cvs_author_decoder.set_fallback_encoding(value)
      ctx.cvs_log_decoder.set_fallback_encoding(value)
      # Don't use fallback_encoding for filenames.
    except LookupError, e:
      raise FatalError(str(e))

  def callback_help_passes(self, option, opt_str, value, parser):
    self.pass_manager.help_passes()
    sys.exit(0)

  def callback_manpage(self, option, opt_str, value, parser):
    f = codecs.getwriter('utf_8')(sys.stdout)
    writer = ManWriter(parser,
                       section='1',
                       date=datetime.date.today(),
                       source='Version %s' % (VERSION,),
                       manual='User Commands',
                       short_desc=self.short_desc,
                       synopsis=self.synopsis,
                       long_desc=self.long_desc,
                       files=self.files,
                       authors=self.authors,
                       see_also=self.see_also)
    writer.write_manpage(f)
    sys.exit(0)

  def callback_version(self, option, opt_str, value, parser):
    sys.stdout.write(
        '%s version %s\n' % (self.progname, VERSION)
        )
    sys.exit(0)

  def callback_verbose(self, option, opt_str, value, parser):
    logger.increase_verbosity()

  def callback_quiet(self, option, opt_str, value, parser):
    logger.decrease_verbosity()

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

  def callback_profile(self, option, opt_str, value, parser):
    self.profiling = True

  def callback_symbol_hints(self, option, opt_str, value, parser):
    parser.values.symbol_strategy_rules.append(SymbolHintsFileRule(value))

  def callback_force_branch(self, option, opt_str, value, parser):
    parser.values.symbol_strategy_rules.append(
        ForceBranchRegexpStrategyRule(value)
        )

  def callback_force_tag(self, option, opt_str, value, parser):
    parser.values.symbol_strategy_rules.append(
        ForceTagRegexpStrategyRule(value)
        )

  def callback_exclude(self, option, opt_str, value, parser):
    parser.values.symbol_strategy_rules.append(
        ExcludeRegexpStrategyRule(value)
        )

  def callback_cvs_revnums(self, option, opt_str, value, parser):
    Ctx().revision_property_setters.append(CVSRevisionNumberSetter())

  def callback_symbol_transform(self, option, opt_str, value, parser):
    [pattern, replacement] = value.split(":")
    try:
      parser.values.symbol_transforms.append(
          RegexpSymbolTransform(pattern, replacement)
          )
    except re.error:
      raise FatalError("'%s' is not a valid regexp." % (pattern,))

  # Common to SVNRunOptions, HgRunOptions (GitRunOptions and
  # BzrRunOptions do not support --use-internal-co, so cannot use this).
  def process_all_extraction_options(self):
    ctx = Ctx()
    options = self.options

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    not_both(options.use_rcs, '--use-rcs',
             options.use_internal_co, '--use-internal-co')

    not_both(options.use_cvs, '--use-cvs',
             options.use_internal_co, '--use-internal-co')

    if options.use_rcs:
      ctx.revision_collector = NullRevisionCollector()
      ctx.revision_reader = RCSRevisionReader(options.co_executable)
    elif options.use_cvs:
      ctx.revision_collector = NullRevisionCollector()
      ctx.revision_reader = CVSRevisionReader(options.cvs_executable)
    else:
      # --use-internal-co is the default:
      ctx.revision_collector = InternalRevisionCollector(compress=True)
      ctx.revision_reader = InternalRevisionReader(compress=True)

  def process_symbol_strategy_options(self):
    """Process symbol strategy-related options."""

    ctx = Ctx()
    options = self.options

    # Add the standard symbol name cleanup rules:
    self.options.symbol_transforms.extend([
        ReplaceSubstringsSymbolTransform('\\','/'),
        # Remove leading, trailing, and repeated slashes:
        NormalizePathsSymbolTransform(),
        ])

    if ctx.trunk_only:
      if options.symbol_strategy_rules or options.keep_trivial_imports:
        raise SymbolOptionsWithTrunkOnlyException()

    else:
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
      elif options.symbol_default == 'exclude':
        options.symbol_strategy_rules.append(AllExcludedRule())
      else:
        assert False

      # Now add a rule whose job it is to pick the preferred parents of
      # branches and tags:
      options.symbol_strategy_rules.append(HeuristicPreferredParentRule())

  def process_property_setter_options(self):
    """Process the options that set SVN properties."""

    ctx = Ctx()
    options = self.options

    for value in options.auto_props_files:
      ctx.file_property_setters.append(
          AutoPropsPropertySetter(value, options.auto_props_ignore_case)
          )

    for value in options.mime_types_files:
      ctx.file_property_setters.append(MimeMapper(value))

    ctx.file_property_setters.append(CVSBinaryFileEOLStyleSetter())

    ctx.file_property_setters.append(CVSBinaryFileDefaultMimeTypeSetter())

    if options.eol_from_mime_type:
      ctx.file_property_setters.append(EOLStyleFromMimeTypeSetter())

    ctx.file_property_setters.append(
        DefaultEOLStyleSetter(options.default_eol)
        )

    ctx.file_property_setters.append(SVNBinaryFileKeywordsPropertySetter())

    if not options.keywords_off:
      ctx.file_property_setters.append(
        KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE)
        )

    ctx.file_property_setters.append(ExecutablePropertySetter())

    ctx.file_property_setters.append(DescriptionPropertySetter())

  def process_options(self):
    """Do the main configuration based on command-line options.

    This method is only called if the --options option was not
    specified."""

    raise NotImplementedError()

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

  def verify_option_compatibility(self):
    """Verify that no options incompatible with --options were used.

    The --options option was specified.  Verify that no incompatible
    options or arguments were specified."""

    if self.options.options_incompatible_options or self.args:
      if self.options.options_incompatible_options:
        oio = self.options.options_incompatible_options
        logger.error(
            '%s: The following options cannot be used in combination with '
            'the --options\n'
            'option:\n'
            '    %s\n'
            % (error_prefix, '\n    '.join(oio))
            )
      if self.args:
        logger.error(
            '%s: No cvs-repos-path arguments are allowed with the --options '
            'option.\n'
            % (error_prefix,)
            )
      sys.exit(1)

  def process_options_file(self, options_filename):
    """Read options from the file named OPTIONS_FILENAME.

    Store the run options to SELF."""

    g = {
      'ctx' : Ctx(),
      'run_options' : self,
      }
    execfile(options_filename, g)

  def usage(self):
    self.parser.print_help()


