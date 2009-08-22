# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2008 CollabNet.  All rights reserved.
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


from cvs2svn_lib.common import InternalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.time_range import TimeRange
from cvs2svn_lib.changeset_graph_node import ChangesetGraphNode


class Changeset(object):
  """A set of cvs_items that might potentially form a single change set."""

  def __init__(self, id, cvs_item_ids):
    self.id = id
    self.cvs_item_ids = list(cvs_item_ids)

  def iter_cvs_items(self):
    """Yield the CVSItems within this Changeset."""

    for (id, cvs_item) in Ctx()._cvs_items_db.get_many(self.cvs_item_ids):
      assert cvs_item is not None
      yield cvs_item

  def get_projects_opened(self):
    """Return the set of projects that might be opened by this changeset."""

    raise NotImplementedError()

  def create_graph_node(self, cvs_item_to_changeset_id):
    """Return a ChangesetGraphNode for this Changeset."""

    raise NotImplementedError()

  def create_split_changeset(self, id, cvs_item_ids):
    """Return a Changeset with the specified contents.

    This method is only implemented for changesets that can be split.
    The type of the new changeset should be the same as that of SELF,
    and any other information from SELF should also be copied to the
    new changeset."""

    raise NotImplementedError()

  def __getstate__(self):
    return (self.id, self.cvs_item_ids,)

  def __setstate__(self, state):
    (self.id, self.cvs_item_ids,) = state

  def __cmp__(self, other):
    raise NotImplementedError()

  def __str__(self):
    raise NotImplementedError()

  def __repr__(self):
    return '%s [%s]' % (
        self, ', '.join(['%x' % id for id in self.cvs_item_ids]),)


class RevisionChangeset(Changeset):
  """A Changeset consisting of CVSRevisions."""

  _sort_order = 3

  def create_graph_node(self, cvs_item_to_changeset_id):
    time_range = TimeRange()
    pred_ids = set()
    succ_ids = set()

    for cvs_item in self.iter_cvs_items():
      time_range.add(cvs_item.timestamp)

      for pred_id in cvs_item.get_pred_ids():
        changeset_id = cvs_item_to_changeset_id.get(pred_id)
        if changeset_id is not None:
          pred_ids.add(changeset_id)

      for succ_id in cvs_item.get_succ_ids():
        changeset_id = cvs_item_to_changeset_id.get(succ_id)
        if changeset_id is not None:
          succ_ids.add(changeset_id)

    return ChangesetGraphNode(self, time_range, pred_ids, succ_ids)

  def create_split_changeset(self, id, cvs_item_ids):
    return RevisionChangeset(id, cvs_item_ids)

  def __cmp__(self, other):
    return cmp(self._sort_order, other._sort_order) \
           or cmp(self.id, other.id)

  def __str__(self):
    return 'RevisionChangeset<%x>' % (self.id,)


class OrderedChangeset(Changeset):
  """A Changeset of CVSRevisions whose preliminary order is known.

  The first changeset ordering involves only RevisionChangesets, and
  results in a full ordering of RevisionChangesets (i.e., a linear
  chain of dependencies with the order consistent with the
  dependencies).  These OrderedChangesets form the skeleton for the
  full topological sort that includes SymbolChangesets as well."""

  _sort_order = 2

  def __init__(self, id, cvs_item_ids, ordinal, prev_id, next_id):
    Changeset.__init__(self, id, cvs_item_ids)

    # The order of this changeset among all OrderedChangesets:
    self.ordinal = ordinal

    # The changeset id of the previous OrderedChangeset, or None if
    # this is the first OrderedChangeset:
    self.prev_id = prev_id

    # The changeset id of the next OrderedChangeset, or None if this
    # is the last OrderedChangeset:
    self.next_id = next_id

  def get_projects_opened(self):
    retval = set()
    for cvs_item in self.iter_cvs_items():
      retval.add(cvs_item.cvs_file.project)
    return retval

  def create_graph_node(self, cvs_item_to_changeset_id):
    time_range = TimeRange()

    pred_ids = set()
    succ_ids = set()

    if self.prev_id is not None:
      pred_ids.add(self.prev_id)

    if self.next_id is not None:
      succ_ids.add(self.next_id)

    for cvs_item in self.iter_cvs_items():
      time_range.add(cvs_item.timestamp)

      for pred_id in cvs_item.get_symbol_pred_ids():
        changeset_id = cvs_item_to_changeset_id.get(pred_id)
        if changeset_id is not None:
          pred_ids.add(changeset_id)

      for succ_id in cvs_item.get_symbol_succ_ids():
        changeset_id = cvs_item_to_changeset_id.get(succ_id)
        if changeset_id is not None:
          succ_ids.add(changeset_id)

    return ChangesetGraphNode(self, time_range, pred_ids, succ_ids)

  def __getstate__(self):
    return (
        Changeset.__getstate__(self),
        self.ordinal, self.prev_id, self.next_id,)

  def __setstate__(self, state):
    (changeset_state, self.ordinal, self.prev_id, self.next_id,) = state
    Changeset.__setstate__(self, changeset_state)

  def __cmp__(self, other):
    return cmp(self._sort_order, other._sort_order) \
           or cmp(self.id, other.id)

  def __str__(self):
    return 'OrderedChangeset<%x(%d)>' % (self.id, self.ordinal,)


class SymbolChangeset(Changeset):
  """A Changeset consisting of CVSSymbols."""

  def __init__(self, id, symbol, cvs_item_ids):
    Changeset.__init__(self, id, cvs_item_ids)
    self.symbol = symbol

  def get_projects_opened(self):
    # A SymbolChangeset can never open a project.
    return set()

  def create_graph_node(self, cvs_item_to_changeset_id):
    pred_ids = set()
    succ_ids = set()

    for cvs_item in self.iter_cvs_items():
      for pred_id in cvs_item.get_pred_ids():
        changeset_id = cvs_item_to_changeset_id.get(pred_id)
        if changeset_id is not None:
          pred_ids.add(changeset_id)

      for succ_id in cvs_item.get_succ_ids():
        changeset_id = cvs_item_to_changeset_id.get(succ_id)
        if changeset_id is not None:
          succ_ids.add(changeset_id)

    return ChangesetGraphNode(self, TimeRange(), pred_ids, succ_ids)

  def __cmp__(self, other):
    return cmp(self._sort_order, other._sort_order) \
           or cmp(self.symbol, other.symbol) \
           or cmp(self.id, other.id)

  def __getstate__(self):
    return (Changeset.__getstate__(self), self.symbol.id,)

  def __setstate__(self, state):
    (changeset_state, symbol_id) = state
    Changeset.__setstate__(self, changeset_state)
    self.symbol = Ctx()._symbol_db.get_symbol(symbol_id)


class BranchChangeset(SymbolChangeset):
  """A Changeset consisting of CVSBranches."""

  _sort_order = 1

  def create_split_changeset(self, id, cvs_item_ids):
    return BranchChangeset(id, self.symbol, cvs_item_ids)

  def __str__(self):
    return 'BranchChangeset<%x>("%s")' % (self.id, self.symbol,)


class TagChangeset(SymbolChangeset):
  """A Changeset consisting of CVSTags."""

  _sort_order = 0

  def create_split_changeset(self, id, cvs_item_ids):
    return TagChangeset(id, self.symbol, cvs_item_ids)

  def __str__(self):
    return 'TagChangeset<%x>("%s")' % (self.id, self.symbol,)


def create_symbol_changeset(id, symbol, cvs_item_ids):
  """Factory function for SymbolChangesets.

  Return a BranchChangeset or TagChangeset, depending on the type of
  SYMBOL.  SYMBOL must be a Branch or Tag."""

  if isinstance(symbol, Branch):
    return BranchChangeset(id, symbol, cvs_item_ids)
  if isinstance(symbol, Tag):
    return TagChangeset(id, symbol, cvs_item_ids)
  else:
    raise InternalError('Unknown symbol type %s' % (symbol,))


