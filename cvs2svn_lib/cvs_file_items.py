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


class LODItems(object):
  def __init__(self, lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags):
    # The LineOfDevelopment described by this instance.
    self.lod = lod

    # The CVSBranch starting this LOD, if any; otherwise, None.
    self.cvs_branch = cvs_branch

    # The list of CVSRevisions on this LOD, if any.  The CVSRevisions
    # are listed in dependency order.
    self.cvs_revisions = cvs_revisions

    # A list of CVSBranches that sprout from this LOD (either from
    # cvs_branch or from one of the CVSRevisions).
    self.cvs_branches = cvs_branches

    # A list of CVSTags that sprout from this LOD (either from
    # cvs_branch or from one of the CVSRevisions).
    self.cvs_tags = cvs_tags


class CVSFileItems(object):
  def __init__(self, cvs_file, cvs_items):
    self.cvs_file = cvs_file

    # A map from CVSItem.id to CVSItem:
    self._cvs_items = {}

    # The CVSItem.id of the root CVSItem:
    self.root_id = None

    for cvs_item in cvs_items:
      self.add(cvs_item)
      if not cvs_item.get_pred_ids():
        assert self.root_id is None
        self.root_id = cvs_item.id

    assert self.root_id is not None

  def __getstate__(self):
    return self.values()

  def __setstate__(self, state):
    CVSFileItems.__init__(self, state)

  def __getstate__(self):
    return (self.cvs_file, self.values(),)

  def __setstate__(self, state):
    (cvs_file, cvs_items,) = state
    CVSFileItems.__init__(self, cvs_file, cvs_items)

  def add(self, cvs_item):
    self._cvs_items[cvs_item.id] = cvs_item

  def __getitem__(self, id):
    """Return the CVSItem with the specified ID."""

    return self._cvs_items[id]

  def __delitem__(self, id):
    assert id is not self.root_id
    del self._cvs_items[id]

  def values(self):
    return self._cvs_items.values()

  def _iter_tree(self, lod, cvs_branch, start_id):
    """Iterate over the tree that starts at the specified line of development.

    LOD is the LineOfDevelopment where the iteration should start.
    CVS_BRANCH is the CVSBranch instance that starts the LOD if any;
    otherwise it is None.  ID is the id of the first CVSRevision on
    this LOD, or None if there are none.

    There are two cases handled by this routine: trunk (where LOD is a
    Trunk instance, CVS_BRANCH is None, and ID is the id of the 1.1
    revision) and a branch (where LOD is a Branch instance, CVS_BRANCH
    is a CVSBranch instance, and ID is either the id of the first
    CVSRevision on the branch or None if there are no CVSRevisions on
    the branch).  Note that CVS_BRANCH and ID cannot simultaneously be
    None.

    Yield an LODItems instance for each line of development."""

    cvs_revisions = []
    cvs_branches = []
    cvs_tags = []

    def process_subitems(cvs_item):
      """Process the branches and tags that are rooted in CVS_ITEM.

      CVS_ITEM can be a CVSRevision or a CVSBranch."""

      for branch_id in cvs_item.branch_ids[:]:
        # Recurse into the branch:
        branch = self[branch_id]
        for lod_items in self._iter_tree(
              branch.symbol, branch, branch.next_id
              ):
          yield lod_items
        # The caller might have deleted the branch that we just
        # yielded.  If it is no longer present, then do not add it to
        # the list of cvs_branches.
        try:
          cvs_branches.append(self[branch_id])
        except KeyError:
          pass

      for tag_id in cvs_item.tag_ids:
        cvs_tags.append(self[tag_id])

    if cvs_branch is not None:
      # Include the symbols sprouting directly from the CVSBranch:
      for lod_items in process_subitems(cvs_branch):
        yield lod_items

    id = start_id
    while id is not None:
      cvs_rev = self[id]
      cvs_revisions.append(cvs_rev)

      for lod_items in process_subitems(cvs_rev):
        yield lod_items

      id = cvs_rev.next_id

    yield LODItems(lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags)

  def iter_lods(self):
    """Iterate over LinesOfDevelopment in this file, in depth-first order.

    For each LOD, yield tuples (LOD, CVSBranch, [CVSRevision],
    [CVSBranch], [CVSTag]).  LOD is the LineOfDevelopment holding the
    other items.  CVSBranch is the CVSBranch starting this LOD, if
    any; otherwise it is None.  The remaining elements are lists of
    CVSRevisions, CVSBranches, and CVSTags based in this LOD.  The
    traversal will start at the root node and will return the LODs in
    depth-first order."""

    # This is always the id of a CVSRevision:
    id = self.root_id

    return self._iter_tree(self[id].lod, None, id)

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
    for lod_items in self.iter_lods():

      # (lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags)

      # Delete any excluded tags:
      for cvs_tag in lod_items.cvs_tags[:]:
        if isinstance(cvs_tag.symbol, ExcludedSymbol):
          # Notify the revision excluder:
          if not revision_excluder_started:
            revision_excluder.start_file(self.cvs_file)
            revision_excluder_started = True
          revision_excluder.exclude_tag(cvs_tag)

          self._exclude_tag(cvs_tag)

          lod_items.cvs_tags.remove(cvs_tag)

      # Delete the whole branch if it is to be excluded:
      if isinstance(lod_items.lod, ExcludedSymbol):
        # A symbol can only be excluded if no other symbols spring
        # from it.  This was already checked in CollateSymbolsPass, so
        # these conditions should already be satisfied.
        assert not lod_items.cvs_branches
        assert not lod_items.cvs_tags

        # Notify the revision excluder:
        if not revision_excluder_started:
          revision_excluder.start_file(self.cvs_file)
          revision_excluder_started = True
        revision_excluder.exclude_branch(
            lod_items.cvs_branch, lod_items.cvs_revisions)

        self._exclude_branch(lod_items.cvs_branch, lod_items.cvs_revisions)

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
    self.add(cvs_tag)
    cvs_revision = self[cvs_tag.source_id]
    cvs_revision.branch_ids.remove(cvs_tag.id)
    cvs_revision.tag_ids.append(cvs_tag.id)

  def _mutate_tag_to_branch(self, cvs_tag):
    """Mutate the tag into a branch."""

    cvs_branch = CVSBranch(
        cvs_tag.id, cvs_tag.cvs_file, cvs_tag.symbol,
        None, cvs_tag.source_id, None)
    self.add(cvs_branch)
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

    for lod_items in self.iter_lods():
      for cvs_tag in lod_items.cvs_tags:
        self._adjust_tag_parent(cvs_tag)

      for cvs_branch in lod_items.cvs_branches:
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


