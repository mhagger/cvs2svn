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

"""The changeset dependency graph."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.changeset import RevisionChangeset
from cvs2svn_lib.changeset_graph_node import ChangesetGraphNode


class CycleInGraphException(Exception):
  def __init__(self, cycle):
    Exception.__init__(
        self,
        'Cycle found in graph: %s'
        % ' -> '.join(map(str, cycle + [cycle[0]])))


class ChangesetGraph(object):
  """A graph of changesets and their dependencies."""

  def __init__(self):
    # A map { id : ChangesetGraphNode }
    self.nodes = {}

  def add_changeset(self, changeset):
    """Add CHANGESET to this graph.

    Determine and record any dependencies to changesets that are
    already in the graph."""

    node = changeset.create_graph_node()

    # Now tie the node into our graph.  If a changeset referenced by
    # node is already in our graph, then add the backwards connection
    # from the other node to the new one.  If not, then delete the
    # changeset from node.

    for pred_id in list(node.pred_ids):
      pred_node = self.nodes.get(pred_id)
      if pred_node is not None:
        pred_node.succ_ids.add(node.id)
      else:
        node.pred_ids.remove(pred_id)

    for succ_id in list(node.succ_ids):
      succ_node = self.nodes.get(succ_id)
      if succ_node is not None:
        succ_node.pred_ids.add(node.id)
      else:
        node.succ_ids.remove(succ_id)

    self.nodes[node.id] = node

  def __nonzero__(self):
    """Instances are considered True iff they contain any nodes."""

    return bool(self.nodes)

  def __contains__(self, id):
    """Return True if the specified ID is contained in this graph."""

    return id in self.nodes

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

  def keys(self):
    return self.nodes.keys()

  def __iter__(self):
    return self.nodes.itervalues()

  def _consume_nopred_nodes(self):
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

  def _find_cycle(self):
    """Find a cycle in the dependency graph and return it.

    Return the list of changesets that are involved in the cycle
    (ordered such that cycle[n-1] is a predecessor of cycle[n] and
    cycle[-1] is a predecessor of cycle[0]).  This routine must only
    be called after all nopred_nodes have been removed but the node
    list is not empty."""

    # Since there are no nopred nodes in the graph, all nodes in the
    # graph must either be involved in a cycle or depend (directly or
    # indirectly) on nodes that are in a cycle.  Pick an arbitrary
    # node and follow it backwards until a node is seen a second time;
    # then we have our cycle.
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

  def consume_graph(self, cycle_breaker=None):
    """Remove and yield changesets from this graph in dependency order.

    Each iteration, this generator yields a (changeset_id, time_range)
    tuple for the oldest changeset in the graph that doesn't have any
    predecessor nodes.  If CYCLE_BREAKER is specified, then call
    CYCLE_BREAKER(cycle) whenever a cycle is encountered, where cycle
    is the list of changesets that are involved in the cycle (ordered
    such that cycle[n-1] is a predecessor of cycle[n] and cycle[-1] is
    a predecessor of cycle[0]).  CYCLE_BREAKER should break the cycle
    in place then return.

    If a cycle is found and CYCLE_BREAKER was not specified, raise
    CycleInGraphException."""

    while True:
      for (changeset_id, time_range) in self._consume_nopred_nodes():
        yield (changeset_id, time_range)

      if not self.nodes:
        return

      # There must be a cycle; find and process it:
      cycle = self._find_cycle()
      if cycle_breaker is not None:
        cycle_breaker(cycle)
      else:
        raise CycleInGraphException(cycle)

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    if self.nodes:
      return 'ChangesetGraph:\n%s' \
             % ''.join(['  %r\n' % node for node in self])
    else:
      return 'ChangesetGraph:\n  EMPTY\n'

  def output_coarse_dot(self, f):
    """Output the graph in DOT format to file-like object f.

    Such a file can be rendered into a visual representation of the
    graph using tools like graphviz.  Include only changesets in the
    graph, and the dependencies between changesets."""

    f.write('digraph G {\n')
    for node in self:
      for succ_id in node.succ_ids:
        f.write('  C%x -> C%x\n' % (node.id, succ_id,))
      f.write('\n')
    f.write('}\n')

  def output_fine_dot(self, f):
    """Output the graph in DOT format to file-like object f.

    Such a file can be rendered into a visual representation of the
    graph using tools like graphviz.  Include all CVSItems and the
    CVSItem-CVSItem dependencies in the graph.  Group the CVSItems
    into clusters by changeset."""

    f.write('digraph G {\n')
    for node in self:
      f.write('  subgraph cluster_%x {\n' % (node.id,))
      f.write('    label = "C%x";\n' % (node.id,))
      changeset = Ctx()._changesets_db[node.id]
      for item_id in changeset.cvs_item_ids:
        f.write('    I%x;\n' % (item_id,))
      f.write('  }\n\n')

    for node in self:
      changeset = Ctx()._changesets_db[node.id]
      for cvs_item in changeset.get_cvs_items():
        for succ_id in cvs_item.get_succ_ids():
          f.write('  I%x -> I%x;\n' % (cvs_item.id, succ_id,))

      f.write('\n')

    f.write('}\n')


