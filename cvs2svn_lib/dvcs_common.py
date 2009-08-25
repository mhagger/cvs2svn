# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007-2009 CollabNet.  All rights reserved.
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

"""Miscellaneous utility code common to DVCS backends (like
Git, Mercurial, or Bazaar).
"""

import sys

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.project import Project
from cvs2svn_lib.output_option import OutputOption


class DVCSRunOptions(RunOptions):
  """Dumping ground for whatever is common to GitRunOptions and
  HgRunOptions."""
  def __init__(self, progname, cmd_args, pass_manager):
    Ctx().cross_project_commits = False
    Ctx().cross_branch_commits = False
    RunOptions.__init__(self, progname, cmd_args, pass_manager)

  def set_project(
        self,
        project_cvs_repos_path,
        symbol_transforms=None,
        symbol_strategy_rules=[],
        ):
    """Set the project to be converted.

    If a project had already been set, overwrite it.

    Most arguments are passed straight through to the Project
    constructor.  SYMBOL_STRATEGY_RULES is an iterable of
    SymbolStrategyRules that will be applied to symbols in this
    project."""

    symbol_strategy_rules = list(symbol_strategy_rules)

    project = Project(
        0,
        project_cvs_repos_path,
        symbol_transforms=symbol_transforms,
        )

    self.projects = [project]
    self.project_symbol_strategy_rules = [symbol_strategy_rules]

  def process_options(self):
    # Consistency check for options and arguments.
    if len(self.args) == 0:
      self.usage()
      sys.exit(1)

    if len(self.args) > 1:
      Log().error(error_prefix + ": must pass only one CVS repository.\n")
      self.usage()
      sys.exit(1)

    cvsroot = self.args[0]

    self.process_extraction_options()
    self.process_output_options()
    self.process_symbol_strategy_options()
    self.process_property_setter_options()

    # Create the project:
    self.set_project(
        cvsroot,
        symbol_transforms=self.options.symbol_transforms,
        symbol_strategy_rules=self.options.symbol_strategy_rules,
        )


class DVCSOutputOption(OutputOption):
  # name of output format (for error messages); must be set by
  # subclasses
  name = None

  def normalize_author_transforms(self, author_transforms):
    """Return a new dict with the same content as author_transforms, but all
    strings encoded to UTF-8.  Also turns None into the empty dict."""
    result = {}
    if author_transforms is not None:
      for (cvsauthor, (name, email,)) in author_transforms.iteritems():
        cvsauthor = to_utf8(cvsauthor)
        name = to_utf8(name)
        email = to_utf8(email)
        result[cvsauthor] = (name, email,)
    return result

  def check(self):
    if Ctx().cross_project_commits:
      raise FatalError(
          '%s output is not supported with cross-project commits' % self.name
          )
    if Ctx().cross_branch_commits:
      raise FatalError(
          '%s output is not supported with cross-branch commits' % self.name
          )
    if Ctx().username is None:
      raise FatalError(
          '%s output requires a default commit username' % self.name
          )


def to_utf8(s):
  if isinstance(s, unicode):
    return s.encode('utf8')
  else:
    return s


