# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

"""This module contains a class to store CVSRevision metadata."""


import sha

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import Database
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.serializer import MarshalSerializer


class MetadataDatabase:
  """A Database to store metadata about CVSRevisions.

  This database manages a map

      id -> (project.id, author, log_msg,)

  where id is a unique identifier for a set of metadata.

  When the MetadataDatabase is opened in DB_OPEN_NEW mode, the mapping

      { (project, branch_name, author, log_msg) -> id }

  is also available.  If the requested set of metadata has never been
  seen before, a new record is created and its id is returned.  This
  is done by creating an SHA digest of a string containing author,
  log_message, and possible project_id and/or branch_name, then
  looking up the digest in the _digest_to_id map.

  """

  def __init__(self, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.mode = mode

    if self.mode == DB_OPEN_NEW:
      # A map { digest : id }:
      self._digest_to_id = {}

      # A key_generator to generate keys for metadata that haven't
      # been seen yet:
      self.key_generator = KeyGenerator()
    elif self.mode == DB_OPEN_READ:
      # In this case, we don't need key_generator or _digest_to_id.
      pass
    elif self.mode == DB_OPEN_WRITE:
      # Modifying an existing database is not supported:
      raise NotImplementedError('Mode %r is not supported' % self.mode)

    self.db = Database(
        artifact_manager.get_temp_file(config.METADATA_DB), self.mode,
        MarshalSerializer())

  def get_key(self, project, branch_name, author, log_msg):
      """Return the id for the specified metadata.

      Locate the record for a commit with the specified (PROJECT,
      BRANCH_NAME, AUTHOR, LOG_MSG).  (Depending on policy, not all of
      these items are necessarily used when creating the unique id.)
      If there is no such record, create one and return its
      newly-generated id."""

      key = [author, log_msg]
      if not Ctx().cross_project_commits:
        key.append('%x' % project.id)
      if not Ctx().cross_branch_commits:
        key.append(branch_name or '')

      digest = sha.new('\0'.join(key)).digest()
      try:
          # See if it is already known:
          return self._digest_to_id[digest]
      except KeyError:
          pass

      id = self.key_generator.gen_id()
      self._digest_to_id[digest] = id
      self.db['%x' % id] = (author, log_msg,)
      return id

  def __getitem__(self, id):
    """Return (author, log_msg,) for ID."""

    return self.db['%x' % (id,)]

  def close(self):
    if self.mode == DB_OPEN_NEW:
      self._digest_to_id = None
    self.db.close()
    self.db = None


