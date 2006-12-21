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


from __future__ import generators

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

    self.cvs_file = cvs_items[0].cvs_file

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

  def iter_lods(self, cvs_branch_id=None):
    """Iterate over LinesOfDevelopment in this file, in depth-first order.

    For each LOD, yield tuples (CVSBranch, [CVSRevision], [CVSBranch],
    [CVSTag]).  CVSBranch is the branch being described, or None for
    trunk.  The remaining elements are lists of CVSRevisions,
    CVSBranches, and CVSTags based in this branch.

    If cvs_branch_id is specified, it should be the id of a CVSBranch
    item, which will be used as the starting point of the traversal
    (i.e., only the specified branch and its sub-branches will be
    traversed).  Otherwise the traversal will start at the root node."""

    if cvs_branch_id is None:
      cvs_branch = None
      id = self.root_id
    else:
      cvs_branch = self[cvs_branch_id]
      id = cvs_branch.next_id

    cvs_revisions = []
    cvs_branches = []
    cvs_tags = []

    while id is not None:
      cvs_rev = self[id]
      cvs_revisions.append(cvs_rev)

      for branch_id in cvs_rev.branch_ids[:]:
        # Recurse into the branch:
        for lod_info in self.iter_lods(branch_id):
          yield lod_info
        try:
          cvs_branches.append(self[branch_id])
        except KeyError:
          # Branch must have been deleted; just ignore it.
          pass
      for tag_id in cvs_rev.tag_ids:
        cvs_tags.append(self[tag_id])

      id = cvs_rev.next_id

    yield (cvs_branch, cvs_revisions, cvs_branches, cvs_tags)

  def filter_excluded_symbols(self, revision_excluder):
    """Delete any excluded symbols and references to them.

    Call the revision_excluder's callback methods to let it know what
    is being excluded."""

    revision_excluder_started = False
    for (cvs_branch, cvs_revisions, cvs_branches, cvs_tags) \
            in self.iter_lods():
      # Delete any excluded tags:
      for cvs_tag in cvs_tags[:]:
        if isinstance(cvs_tag.symbol, ExcludedSymbol):
          # Notify the revision excluder:
          if not revision_excluder_started:
            revision_excluder.start_file(self.cvs_file)
            revision_excluder_started = True
          revision_excluder.exclude_tag(cvs_tag)

          del self[cvs_tag.id]

          # A CVSTag is the successor of the CVSRevision that it
          # sprouts from.  Delete this tag from that revision's
          # tag_ids:
          self[cvs_tag.rev_id].tag_ids.remove(cvs_tag.id)

          cvs_tags.remove(cvs_tag)

      # Delete the whole branch if it is to be excluded:
      if cvs_branch is None:
        continue

      if isinstance(cvs_branch.symbol, ExcludedSymbol):
        # A symbol can only be excluded if no other symbols spring
        # from it.  This was already checked in CollateSymbolsPass, so
        # these conditions should already be satisfied.
        assert not cvs_branches
        assert not cvs_tags

        # Notify the revision excluder:
        if not revision_excluder_started:
          revision_excluder.start_file(self.cvs_file)
          revision_excluder_started = True
        revision_excluder.exclude_branch(cvs_branch, cvs_revisions)

        del self[cvs_branch.id]

        if cvs_revisions:
          # The first CVSRevision on a branch has to be detached from
          # the revision from which the branch sprang:
          cvs_rev = cvs_revisions[0]
          self[cvs_rev.prev_id].branch_commit_ids.remove(cvs_rev.id)
          for cvs_rev in cvs_revisions:
            del self[cvs_rev.id]
            # If cvs_rev is the last default revision on a non-trunk
            # default branch followed by a 1.2 revision, then the 1.2
            # revision depends on this one.
            if cvs_rev.default_branch_next_id is not None:
              next = self[cvs_rev.default_branch_next_id]
              assert next.default_branch_prev_id == cvs_rev.id
              next.default_branch_prev_id = None

        # A CVSBranch is the successor of the CVSRevision that it
        # sprouts from.  Delete this branch from that revision's
        # branch_ids:
        self[cvs_branch.rev_id].branch_ids.remove(cvs_branch.id)

    if revision_excluder_started:
      revision_excluder.finish_file()
    else:
      revision_excluder.skip_file(self.cvs_file)

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

  def record_closed_symbols(self):
    """Populate CVSRevision.closed_symbol_ids for the surviving revisions."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        cvs_item.closed_symbol_ids = []

    for cvs_item in self.values():
      if not isinstance(cvs_item, CVSRevision):
        continue
      cvs_revision = cvs_item
      if cvs_revision.next_id is None:
        continue
      next_item = self[cvs_revision.next_id]
      cvs_symbols = [
          self[symbol_id]
          for symbol_id in (cvs_revision.tag_ids + cvs_revision.branch_ids)]
      for cvs_symbol in cvs_symbols:
        next_item.closed_symbol_ids.append(cvs_symbol.symbol.id)


