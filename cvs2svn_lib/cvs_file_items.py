# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006 CollabNet.  All rights reserved.
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

"""This module contains a class to manage the CVSItems related to one file."""


from cvs2svn_lib.boolean import *


class CVSFileItems(object):
  def __init__(self, cvs_items):
    # A map from CVSItem.id to CVSItem:
    self._cvs_items = {}

    # The CVSItem.id of the root CVSItem:
    self.root_id = None

    for cvs_item in cvs_items:
      self._cvs_items[cvs_item.id] = cvs_item
      if not cvs_item.get_pred_ids():
        assert self.root_id is None
        self.root_id = cvs_item.id

    assert self.root_id is not None

  def __getitem__(self, id):
    """Return the CVSItem with the specified ID."""

    return self._cvs_items[id]

  def __setitem__(self, id, cvs_item):
    assert id is not self.root_id
    self._cvs_items[id] = cvs_item

  def __delitem__(self, id):
    assert id is not self.root_id
    del self._cvs_items[id]

  def get(self, id, default=None):
    try:
      return self[id]
    except KeyError:
      return default

  def __contains__(self, id):
    return id in self._cvs_items

  def values(self):
    return self._cvs_items.values()

  def copy(self):
    return CVSFileItems(self.values())


