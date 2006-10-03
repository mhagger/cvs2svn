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

"""Manage change sets."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx


class Changeset(object):
  """A set of cvs_items that might potentially form a single change set."""

  def __init__(self, id, cvs_item_ids):
    self.id = id
    self.cvs_item_ids = set(cvs_item_ids)

  def get_cvs_items(self):
    """Return the set of CVSItems within this Changeset."""

    return set([
        Ctx()._cvs_items_db[cvs_item_id]
        for cvs_item_id in self.cvs_item_ids])

  def __getstate__(self):
    return (self.id, self.cvs_item_ids,)

  def __setstate__(self, state):
    (self.id, self.cvs_item_ids,) = state

  def __str__(self):
    return 'Changeset<%x>' % (self.id,)

  def __repr__(self):
    return '%s [%s]' % (
        self, ', '.join(['%x' % id for id in self.cvs_item_ids]),)


class RevisionChangeset(Changeset):
  """A Changeset consisting of CVSRevisions."""

  pass


class SymbolChangeset(Changeset):
  """A Changeset consisting of CVSSymbols."""

  pass


