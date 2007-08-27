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
from cvs2svn_lib.context import Ctx
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

  def __init__(self, cvs_path, symbol, lod, node_tree, preferred_source=None):
    """Create a scored fill source.

    Members:

      _CVS_PATH -- (CVSPath): the CVSPath described by this FillSource.
      _SYMBOL -- (Symbol) the symbol to be filled.
      LOD -- (LineOfDevelopment) is the LOD of the source.
      _NODE_TREE -- (dict) a tree stored as a map { CVSPath : node }, where
          subnodes have the same form.  Leaves are SVNRevisionRange instances
          telling the range of SVN revision numbers from which the CVSPath
          can be copied.
      _PREFERRED_SOURCE -- the source that we should prefer to use, or
          None if there is no preference.
      REVNUM -- (int) the SVN revision number with the best score.
      SCORE -- (int) the score of the best revision number and thus of this
          source.

    """

    self._cvs_path = cvs_path
    self._symbol = symbol
    self.lod = lod
    self._node_tree = node_tree
    self._preferred_source = preferred_source
    self.revnum, self.score = self._get_best_revnum()

  def _get_best_revnum(self):
    """Determine the best subversion revision number to use when
    copying the source tree beginning at this source.

    Return (revnum, score) for the best revision found.  If
    SELF._preferred_source is not None and its revision number is
    among the revision numbers with the best scores, return it;
    otherwise, return the oldest such revision."""

    # Aggregate openings and closings from our rev tree
    svn_revision_ranges = self._get_revision_ranges(self._node_tree)

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

  def _get_subsource(self, cvs_path, node, preferred_source):
    """Return the FillSource for the specified NODE."""

    return FillSource(
        cvs_path, self._symbol, self.lod, node, preferred_source
        )

  def get_subsources(self, preferred_source):
    """Generate (entry, FillSource) for all direct subsources."""

    if not isinstance(self._node_tree, SVNRevisionRange):
      for cvs_path, node in self._node_tree.items():
        yield cvs_path, self._get_subsource(cvs_path, node, preferred_source)

  def __cmp__(self, other):
    """Comparison operator that sorts FillSources in descending score order.

    If the scores are the same, prefer the source that is taken from
    the same branch as its preferred_source; otherwise, prefer the one
    that is on trunk.  If all those are equal then use alphabetical
    order by path (to stabilize testsuite results)."""

    return cmp(other.score, self.score) \
           or cmp(other._preferred_source is not None
                  and other.lod == other._preferred_source.lod,
                  self._preferred_source is not None
                  and self.lod == self._preferred_source.lod) \
           or cmp(self.lod, other.lod)


class FillSourceSet:
  """A set of FillSources for a given symbol and path."""

  def __init__(self, symbol, cvs_path, sources):
    # The symbol that the sources are for:
    self._symbol = symbol

    # The CVSPath that is being processed:
    self.cvs_path = cvs_path

    # A list of sources, sorted in descending order of score.
    self._sources = sources
    self._sources.sort()

  def __nonzero__(self):
    return bool(self._sources)

  def get_best_source(self):
    return self._sources[0]

  def get_subsource_sets(self, preferred_source):
    """Return a FillSourceSet for each subentry that still needs filling.

    The return value is a map {CVSPath : FillSourceSet} for subentries
    that need filling, where CVSPath is a path under the path handled
    by SELF."""

    source_entries = {}
    for source in self._sources:
      for cvs_path, subsource in source.get_subsources(preferred_source):
        source_entries.setdefault(cvs_path, []).append(subsource)

    retval = {}
    for (cvs_path, source_list) in source_entries.items():
      retval[cvs_path.basename] = FillSourceSet(
          self._symbol, cvs_path, source_list
          )

    return retval


class _SymbolFillingGuide:
  """A tree holding the sources that can be copied to fill a symbol.

  The class holds a node tree for each LineOfDevelopment that is the
  source LOD of a CVSSymbol in an SVNCommit.  The directory nodes in
  each tree are dictionaries mapping CVSPaths to subnodes.  A leaf
  node exists for the source of each CVSSymbol, and thus should be
  copied to the symbol in this commit.  The leaves themselves are
  SVNRevisionRange objects telling for what range of revisions the
  leaf could serve as a source.

  self._node_trees holds the root nodes of one directory tree per
  LineOfDevelopment.  By walking self._node_trees and calling
  self._get_best_revnum() on each node, the caller can determine what
  subversion revision number to copy the path corresponding to that
  node from.  self._node_trees should be treated as read-only.

  The caller can then descend to sub-nodes to see if their 'best
  revnum' differs from their parent's and if it does, take appropriate
  actions to 'patch up' the subtrees."""

  def __init__(self, symbol, range_map):
    """Initialize a _SymbolFillingGuide for SYMBOL.

    SYMBOL is either a Branch or a Tag.  Record the openings and
    closings from RANGE_MAP, which is a map { CVSSymbol :
    SVNRevisionRange } containing the openings and closings for
    CVSSymbol instances in a SymbolCommit."""

    self.symbol = symbol

    # A map { LOD : tree } for each LOD, where tree is a map { CVSPath
    # : node }, and subnodes have the same form.  Leaves are
    # SVNRevisionRange instances.
    self._node_trees = { }

    for cvs_symbol, svn_revision_range in range_map.items():
      node_tree = self._node_trees.setdefault(cvs_symbol.source_lod, {})
      cvs_file = cvs_symbol.cvs_file
      parent_node = self._get_node(node_tree, cvs_file.parent_directory)
      parent_node[cvs_file] = svn_revision_range

    #self.print_node_trees()

  def _get_node(self, node_tree, cvs_path):
    """Return the node for CVS_PATH within NODE_TREE.

    NODE_TREE is a node tree as described above.  CVS_PATH is a
    CVSPath instance.  Create new nodes as needed."""

    if cvs_path.parent_directory is None:
      return node_tree
    else:
      parent_node = self._get_node(node_tree, cvs_path.parent_directory)
      return parent_node.setdefault(cvs_path, {})

  def get_source_set(self):
    """Return a FillSourceSet for the root path for this symbolic name.

    Return a FillSourceSet describing each source that is present in
    the node tree."""

    root_cvs_directory = Ctx()._cvs_file_db.get_file(
        self.symbol.project.root_cvs_directory_id
        )
    sources = [
        FillSource(root_cvs_directory, self.symbol, lod, node_tree)
        for (lod, node_tree) in self._node_trees.iteritems()
        ]
    return FillSourceSet(self.symbol, root_cvs_directory, sources)

  def print_node_trees(self):
    print "TREE", "=" * 75
    lods = self._node_trees.keys()
    lods.sort()
    for lod in lods:
      print 'TREE LOD = %s' % (lod,)
      self._print_node_tree(
          self._node_trees[lod],
          Ctx()._cvs_file_db.get_file(
              self.symbol.project.root_cvs_directory_id
              ),
          )
      print "TREE", "-" * 75

  def _print_node_tree(self, node, cvs_directory, indent_depth=0):
    """Print all nodes that are rooted at NODE to sys.stdout.

    INDENT_DEPTH is used to indent the output of recursive calls.
    This method is included for debugging purposes."""

    if isinstance(node, SVNRevisionRange):
      print "TREE:", " " * (indent_depth * 2), cvs_directory, node
    else:
      print "TREE:", " " * (indent_depth * 2), cvs_directory
      for sub_directory, sub_node in node.items():
        self._print_node_tree(sub_node, sub_directory, (indent_depth + 1))


def get_source_set(symbol, range_map):
  """Return a FillSourceSet describing the fill sources for RANGE_MAP.

  RANGE_MAP is a map { CVSSymbol : SVNRevisionRange } as returned by
  SymbolingsReader.get_range_map()."""

  return _SymbolFillingGuide(symbol, range_map).get_source_set()


