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

"""This module contains the TagsDatabase class."""


from boolean import *
import config
from artifact_manager import artifact_manager
import database


class TagsDatabase:
  """A Database to record symbolic names that are tags.

  Each key is a tag name.  The value has no meaning, and is set to the
  empty string.  (Since an SDatabase is used, the key cannot be set to
  None.)"""

  def __init__(self, mode):
    self.db = database.SDatabase(
        artifact_manager.get_temp_file(config.TAGS_DB), mode)

  def add(self, item):
    self.db[item] = ''

  def remove(self, item):
    del self.db[item]

  def __contains__(self, item):
    return self.db.has_key(item)


