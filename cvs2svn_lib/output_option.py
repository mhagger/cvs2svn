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

"""This module contains classes that hold the cvs2svn output options."""


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

  def check_symbols(self, symbol_map):
    """Check that the symbols in SYMBOL_MAP are OK for this output option.

    SYMBOL_MAP is a map {AbstractSymbol : (Trunk|TypedSymbol)},
    indicating how each symbol is planned to be converted.  Raise a
    FatalError if the symbol plan is not acceptable for this output
    option."""

    raise NotImplementedError()

  def setup(self, svn_rev_count):
    """Prepare this output option."""

    raise NotImplementedError()

  def process_initial_project_commit(self, svn_commit):
    """Process SVN_COMMIT, which is an SVNInitialProjectCommit."""

    raise NotImplementedError()

  def process_primary_commit(self, svn_commit):
    """Process SVN_COMMIT, which is an SVNPrimaryCommit."""

    raise NotImplementedError()

  def process_post_commit(self, svn_commit):
    """Process SVN_COMMIT, which is an SVNPostCommit."""

    raise NotImplementedError()

  def process_branch_commit(self, svn_commit):
    """Process SVN_COMMIT, which is an SVNBranchCommit."""

    raise NotImplementedError()

  def process_tag_commit(self, svn_commit):
    """Process SVN_COMMIT, which is an SVNTagCommit."""

    raise NotImplementedError()

  def cleanup(self):
    """Perform any required cleanup related to this output option."""

    raise NotImplementedError()


