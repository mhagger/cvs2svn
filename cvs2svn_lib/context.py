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

"""Store the context (options, etc) for a cvs2svn run."""


import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config


class Ctx:
  """Session state for this run of cvs2svn.  For example, run-time
  options are stored here.  This class is a Borg, see
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531."""

  __shared_state = { }

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    # Else, initialize to defaults.
    self.target = None
    self.existing_svnrepos = False
    self.dump_only = False
    self.dumpfile = config.DUMPFILE
    self.dry_run = False
    self.use_cvs = False
    self.svnadmin = "svnadmin"
    self.trunk_only = False
    self.trunk_base = "trunk"
    self.branches_base = "branches"
    self.tags_base = "tags"
    self.prune = True
    self.encoding = ["ascii"]
    self.symbol_strategy = None
    self.symbol_transforms = []
    self.username = None
    self.fs_type = None
    self.bdb_txn_nosync = False
    self.svn_property_setters = []
    self.tmpdir = '.'
    self.skip_cleanup = False
    # A list of Project instances for all projects being converted.
    self.projects = []

  def add_project(self, project):
    """Add a project to be converted."""

    self.projects.append(project)

  def get_temp_filename(self, basename):
    return os.path.join(self.tmpdir, basename)

  def clean(self):
    """Dispose of items in our dictionary that are not intended to
    live past the end of a pass (identified by exactly one leading
    underscore)."""

    for attr in self.__dict__.keys():
      if (attr.startswith('_') and not attr.startswith('__')
          and not attr.startswith('_Ctx__')):
        delattr(self, attr)


