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

"""This module contains classes that hold the cvs2svn output options."""


from __future__ import generators

import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import run_command
from cvs2svn_lib.dumpfile_delegate import DumpfileDelegate
from cvs2svn_lib.repository_delegate import RepositoryDelegate


class OutputOption:
  """Represents an output choice for a run of cvs2svn."""

  def check(self):
    """Check that the options stored in SELF are sensible.

    This might including the existence of a repository on disk, etc."""

    raise NotImplementedError()

  def setup(self, repos):
    """Prepare this output option.

    This might include registering a delegate to repos."""

    raise NotImplementedError()

  def cleanup(self):
    """Perform any required cleanup related to this output option."""

    raise NotImplementedError()


class DumpfileOutputOption(OutputOption):
  """Output the result of the conversion into a dumpfile."""

  def __init__(self, dumpfile_path):
    self.dumpfile_path = dumpfile_path

  def check(self):
    pass

  def setup(self, repos):
    Log().quiet("Starting Subversion Dumpfile.")
    if not Ctx().dry_run:
      repos.add_delegate(DumpfileDelegate(self.dumpfile_path))

  def cleanup(self):
    pass


class RepositoryOutputOption(OutputOption):
  """Output the result of the conversion into an SVN repository."""

  def __init__(self, target):
    self.target = target

  def check(self):
    if not Ctx().dry_run:
      # Verify that svnadmin can be executed.  The 'help' subcommand
      # should be harmless.
      try:
        check_command_runs([Ctx().svnadmin, 'help'], 'svnadmin')
      except CommandFailedException, e:
        raise FatalError(
            '%s\n'
            'svnadmin could not be executed.  Please ensure that it is\n'
            'installed and/or use the --svnadmin option.' % (e,))

  def setup(self, repos):
    pass

  def cleanup(self):
    pass


class NewRepositoryOutputOption(RepositoryOutputOption):
  """Output the result of the conversion into a new SVN repository."""

  def __init__(self, target):
    RepositoryOutputOption.__init__(self, target)

  def check(self):
    RepositoryOutputOption.check(self)
    if not Ctx().dry_run and os.path.exists(self.target):
      raise FatalError("the svn-repos-path '%s' exists.\n"
                       "Remove it, or pass '--existing-svnrepos'."
                       % self.target)

  def setup(self, repos):
    Log().normal("Creating new repository '%s'" % (self.target))
    if Ctx().dry_run:
      # Do not actually create repository:
      pass
    elif not Ctx().fs_type:
      # User didn't say what kind repository (bdb, fsfs, etc).
      # We still pass --bdb-txn-nosync.  It's a no-op if the default
      # repository type doesn't support it, but we definitely want
      # it if BDB is the default.
      run_command('%s create %s "%s"'
                  % (Ctx().svnadmin, "--bdb-txn-nosync", self.target))
    elif Ctx().fs_type == 'bdb':
      # User explicitly specified bdb.
      #
      # Since this is a BDB repository, pass --bdb-txn-nosync,
      # because it gives us a 4-5x speed boost (if cvs2svn is
      # creating the repository, cvs2svn should be the only program
      # accessing the svn repository (until cvs is done, at least)).
      # But we'll turn no-sync off in self.finish(), unless
      # instructed otherwise.
      run_command('%s create %s %s "%s"'
                  % (Ctx().svnadmin, "--fs-type=bdb", "--bdb-txn-nosync",
                     self.target))
    else:
      # User specified something other than bdb.
      run_command('%s create %s "%s"'
                  % (Ctx().svnadmin, "--fs-type=%s" % Ctx().fs_type,
                     self.target))

    RepositoryOutputOption.setup(self, repos)
    Log().quiet("Starting Subversion Repository.")
    if not Ctx().dry_run:
      repos.add_delegate(RepositoryDelegate(self.target))

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)

    # If this is a BDB repository, and we created the repository, and
    # --bdb-no-sync wasn't passed, then comment out the DB_TXN_NOSYNC
    # line in the DB_CONFIG file, because txn syncing should be on by
    # default in BDB repositories.
    #
    # We determine if this is a BDB repository by looking for the
    # DB_CONFIG file, which doesn't exist in FSFS, rather than by
    # checking Ctx().fs_type.  That way this code will Do The Right
    # Thing in all circumstances.
    db_config = os.path.join(self.target, "db/DB_CONFIG")
    if Ctx().dry_run:
      # Do not change repository:
      pass
    elif not Ctx().bdb_txn_nosync and os.path.exists(db_config):
      no_sync = 'set_flags DB_TXN_NOSYNC\n'

      contents = open(db_config, 'r').readlines()
      index = contents.index(no_sync)
      contents[index] = '# ' + no_sync
      open(db_config, 'w').writelines(contents)


class ExistingRepositoryOutputOption(RepositoryOutputOption):
  """Output the result of the conversion into an existing SVN repository."""

  def __init__(self, target):
    RepositoryOutputOption.__init__(self, target)

  def check(self):
    RepositoryOutputOption.check(self)
    if not os.path.isdir(self.target):
      raise FatalError("the svn-repos-path '%s' is not an "
                       "existing directory." % self.target)

  def setup(self, repos):
    RepositoryOutputOption.setup(self, repos)
    Log().quiet("Starting Subversion Repository.")
    if not Ctx().dry_run:
      repos.add_delegate(RepositoryDelegate(self.target))

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)


