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

"""A node in the changeset dependency graph."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.time_range import TimeRange
from cvs2svn_lib.changeset import RevisionChangeset


class ChangesetGraph(object):
  """A graph of changesets and their dependencies."""

  def __init__(self):
    # A map { id : _ChangesetGraphNode }
    self.nodes = {}

  def add_changeset(self, changeset):
    """Add CHANGESET to this graph.

    Determine and record any dependencies to changesets that are
    already in the graph."""

    node = _ChangesetGraphNode(changeset.id)
    for cvs_item in changeset.get_cvs_items():
      for succ_id in cvs_item.get_succ_ids():
        changeset_id = Ctx()._cvs_item_to_changeset_id[succ_id]
        succ_node = self.nodes.get(changeset_id)
        if succ_node is not None:
          node.succ_ids.add(succ_node.id)
          succ_node.pred_ids.add(node.id)

      for pred_id in cvs_item.get_pred_ids():
        changeset_id = Ctx()._cvs_item_to_changeset_id[pred_id]
        pred_node = self.nodes.get(changeset_id)
        if pred_node is not None:
          node.pred_ids.add(pred_node.id)
          pred_node.succ_ids.add(node.id)

      if isinstance(changeset, RevisionChangeset):
        node.time_range.add(cvs_item.timestamp)

    self.nodes[node.id] = node

  def __getitem__(self, id):
    return self.nodes[id]

  def get(self, id):
    return self.nodes.get(id)

  def __delitem__(self, id):
    """Remove the node corresponding to ID.

    Also remove references to it from other nodes.  This method does
    not change pred_ids or succ_ids of the node being deleted."""

    node = self[id]

    for succ_id in node.succ_ids:
      succ = self[succ_id]
      succ.pred_ids.remove(node.id)

    for pred_id in node.pred_ids:
      pred = self[pred_id]
      pred.succ_ids.remove(node.id)

    del self.nodes[node.id]

  def __iter__(self):
    return self.nodes.itervalues()

  def remove_nopred_nodes(self):
    """Remove and yield changesets in dependency order.

    Each iteration, this generator yields a (changeset_id, time_range)
    tuple for the oldest changeset in the graph that doesn't have any
    predecessor nodes (i.e., it is ready to be committed).  This is
    continued until there are no more nodes without predecessors
    (either because the graph has been emptied, or because of cycles
    in the graph).

    Among the changesets that are ready to be processed, the earliest
    one (according to the sorting of the TimeRange class) is yielded
    each time.  (This is the order in which the changesets should be
    committed.)

    The graph should not be otherwise altered while this generator is
    running."""

    # Find a list of nodes with no predecessors:
    nopred_nodes = [
        node
        for node in self.nodes.itervalues()
        if not node.pred_ids]
    nopred_nodes.sort(lambda a, b: cmp(a.time_range, b.time_range))
    while nopred_nodes:
      node = nopred_nodes.pop(0)
      del self[node.id]
      # See if any successors are now ready for extraction:
      new_nodes_found = False
      for succ_id in node.succ_ids:
        succ = self[succ_id]
        if not succ.pred_ids:
          nopred_nodes.append(succ)
          new_nodes_found = True
      if new_nodes_found:
        # All this repeated sorting is very wasteful.  We should
        # instead use a heap to keep things coming out in order.  But
        # I highly doubt that this will be a bottleneck, so here we
        # go.
        nopred_nodes.sort(lambda a, b: cmp(a.time_range, b.time_range))
      yield (node.id, node.time_range)

  def find_cycle(self):
    """Return a cycle in this graph as a lists of Changesets.

    The cycle is left in the graph.

    This method gradually consumes and destroys the graph: it extracts
    and discards nodes that have no predecessors.

    If there are no cycles left in the graph, return None.  By the
    time this can happen, all of the nodes in the graph will have been
    removed."""

    for (changeset_id, time_range) in self.remove_nopred_nodes():
      pass

    if not self.nodes:
      return None
    # Now all nodes in the graph are involved in a cycle.  Pick an
    # arbitrary node and follow it backwards until a node is seen a
    # second time, then we have our cycle.
    node = self.nodes.itervalues().next()
    seen_nodes = [node]
    while True:
      node_id = node.pred_ids.__iter__().next()
      node = self[node_id]
      try:
        i = seen_nodes.index(node)
      except ValueError:
        seen_nodes.append(node)
      else:
        seen_nodes = seen_nodes[i:]
        seen_nodes.reverse()
        return [Ctx()._changesets_db[node.id] for node in seen_nodes]

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    if self.nodes:
      return 'ChangesetGraph:\n%s' \
             % ''.join(['  %r\n' % node for node in self])
    else:
      return 'ChangesetGraph:\n  EMPTY\n'


class _ChangesetGraphNode(object):
  """A node in the changeset dependency graph."""

  def __init__(self, id):
    self.id = id
    self.time_range = TimeRange()
    self.pred_ids = set()
    self.succ_ids = set()

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%x; pred=[%s]; succ=[%s]' % (
        self.id,
        ','.join(['%x' % id for id in self.pred_ids]),
        ','.join(['%x' % id for id in self.succ_ids]),
        )


