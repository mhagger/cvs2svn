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


from boolean import *


# If this run's output is a repository, then (in the tmpdir) we use
# a dumpfile of this name for repository loads.
#
# If this run's output is a dumpfile, then this is default name of
# that dumpfile, but in the current directory (unless the user has
# specified a dumpfile path, of course, in which case it will be
# wherever the user said).
DUMPFILE = 'cvs2svn-dump'


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
    self.dumpfile = DUMPFILE
    self.tmpdir = '.'
    self.verbose = 0
    self.quiet = 0
    self.prune = 1
    self.existing_svnrepos = 0
    self.dump_only = 0
    self.dry_run = 0
    self.trunk_only = 0
    self.trunk_base = "trunk"
    self.tags_base = "tags"
    self.branches_base = "branches"
    self.encoding = ["ascii"]
    self.mime_types_file = None
    self.auto_props_file = None
    self.auto_props_ignore_case = False
    self.no_default_eol = 0
    self.eol_from_mime_type = 0
    self.keywords_off = 0
    self.use_cvs = None
    self.svnadmin = "svnadmin"
    self.username = None
    self.print_help = 0
    self.skip_cleanup = 0
    self.bdb_txn_nosync = 0
    self.fs_type = None
    self.forced_branches = []
    self.forced_tags = []
    self.excludes = []
    self.symbol_transforms = []
    self.svn_property_setters = []


