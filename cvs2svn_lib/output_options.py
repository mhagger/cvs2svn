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
    RepositoryOutputOption.setup(self, repos)
    Log().quiet("Starting Subversion Repository.")
    if not Ctx().dry_run:
      repos.add_delegate(RepositoryDelegate())

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)


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
      repos.add_delegate(RepositoryDelegate())

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)


