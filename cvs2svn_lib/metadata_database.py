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

"""This module contains a class to store CVSRevision metadata."""


import sha

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import Database
from cvs2svn_lib.key_generator import KeyGenerator


class MetadataDatabase:
  """A Database to store metadata about CVSRevisions.

  This database has two types of entries:

      digest -> id

      hex(id) -> (project.id, author, log_msg,)

  Digest is the digest of a string containing author, log_message, and
  possible project_id and/or branch_name, and is used to locate
  matching records efficiently.  id is a unique id for each record (as
  a hex string ('%x' % id) when used as a key).

  """

  def __init__(self, mode):
    """Initialize an instance, opening database in MODE (like the MODE
    argument to Database or anydbm.open()).  Use CVS_FILE_DB to look
    up CVSFiles."""

    self.key_generator = KeyGenerator(1)
    self.db = Database(artifact_manager.get_temp_file(config.METADATA_DB),
                       mode)

  def get_key(self, project, branch_name, author, log_msg):
      """Return the id for the specified metadata.

      Locate the record for a commit with the specified (PROJECT,
      BRANCH_NAME, AUTHOR, LOG_MSG).  (Depending on policy, not all of
      these items are necessarily used when creating the unique id.)
      If there is no such record, create one and return its
      newly-generated id."""

      key = [author, log_msg]
      if not Ctx().cross_project_commits:
        key += '%x' % project.id
      if not Ctx().cross_branch_commits:
        key += branch_name or ''

      digest = sha.new('\0'.join(key)).hexdigest()
      try:
          # See if it is already known:
          return self.db[digest]
      except KeyError:
          pass

      id = self.key_generator.gen_id()
      self.db['%x' % id] = (project.id, author, log_msg,)
      self.db[digest] = id
      return id

  def __getitem__(self, id):
    """Return (author, log_msg,) for ID."""

    return self.db['%x' % (id,)][1:]


