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
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.symbol import BranchSymbol
from cvs2svn_lib.symbol import TagSymbol
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.line_of_development import Branch
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag


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

  def filter_excluded_symbols(self):
    """Delete any excluded symbols and references to them."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        # Skip this entire revision if it's on an excluded branch
        if isinstance(cvs_item.lod, Branch):
          symbol = cvs_item.lod.symbol
          if isinstance(symbol, ExcludedSymbol):
            # Delete this item.
            del self[cvs_item.id]
            # There are only two other possible references to this
            # item from CVSRevisions outside of the to-be-deleted
            # branch:

            # Is if this is the first commit on the branch, it is
            # listed in the branch_commit_ids of the CVSRevision from
            # which the branch sprouted.
            if cvs_item.first_on_branch_id is not None:
              prev = self.get(cvs_item.prev_id)
              if prev is not None:
                prev.branch_commit_ids.remove(cvs_item.id)

            # If it is the last default revision on a non-trunk
            # default branch followed by a 1.2 revision, then the 1.2
            # revision depends on this one.
            if cvs_item.default_branch_next_id is not None:
              next = self.get(cvs_item.default_branch_next_id)
              if next is not None:
                assert next.default_branch_prev_id == cvs_item.id
                next.default_branch_prev_id = None
      elif isinstance(cvs_item, CVSSymbol):
        # Skip this symbol if it is to be excluded
        symbol = cvs_item.symbol
        if isinstance(symbol, ExcludedSymbol):
          del self[cvs_item.id]
          # A CVSSymbol is the successor of the CVSRevision that it
          # springs from.  If that revision still exists, delete
          # this symbol from its branch_ids:
          cvs_revision = self.get(cvs_item.rev_id)
          if cvs_revision is None:
            # It has already been deleted; do nothing:
            pass
          elif isinstance(cvs_item, CVSBranch):
            cvs_revision.branch_ids.remove(cvs_item.id)
          elif isinstance(cvs_item, CVSTag):
            cvs_revision.tag_ids.remove(cvs_item.id)
      else:
        raise RuntimeError('Unknown cvs item type')

  def mutate_symbols(self):
    """Force symbols to be tags/branches based on self.symbol_db."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        # This CVSRevision may be affected by the mutation of any
        # CVSSymbols that it references, but there is nothing to do
        # here directly.
        pass
      elif isinstance(cvs_item, CVSSymbol):
        symbol = cvs_item.symbol
        if isinstance(cvs_item, CVSBranch) and isinstance(symbol, TagSymbol):
          # Mutate the branch into a tag.
          if cvs_item.next_id is not None:
            # This shouldn't happen because it was checked in
            # CollateSymbolsPass:
            raise FatalError('Attempt to exclude a branch with commits.')
          cvs_item = CVSTag(
              cvs_item.id, cvs_item.cvs_file, cvs_item.symbol,
              cvs_item.rev_id)
          self[cvs_item.id] = cvs_item
          cvs_revision = self[cvs_item.rev_id]
          cvs_revision.branch_ids.remove(cvs_item.id)
          cvs_revision.tag_ids.append(cvs_item.id)
        elif isinstance(cvs_item, CVSTag) \
               and isinstance(symbol, BranchSymbol):
          # Mutate the tag into a branch.
          cvs_item = CVSBranch(
              cvs_item.id, cvs_item.cvs_file, cvs_item.symbol,
              None, cvs_item.rev_id, None)
          self[cvs_item.id] = cvs_item
          cvs_revision = self[cvs_item.rev_id]
          cvs_revision.tag_ids.remove(cvs_item.id)
          cvs_revision.branch_ids.append(cvs_item.id)
      else:
        raise RuntimeError('Unknown cvs item type')


