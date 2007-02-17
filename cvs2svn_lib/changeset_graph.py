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


class NoPredNodeInGraphException(Exception):
  def __init__(self, node):
    Exception.__init__(self, 'Node %s has no predecessors' % (node,))


class ReachablePredecessors(object):
  """Represent the changesets that a specified changeset depends on.

  We consider direct and indirect dependencies in the sense that the
  changeset can be reached by following a chain of predecessor nodes."""

  def __init__(self, graph, starting_node_id):
    self.graph = graph
    self.starting_node_id = starting_node_id

    # A map {node_id : (steps, next_node_id)} where NODE_ID can be
    # reached from STARTING_NODE_ID in STEPS steps, and NEXT_NODE_ID
    # is the id of the previous node in the path.  STARTING_NODE_ID is
    # only included as a key if there is a loop leading back to it.
    self.reachable_changesets = {}

    # A list of (node_id, steps) that still have to be investigated,
    # and STEPS is the number of steps to get to NODE_ID.
    open_nodes = [(starting_node_id, 0)]
    # A breadth-first search:
    while open_nodes:
      (id, steps) = open_nodes.pop(0)
      steps += 1
      node = self.graph[id]
      for pred_id in node.pred_ids:
        # Since the search is breadth-first, we only have to set steps
        # that don't already exist.
        pred_record = self.reachable_changesets.get(pred_id)
        if pred_record is None:
          self.reachable_changesets[pred_id] = (steps, id)
          open_nodes.append((pred_id, steps))

  def get_path(self, ending_node_id):
    """Return the shortest path from ENDING_NODE_ID to STARTING_NODE_ID.

    Return a list of changesets, where the 0th one has ENDING_NODE_ID
    and the last one has STARTING_NODE_ID.  If there is no such path,
    return None."""

    if ending_node_id not in self.reachable_changesets:
      return None

    path = [Ctx()._changesets_db[ending_node_id]]
    id = self.reachable_changesets[ending_node_id][1]
    while id != self.starting_node_id:
      path.append(Ctx()._changesets_db[id])
      id = self.reachable_changesets[id][1]
    path.append(Ctx()._changesets_db[self.starting_node_id])
    return path

  def __iter__(self):
    """Iterate over all reachable nodes, in path length order.

    Yield (node_id, steps) for each reachable node, where STEPS is the
    number of steps needed to reach the node from starting_node.  The
    nodes are yielded in ascending path-length order.  Nodes that have
    the same path length are yielded in node_id (i.e., essentially
    arbitrary) order."""

    items = self.reachable_changesets.items()
    items.sort(lambda a, b: cmp(a[1][0], b[1][0]))
    for (id, (steps, next_id,)) in items:
      yield (id, steps)


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

  def get_reachable_predecessors(self, id):
    return ReachablePredecessors(self, id)

  def consume_nopred_nodes(self):
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

    def compare((node_1, changeset_1), (node_2, changeset_2)):
      """Define an ordering on nopred_nodes elements."""

      return cmp(node_1.time_range, node_2.time_range) \
             or cmp(changeset_1, changeset_2)

    # Find a list of (node,changeset,) where the node has no
    # predecessors:
    nopred_nodes = [
        (node, node.get_changeset(),)
        for node in self.nodes.itervalues()
        if not node.pred_ids]
    nopred_nodes.sort(compare)
    while nopred_nodes:
      (node, changeset,) = nopred_nodes.pop(0)
      del self[node.id]
      # See if any successors are now ready for extraction:
      new_nodes_found = False
      for succ_id in node.succ_ids:
        succ = self[succ_id]
        if not succ.pred_ids:
          nopred_nodes.append( (succ, succ.get_changeset(),) )
          new_nodes_found = True
      if new_nodes_found:
        # All this repeated sorting is very wasteful.  We should
        # instead use a heap to keep things coming out in order.  But
        # I highly doubt that this will be a bottleneck, so here we
        # go.
        nopred_nodes.sort(compare)
      yield (node.id, node.time_range)

  def find_cycle(self, starting_node_id):
    """Find a cycle in the dependency graph and return it.

    Use STARTING_NODE_ID as the place to start looking.  This routine
    must only be called after all nopred_nodes have been removed.
    Return the list of changesets that are involved in the cycle
    (ordered such that cycle[n-1] is a predecessor of cycle[n] and
    cycle[-1] is a predecessor of cycle[0])."""

    # Since there are no nopred nodes in the graph, all nodes in the
    # graph must either be involved in a cycle or depend (directly or
    # indirectly) on nodes that are in a cycle.

    # Pick an arbitrary node:
    node = self[starting_node_id]

    seen_nodes = [node]

    # Follow it backwards until a node is seen a second time; then we
    # have our cycle.
    while True:
      # Pick an arbitrary predecessor of node.  It must exist, because
      # there are no nopred nodes:
      try:
        node_id = node.pred_ids.__iter__().next()
      except StopIteration:
        raise NoPredNodeInGraphException(node)
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
      for (changeset_id, time_range) in self.consume_nopred_nodes():
        yield (changeset_id, time_range)

      # If there are any nodes left in the graph, then there must be
      # at least one cycle.  Find a cycle and process it.

      # This might raise StopIteration, but that indicates that the
      # graph has been fully consumed, so we just let the exception
      # escape.
      start_node_id = self.nodes.iterkeys().next()

      cycle = self.find_cycle(start_node_id)

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


