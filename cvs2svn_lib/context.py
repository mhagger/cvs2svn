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
from cvs2svn_lib.log import Log


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
    self.dumpfile = config.DUMPFILE
    self.tmpdir = '.'
    self.verbose = False
    self.quiet = False
    self.prune = True
    self.existing_svnrepos = False
    self.dump_only = False
    self.dry_run = False
    self.trunk_only = False
    self.trunk_base = "trunk"
    self.tags_base = "tags"
    self.branches_base = "branches"
    self.encoding = ["ascii"]
    self.mime_types_file = None
    self.auto_props_file = None
    self.auto_props_ignore_case = False
    self.no_default_eol = False
    self.eol_from_mime_type = False
    self.keywords_off = False
    self.use_cvs = False
    self.svnadmin = "svnadmin"
    self.username = None
    self.print_help = False
    self.skip_cleanup = False
    self.bdb_txn_nosync = False
    self.fs_type = None
    self.symbol_strategy = None
    self.symbol_strategy_default = 'strict'
    self.symbol_transforms = []
    self.svn_property_setters = []
    self.project = None
    # A list of Project instances for all projects being converted.
    self.projects = []

  def add_project(self, project):
    """Add a project to be converted.

    Currently, only one project is supported (i.e., this method must
    be called exactly once)."""

    assert self.project is None
    self.project = project
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

  def to_utf8(self, value, mode='replace'):
    """Encode (as Unicode) VALUE, trying the encodings in self.encoding
    as valid source encodings.  Raise UnicodeError on failure of all
    source encodings."""

    ### FIXME: The 'replace' default mode should be an option,
    ### like --encoding is.
    for encoding in self.encoding:
      try:
        return unicode(value, encoding, mode).encode('utf8')
      except UnicodeError:
        Log().verbose("Encoding '%s' failed for string '%s'"
                      % (encoding, value))
    raise UnicodeError



