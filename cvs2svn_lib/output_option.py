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
from cvs2svn_lib.svn_repository_mirror import SVNRepositoryMirror
from cvs2svn_lib.stdout_delegate import StdoutDelegate
from cvs2svn_lib.dumpfile_delegate import DumpfileDelegate
from cvs2svn_lib.repository_delegate import RepositoryDelegate


class OutputOption:
  """Represents an output choice for a run of cvs2svn."""

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed for this output option.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    pass

  def check(self):
    """Check that the options stored in SELF are sensible.

    This might including the existence of a repository on disk, etc."""

    raise NotImplementedError()

  def setup(self, svn_rev_count):
    """Prepare this output option."""

    raise NotImplementedError()

  def process(self, svn_commit):
    """Process SVN_COMMIT, which is an instance of SVNCommit."""

    raise NotImplementedError()

  def cleanup(self):
    """Perform any required cleanup related to this output option."""

    raise NotImplementedError()


class SVNOutputOption(OutputOption):
  """An OutputOption appropriate for output to Subversion."""

  def __init__(self):
    self.repos = SVNRepositoryMirror()

  def register_artifacts(self, which_pass):
    self.repos.register_artifacts(which_pass)
    Ctx().revision_reader.register_artifacts(which_pass)

  def setup(self, svn_rev_count):
    self.repos.open()
    Ctx().revision_reader.start()
    self.repos.add_delegate(StdoutDelegate(svn_rev_count))

  def process(self, svn_commit):
    svn_commit.commit(self.repos)

  def cleanup(self):
    self.repos.close()
    Ctx().revision_reader.finish()


class DumpfileOutputOption(SVNOutputOption):
  """Output the result of the conversion into a dumpfile."""

  def __init__(self, dumpfile_path):
    SVNOutputOption.__init__(self)
    self.dumpfile_path = dumpfile_path

  def check(self):
    pass

  def setup(self, svn_rev_count):
    Log().quiet("Starting Subversion Dumpfile.")
    SVNOutputOption.setup(self, svn_rev_count)
    if not Ctx().dry_run:
      self.repos.add_delegate(
          DumpfileDelegate(Ctx().revision_reader, self.dumpfile_path)
          )


class RepositoryOutputOption(SVNOutputOption):
  """Output the result of the conversion into an SVN repository."""

  def __init__(self, target):
    SVNOutputOption.__init__(self)
    self.target = target

  def check(self):
    if not Ctx().dry_run:
      # Verify that svnadmin can be executed.  The 'help' subcommand
      # should be harmless.
      try:
        check_command_runs([Ctx().svnadmin_executable, 'help'], 'svnadmin')
      except CommandFailedException, e:
        raise FatalError(
            '%s\n'
            'svnadmin could not be executed.  Please ensure that it is\n'
            'installed and/or use the --svnadmin option.' % (e,))

  def setup(self, svn_rev_count):
    Log().quiet("Starting Subversion Repository.")
    SVNOutputOption.setup(self, svn_rev_count)
    if not Ctx().dry_run:
      self.repos.add_delegate(
          RepositoryDelegate(Ctx().revision_reader, self.target)
          )


class NewRepositoryOutputOption(RepositoryOutputOption):
  """Output the result of the conversion into a new SVN repository."""

  def __init__(self, target, fs_type=None, bdb_txn_nosync=None):
    RepositoryOutputOption.__init__(self, target)
    self.fs_type = fs_type
    self.bdb_txn_nosync = bdb_txn_nosync

  def check(self):
    RepositoryOutputOption.check(self)
    if not Ctx().dry_run and os.path.exists(self.target):
      raise FatalError("the svn-repos-path '%s' exists.\n"
                       "Remove it, or pass '--existing-svnrepos'."
                       % self.target)

  def setup(self, svn_rev_count):
    Log().normal("Creating new repository '%s'" % (self.target))
    if Ctx().dry_run:
      # Do not actually create repository:
      pass
    elif not self.fs_type:
      # User didn't say what kind repository (bdb, fsfs, etc).
      # We still pass --bdb-txn-nosync.  It's a no-op if the default
      # repository type doesn't support it, but we definitely want
      # it if BDB is the default.
      run_command('%s create %s "%s"'
                  % (Ctx().svnadmin_executable, "--bdb-txn-nosync",
                     self.target))
    elif self.fs_type == 'bdb':
      # User explicitly specified bdb.
      #
      # Since this is a BDB repository, pass --bdb-txn-nosync,
      # because it gives us a 4-5x speed boost (if cvs2svn is
      # creating the repository, cvs2svn should be the only program
      # accessing the svn repository (until cvs is done, at least)).
      # But we'll turn no-sync off in self.finish(), unless
      # instructed otherwise.
      run_command('%s create %s %s "%s"'
                  % (Ctx().svnadmin_executable,
                     "--fs-type=bdb", "--bdb-txn-nosync",
                     self.target))
    else:
      # User specified something other than bdb.
      run_command('%s create %s "%s"'
                  % (Ctx().svnadmin_executable,
                     "--fs-type=%s" % self.fs_type,
                     self.target))

    RepositoryOutputOption.setup(self, svn_rev_count)

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)

    # If this is a BDB repository, and we created the repository, and
    # --bdb-no-sync wasn't passed, then comment out the DB_TXN_NOSYNC
    # line in the DB_CONFIG file, because txn syncing should be on by
    # default in BDB repositories.
    #
    # We determine if this is a BDB repository by looking for the
    # DB_CONFIG file, which doesn't exist in FSFS, rather than by
    # checking self.fs_type.  That way this code will Do The Right
    # Thing in all circumstances.
    db_config = os.path.join(self.target, "db/DB_CONFIG")
    if Ctx().dry_run:
      # Do not change repository:
      pass
    elif not self.bdb_txn_nosync and os.path.exists(db_config):
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


