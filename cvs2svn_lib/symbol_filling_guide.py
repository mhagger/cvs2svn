# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

"""This module contains classes to help choose symbol sources."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import SVN_INVALID_REVNUM
from cvs2svn_lib.svn_revision_range import SVNRevisionRange
from cvs2svn_lib.svn_revision_range import RevisionScores


class FillSource:
  """Representation of a fill source.

  A fill source is a directory (either trunk or a branches
  subdirectory) that can be used as a source for a symbol, along with
  the self-computed score for the source.  FillSources can be
  compared; the comparison is such that it sorts FillSources in
  descending order by score (higher score implies smaller).

  These objects are used by the symbol filler in SVNRepositoryMirror."""

  def __init__(self, symbol, prefix, node, preferred_source=None):
    """Create a scored fill source with a prefix and a key."""

    # The Symbol instance for the symbol to be filled:
    self._symbol = symbol

    # The svn path that is the base of this source (e.g.,
    # 'project1/trunk' or 'project1/branches/BRANCH1'):
    self.prefix = prefix

    # The node in the _SymbolFillingGuide corresponding to the prefix
    # path:
    self.node = node

    # The source that we should prefer to use, or None if there is no
    # preference:
    self._preferred_source = preferred_source

    # SCORE is the score of this source; REVNUM is the revision number
    # with the best score:
    self.revnum, self.score = self._get_best_revnum()

  def _get_best_revnum(self):
    """Determine the best subversion revision number to use when
    copying the source tree beginning at this source.

    Return (revnum, score) for the best revision found.  If
    SELF._preferred_source is not None and its revision number is
    among the revision numbers with the best scores, return it;
    otherwise, return the oldest such revision."""

    # Aggregate openings and closings from our rev tree
    svn_revision_ranges = self._get_revision_ranges(self.node)

    # Score the lists
    revision_scores = RevisionScores(svn_revision_ranges)

    best_revnum, best_score = revision_scores.get_best_revnum()

    if self._preferred_source is not None \
           and revision_scores.get_score(self._preferred_source.revnum) \
               == best_score:
      best_revnum = self._preferred_source.revnum

    if best_revnum == SVN_INVALID_REVNUM:
      raise FatalError(
          "failed to find a revision to copy from when copying %s"
          % self._symbol.name)
    return best_revnum, best_score

  def _get_revision_ranges(self, node):
    """Return a list of all the SVNRevisionRanges at and under NODE.

    Include duplicates.  This is a helper method used by
    _get_best_revnum()."""

    if isinstance(node, SVNRevisionRange):
      # It is a leaf node.
      return [ node ]
    else:
      # It is an intermediate node.
      revision_ranges = []
      for key, subnode in node.items():
        revision_ranges.extend(self._get_revision_ranges(subnode))
      return revision_ranges

  def _get_subsource(self, node, preferred_source):
    """Return the FillSource for the specified NODE."""

    return FillSource(self._symbol, self.prefix, node, preferred_source)

  def get_subsources(self, preferred_source):
    """Generate (entry, FillSource) for all direct subsources."""

    if not isinstance(self.node, SVNRevisionRange):
      for entry, node in self.node.items():
        yield entry, self._get_subsource(node, preferred_source)

  def __cmp__(self, other):
    """Comparison operator that sorts FillSources in descending score order.

    If the scores are the same, prefer the source that is taken from
    the same branch as its preferred_source; otherwise, prefer the one
    that is on trunk.  If all those are equal then use alphabetical
    order by path (to stabilize testsuite results)."""

    trunk_path = self._symbol.project.trunk_path
    return cmp(other.score, self.score) \
           or cmp(other._preferred_source is not None
                  and other.prefix == other._preferred_source.prefix,
                  self._preferred_source is not None
                  and self.prefix == self._preferred_source.prefix) \
           or cmp(other.prefix == trunk_path, self.prefix == trunk_path) \
           or cmp(self.prefix, other.prefix)


class FillSourceSet:
  """A set of FillSources for a given symbol and path."""

  def __init__(self, symbol, path, sources):
    # The symbol that the sources are for:
    self._symbol = symbol

    # The path, relative to the source base paths, that is being
    # processed:
    self.path = path

    # A list of sources, sorted in descending order of score.
    self._sources = sources
    self._sources.sort()

  def __nonzero__(self):
    return bool(self._sources)

  def get_best_source(self):
    return self._sources[0]

  def get_subsource_sets(self, preferred_source):
    """Return a FillSourceSet for each subentry that still needs filling.

    The return value is a map {entry : FillSourceSet} for subentries
    that need filling, where entry is a path element under the path
    handled by SELF."""

    source_entries = {}
    for source in self._sources:
      for entry, subsource in source.get_subsources(preferred_source):
        source_entries.setdefault(entry, []).append(subsource)

    retval = {}
    for (entry, source_list) in source_entries.items():
      retval[entry] = FillSourceSet(
          self._symbol, path_join(self.path, entry), source_list
          )

    return retval


class _SymbolFillingGuide:
  """A tree holding the sources that can be copied to fill a symbol.

  The class holds a node tree representing any parts of the svn
  directory structure that can be used to incrementally fill the
  symbol in the current SVNCommit.  The directory nodes in the tree
  are dictionaries mapping pathname components to subnodes.  A leaf
  node exists for any potential source that has had an opening since
  the last fill of this symbol, and thus can be filled in this commit.
  The leaves themselves are SVNRevisionRange objects telling for what
  range of revisions the leaf could serve as a source.

  self._node_tree is the root node of the directory tree.  By walking
  self._node_tree and calling self._get_best_revnum() on each node,
  the caller can determine what subversion revision number to copy the
  path corresponding to that node from.  self._node_tree should be
  treated as read-only.

  The caller can then descend to sub-nodes to see if their 'best
  revnum' differs from their parent's and if it does, take appropriate
  actions to 'patch up' the subtrees."""

  def __init__(self, symbol, range_map):
    """Initializes a _SymbolFillingGuide for SYMBOL.

    SYMBOL is either a Branch or a Tag.  Record the openings and
    closings from OPENINGS_CLOSINGS_MAP, which is a map {svn_path :
    SVNRevisionRange} containing the openings and closings for
    svn_paths."""

    self.symbol = symbol

    # The dictionary that holds our root node as a map {
    # path_component : node }.  Subnodes are also dictionaries with
    # the same form.
    self._node_tree = { }

    for cvs_symbol, svn_revision_range in range_map.items():
      svn_path = cvs_symbol.source_lod.get_path(cvs_symbol.cvs_file.cvs_path)
      (head, tail) = path_split(svn_path)
      self._get_node_for_path(head)[tail] = svn_revision_range

    #self.print_node_tree(self._node_tree)

  def _get_node_for_path(self, svn_path):
    """Return the node for svn_path, creating new nodes as needed."""

    # Walk down the path, one node at a time.
    node = self._node_tree

    for component in svn_path.split('/'):
      node = node.setdefault(component, {})

    return node

  def get_source_set(self):
    """Return the list of FillSources for this symbolic name.

    The Project instance defines what are legitimate sources
    (basically, the project's trunk or any directory directly under
    its branches path).  Return a list of FillSource objects, one for
    each source that is present in the node tree.  Raise an exception
    if a change occurred outside of the source directories."""

    return FillSourceSet(
        self.symbol, '', list(self._get_sub_sources('', self._node_tree))
        )

  def _get_sub_sources(self, start_svn_path, start_node):
    """Generate the sources within SVN_START_PATH.

    Start the search at path START_SVN_PATH, which is node START_NODE.
    Generate a sequence of FillSource objects.

    This is a helper method, called by get_source_set() (see)."""

    if isinstance(start_node, SVNRevisionRange):
      # This implies that a change was found outside of the
      # legitimate sources.  This should never happen.
      raise
    elif self.symbol.project.is_source(start_svn_path):
      # This is a legitimate source.  Output it:
      yield FillSource(self.symbol, start_svn_path, start_node)
    else:
      # This is a directory that is not a legitimate source.  (That's
      # OK because it hasn't changed directly.)  But one or more
      # directories within it have been changed, so we need to search
      # recursively to find the sources enclosing them.
      for entry, node in start_node.items():
        svn_path = path_join(start_svn_path, entry)
        for source in self._get_sub_sources(svn_path, node):
          yield source

  def print_node_tree(self, node, name='/', indent_depth=0):
    """Print all nodes in TREE that are rooted at NODE to sys.stdout.

    INDENT_DEPTH is used to indent the output of recursive calls.
    This method is included for debugging purposes."""

    if not indent_depth:
      print "TREE", "=" * 75
    if isinstance(node, SVNRevisionRange):
      print "TREE:", " " * (indent_depth * 2), name, node
    else:
      print "TREE:", " " * (indent_depth * 2), name
      for key, value in node.items():
        self.print_node_tree(value, key, (indent_depth + 1))


def get_source_set(symbol, range_map):
  return _SymbolFillingGuide(symbol, range_map).get_source_set()


