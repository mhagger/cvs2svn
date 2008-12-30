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

from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_output_option import DumpfileOutputOption
from cvs2svn_lib.svn_output_option import ExistingRepositoryOutputOption
from cvs2svn_lib.svn_output_option import NewRepositoryOutputOption
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import IncompatibleOption


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

    group.add_option(
        '--dry-run',
        action='callback', callback=self.callback_dry_run,
        help=(
            'do not create a repository or a dumpfile; just print what '
            'would happen.'
            ),
        )

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

  def callback_dry_run(self, option, opt_str, value, parser):
    Ctx().dry_run = True

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


