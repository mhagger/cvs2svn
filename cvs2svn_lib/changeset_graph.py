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

"""The changeset dependency graph."""


from cvs2svn_lib.log import Log
from cvs2svn_lib.changeset import RevisionChangeset
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import BranchChangeset
from cvs2svn_lib.changeset import TagChangeset


class CycleInGraphException(Exception):
  def __init__(self, cycle):
    Exception.__init__(
        self,
        'Cycle found in graph: %s'
        % ' -> '.join(map(str, cycle + [cycle[0]])))


class NoPredNodeInGraphException(Exception):
  def __init__(self, node):
    Exception.__init__(self, 'Node %s has no predecessors' % (node,))


class _NoPredNodes:
  """Manage changesets that are to be processed.

  Output the changesets in order by time and changeset type.

  The implementation of this class is crude: as changesets are added,
  they are appended to a list.  When one is needed, the list is sorted
  in reverse order and then the last changeset in the list is
  returned.  To reduce the number of sorts that are needed, the class
  keeps track of whether the list is currently sorted.

  All this repeated sorting is wasteful and unnecessary.  We should
  instead use a heap to output the changeset order, which would
  require O(lg N) work per add()/get() rather than O(1) and O(N lg N)
  as in the current implementation [1].  But: (1) the lame interface
  of heapq doesn't allow an arbitrary compare function, so we would
  have to store extra information in the array elements; (2) in
  practice, the number of items in the list at any time is only a tiny
  fraction of the total number of changesets; and (3) testing showed
  that the heapq implementation is no faster than this one (perhaps
  because of the increased memory usage).

  [1] According to Objects/listsort.txt in the Python source code, the
  Python list-sorting code is heavily optimized for arrays that have
  runs of already-sorted elements, so the current cost of get() is
  probably closer to O(N) than O(N lg N)."""

  def __init__(self, changeset_db):
    self.changeset_db = changeset_db
    # A list [(node, changeset,)] of nodes with no predecessors:
    self._nodes = []
    self._sorted = True

  def __len__(self):
    return len(self._nodes)

  @staticmethod
  def _compare((node_1, changeset_1), (node_2, changeset_2)):
    """Define a (reverse) ordering on self._nodes."""

    return cmp(node_2.time_range, node_1.time_range) \
           or cmp(changeset_2, changeset_1)

  def add(self, node):
    self._nodes.append( (node, self.changeset_db[node.id],) )
    self._sorted = False

  def get(self):
    """Return (node, changeset,) of the smallest node.

    'Smallest' is defined by self._compare()."""

    if not self._sorted:
      self._nodes.sort(self._compare)
      self._sorted = True
    return self._nodes.pop()


class ChangesetGraph(object):
  """A graph of changesets and their dependencies."""

  def __init__(self, changeset_db, cvs_item_to_changeset_id):
    self._changeset_db = changeset_db
    self._cvs_item_to_changeset_id = cvs_item_to_changeset_id
    # A map { id : ChangesetGraphNode }
    self.nodes = {}

  def close(self):
    self._cvs_item_to_changeset_id.close()
    self._cvs_item_to_changeset_id = None
    self._changeset_db.close()
    self._changeset_db = None

  def add_changeset(self, changeset):
    """Add CHANGESET to this graph.

    Determine and record any dependencies to changesets that are
    already in the graph.  This method does not affect the databases."""

    node = changeset.create_graph_node(self._cvs_item_to_changeset_id)

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

  def store_changeset(self, changeset):
    for cvs_item_id in changeset.cvs_item_ids:
      self._cvs_item_to_changeset_id[cvs_item_id] = changeset.id
    self._changeset_db.store(changeset)

  def add_new_changeset(self, changeset):
    """Add the new CHANGESET to the graph and also to the databases."""

    if Log().is_on(Log.DEBUG):
      Log().debug('Adding changeset %r' % (changeset,))

    self.add_changeset(changeset)
    self.store_changeset(changeset)

  def delete_changeset(self, changeset):
    """Remove CHANGESET from the graph and also from the databases.

    In fact, we don't remove CHANGESET from
    self._cvs_item_to_changeset_id, because in practice the CVSItems
    in CHANGESET are always added again as part of a new CHANGESET,
    which will cause the old values to be overwritten."""

    if Log().is_on(Log.DEBUG):
      Log().debug('Removing changeset %r' % (changeset,))

    del self[changeset.id]
    del self._changeset_db[changeset.id]

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
    not change pred_ids or succ_ids of the node being deleted, nor
    does it affect the databases."""

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

  def _get_path(self, reachable_changesets, starting_node_id, ending_node_id):
    """Return the shortest path from ENDING_NODE_ID to STARTING_NODE_ID.

    Find a path from ENDING_NODE_ID to STARTING_NODE_ID in
    REACHABLE_CHANGESETS, where STARTING_NODE_ID is the id of a
    changeset that depends on the changeset with ENDING_NODE_ID.  (See
    the comment in search_for_path() for a description of the format
    of REACHABLE_CHANGESETS.)

    Return a list of changesets, where the 0th one has ENDING_NODE_ID
    and the last one has STARTING_NODE_ID.  If there is no such path
    described in in REACHABLE_CHANGESETS, return None."""

    if ending_node_id not in reachable_changesets:
      return None

    path = [self._changeset_db[ending_node_id]]
    id = reachable_changesets[ending_node_id][1]
    while id != starting_node_id:
      path.append(self._changeset_db[id])
      id = reachable_changesets[id][1]
    path.append(self._changeset_db[starting_node_id])
    return path

  def search_for_path(self, starting_node_id, stop_set):
    """Search for paths to prerequisites of STARTING_NODE_ID.

    Try to find the shortest dependency path that causes the changeset
    with STARTING_NODE_ID to depend (directly or indirectly) on one of
    the changesets whose ids are contained in STOP_SET.

    We consider direct and indirect dependencies in the sense that the
    changeset can be reached by following a chain of predecessor nodes.

    When one of the changeset_ids in STOP_SET is found, terminate the
    search and return the path from that changeset_id to
    STARTING_NODE_ID.  If no path is found to a node in STOP_SET,
    return None."""

    # A map {node_id : (steps, next_node_id)} where NODE_ID can be
    # reached from STARTING_NODE_ID in STEPS steps, and NEXT_NODE_ID
    # is the id of the previous node in the path.  STARTING_NODE_ID is
    # only included as a key if there is a loop leading back to it.
    reachable_changesets = {}

    # A list of (node_id, steps) that still have to be investigated,
    # and STEPS is the number of steps to get to NODE_ID.
    open_nodes = [(starting_node_id, 0)]
    # A breadth-first search:
    while open_nodes:
      (id, steps) = open_nodes.pop(0)
      steps += 1
      node = self[id]
      for pred_id in node.pred_ids:
        # Since the search is breadth-first, we only have to set steps
        # that don't already exist.
        if pred_id not in reachable_changesets:
          reachable_changesets[pred_id] = (steps, id)
          open_nodes.append((pred_id, steps))

          # See if we can stop now:
          if pred_id in stop_set:
            return self._get_path(
                reachable_changesets, starting_node_id, pred_id
                )

    return None

  def consume_nopred_nodes(self):
    """Remove and yield changesets in dependency order.

    Each iteration, this generator yields a (changeset, time_range)
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

    # Find a list of (node,changeset,) where the node has no
    # predecessors:
    nopred_nodes = _NoPredNodes(self._changeset_db)
    for node in self.nodes.itervalues():
      if not node.pred_ids:
        nopred_nodes.add(node)

    while nopred_nodes:
      (node, changeset,) = nopred_nodes.get()
      del self[node.id]
      # See if any successors are now ready for extraction:
      for succ_id in node.succ_ids:
        succ = self[succ_id]
        if not succ.pred_ids:
          nopred_nodes.add(succ)
      yield (changeset, node.time_range)

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
        return [self._changeset_db[node.id] for node in seen_nodes]

  def consume_graph(self, cycle_breaker=None):
    """Remove and yield changesets from this graph in dependency order.

    Each iteration, this generator yields a (changeset, time_range)
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
      for (changeset, time_range) in self.consume_nopred_nodes():
        yield (changeset, time_range)

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

  node_colors = {
      RevisionChangeset : 'lightgreen',
      OrderedChangeset : 'cyan',
      BranchChangeset : 'orange',
      TagChangeset : 'yellow',
      }

  def output_coarse_dot(self, f):
    """Output the graph in DOT format to file-like object f.

    Such a file can be rendered into a visual representation of the
    graph using tools like graphviz.  Include only changesets in the
    graph, and the dependencies between changesets."""

    f.write('digraph G {\n')
    for node in self:
      f.write(
          '  C%x [style=filled, fillcolor=%s];\n' % (
              node.id,
              self.node_colors[self._changeset_db[node.id].__class__],
              )
          )
    f.write('\n')

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
      changeset = self._changeset_db[node.id]
      for item_id in changeset.cvs_item_ids:
        f.write('    I%x;\n' % (item_id,))
      f.write('    style=filled;\n')
      f.write(
          '    fillcolor=%s;\n'
          % (self.node_colors[self._changeset_db[node.id].__class__],))
      f.write('  }\n\n')

    for node in self:
      changeset = self._changeset_db[node.id]
      for cvs_item in changeset.iter_cvs_items():
        for succ_id in cvs_item.get_succ_ids():
          f.write('  I%x -> I%x;\n' % (cvs_item.id, succ_id,))

      f.write('\n')

    f.write('}\n')


