# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2007 CollabNet.  All rights reserved.
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
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol
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

  def __getstate__(self):
    return self.values()

  def __setstate__(self, state):
    CVSFileItems.__init__(self, state)

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

  def _exclude_tag(self, cvs_tag):
    """Exclude the specified CVS_TAG."""

    del self[cvs_tag.id]

    # A CVSTag is the successor of the CVSRevision that it
    # sprouts from.  Delete this tag from that revision's
    # tag_ids:
    self[cvs_tag.source_id].tag_ids.remove(cvs_tag.id)

  def _exclude_branch(self, cvs_branch, cvs_revisions):
    """Exclude the specified CVS_BRANCH.

    Also exclude CVS_REVISIONS, which are on CVS_BRANCH."""

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
    self[cvs_branch.source_id].branch_ids.remove(cvs_branch.id)

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

          self._exclude_tag(cvs_tag)

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

        self._exclude_branch(cvs_branch, cvs_revisions)

    if revision_excluder_started:
      revision_excluder.finish_file()
    else:
      revision_excluder.skip_file(self.cvs_file)

  def _mutate_branch_to_tag(self, cvs_branch):
    """Mutate the branch CVS_BRANCH into a tag."""

    if cvs_branch.next_id is not None:
      # This shouldn't happen because it was checked in
      # CollateSymbolsPass:
      raise FatalError('Attempt to exclude a branch with commits.')
    cvs_tag = CVSTag(
        cvs_branch.id, cvs_branch.cvs_file, cvs_branch.symbol,
        cvs_branch.source_id)
    self[cvs_tag.id] = cvs_tag
    cvs_revision = self[cvs_tag.source_id]
    cvs_revision.branch_ids.remove(cvs_tag.id)
    cvs_revision.tag_ids.append(cvs_tag.id)

  def _mutate_tag_to_branch(self, cvs_tag):
    """Mutate the tag into a branch."""

    cvs_branch = CVSBranch(
        cvs_tag.id, cvs_tag.cvs_file, cvs_tag.symbol,
        None, cvs_tag.source_id, None)
    self[cvs_branch.id] = cvs_branch
    cvs_revision = self[cvs_branch.source_id]
    cvs_revision.tag_ids.remove(cvs_branch.id)
    cvs_revision.branch_ids.append(cvs_branch.id)

  def _mutate_symbol(self, cvs_symbol):
    """Mutate CVS_SYMBOL if necessary."""

    symbol = cvs_symbol.symbol
    if isinstance(cvs_symbol, CVSBranch) and isinstance(symbol, Tag):
      self._mutate_branch_to_tag(cvs_symbol)
    elif isinstance(cvs_symbol, CVSTag) and isinstance(symbol, Branch):
      self._mutate_tag_to_branch(cvs_symbol)

  def mutate_symbols(self):
    """Force symbols to be tags/branches based on self.symbol_db."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        # This CVSRevision may be affected by the mutation of any
        # CVSSymbols that it references, but there is nothing to do
        # here directly.
        pass
      elif isinstance(cvs_item, CVSSymbol):
        self._mutate_symbol(cvs_item)
      else:
        raise RuntimeError('Unknown cvs item type')

  def _adjust_tag_parent(self, cvs_tag):
    """Adjust the parent of CVS_TAG if possible and preferred.

    CVS_TAG is an instance of CVSTag.  This method must be called in
    leaf-to-trunk order."""

    # The Symbol that cvs_tag would like to have as a parent:
    preferred_parent = Ctx()._symbol_db.get_symbol(
        cvs_tag.symbol.preferred_parent_id)
    # The CVSRevision that is its direct parent:
    source = self[cvs_tag.source_id]
    assert isinstance(source, CVSRevision)

    if preferred_parent == source.lod:
      # The preferred parent is already the parent.
      return

    if isinstance(preferred_parent, Trunk):
      # It is not possible to graft *onto* Trunk:
      return

    # Try to find the preferred parent among the possible parents:
    for branch_id in source.branch_ids:
      if self[branch_id].symbol == preferred_parent:
        # We found it!
        break
    else:
      # The preferred parent is not a possible parent in this file.
      return

    parent = self[branch_id]
    assert isinstance(parent, CVSBranch)

    Log().debug('Grafting %s from %s (on %s) onto %s' % (
                cvs_tag, source, source.lod, parent,))
    # Switch parent:
    source.tag_ids.remove(cvs_tag.id)
    parent.tag_ids.append(cvs_tag.id)
    cvs_tag.source_id = parent.id

  def _adjust_branch_parents(self, cvs_branch):
    """Adjust the parent of CVS_BRANCH if possible and preferred.

    CVS_BRANCH is an instance of CVSBranch.  This method must be
    called in leaf-to-trunk order."""

    # The Symbol that cvs_branch would like to have as a parent:
    preferred_parent = Ctx()._symbol_db.get_symbol(
        cvs_branch.symbol.preferred_parent_id)
    # The CVSRevision that is its direct parent:
    source = self[cvs_branch.source_id]
    # This is always a CVSRevision because we haven't adjusted it yet:
    assert isinstance(source, CVSRevision)

    if preferred_parent == source.lod:
      # The preferred parent is already the parent.
      return

    if isinstance(preferred_parent, Trunk):
      # It is not possible to graft *onto* Trunk:
      return

    # Try to find the preferred parent among the possible parents:
    for branch_id in source.branch_ids:
      possible_parent = self[branch_id]
      if possible_parent.symbol == preferred_parent:
        # We found it!
        break
      elif possible_parent.symbol == cvs_branch.symbol:
        # Only branches that precede the branch to be adjusted are
        # considered possible parents.  Leave parentage unchanged:
        return
    else:
      # This point should never be reached.
      raise InternalError(
          'Possible parent search did not terminate as expected')

    parent = possible_parent
    assert isinstance(parent, CVSBranch)

    Log().debug('Grafting %s from %s (on %s) onto %s' % (
                cvs_branch, source, source.lod, parent,))
    # Switch parent:
    source.branch_ids.remove(cvs_branch.id)
    parent.branch_ids.append(cvs_branch.id)
    cvs_branch.source_id = parent.id

  def adjust_parents(self):
    """Adjust the parents of symbols to their preferred parents.

    If a CVSSymbol has a preferred parent that is different than its
    current parent, and if the preferred parent is an allowed parent
    of the CVSSymbol in this file, then graft the CVSSymbol onto its
    preferred parent."""

    for (containing_branch, cvs_revisions, cvs_branches, cvs_tags) \
            in self.iter_lods():
      for cvs_tag in cvs_tags:
        self._adjust_tag_parent(cvs_tag)

      for cvs_branch in cvs_branches:
        self._adjust_branch_parents(cvs_branch)

  def record_closed_symbols(self):
    """Populate CVSRevision.closed_symbol_ids for the surviving revisions."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        cvs_item.closed_symbol_ids = []

    for cvs_item in self.values():
      if isinstance(cvs_item, (CVSRevision, CVSBranch)):
        if cvs_item.next_id is None:
          continue
        next_item = self[cvs_item.next_id]
        cvs_symbols = [
            self[symbol_id]
            for symbol_id in (cvs_item.tag_ids + cvs_item.branch_ids)]
        for cvs_symbol in cvs_symbols:
          next_item.closed_symbol_ids.append(cvs_symbol.symbol.id)


