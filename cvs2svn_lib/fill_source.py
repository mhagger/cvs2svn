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

"""This module contains classes describing the sources of symbol fills."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import SVN_INVALID_REVNUM
from cvs2svn_lib.svn_revision_range import SVNRevisionRange
from cvs2svn_lib.svn_revision_range import RevisionScores


class FillSource:
  """Representation of a fill source.

  A FillSource keeps track of the paths that have to be filled in a
  particular symbol fill.

  This class holds a SVNRevisionRange instance for each CVSFile that
  has to be filled within the subtree of the repository rooted at
  self.cvs_path.  The SVNRevisionRange objects are stored in a tree
  in which the directory nodes are dictionaries mapping CVSPaths to
  subnodes and the leaf nodes are the SVNRevisionRange objects telling
  for what source_lod and what range of revisions the leaf could serve
  as a source.

  FillSource objects are able to compute the score for arbitrary
  source LODs and source revision numbers.

  These objects are used by the symbol filler in SVNRepositoryMirror."""

  def __init__(self, cvs_path, symbol, node_tree, preferred_range=None):
    """Create a fill source.

    The best LOD and SVN REVNUM to use as the copy source can be
    determined by calling compute_best_revnum().

    Members:

      CVS_PATH -- (CVSPath): the CVSPath described by this FillSource.
      _SYMBOL -- (Symbol) the symbol to be filled.
      _PREFERRED_RANGE -- the SVNRevisionRange that we should prefer
          to use, or None if there is no preference.
      _NODE_TREE -- (dict) a tree stored as a map { CVSPath : node },
          where subnodes have the same form.  Leaves are
          SVNRevisionRange instances telling the source_lod and range
          of SVN revision numbers from which the CVSPath can be
          copied.
      BEST_RANGE -- (SVNRevisionRange) the SVNRevisionRange whose
          source_lod and opening_revision have the best score.  This
          member is set when compute_best_revnum() is called.

    """

    self.cvs_path = cvs_path
    self._symbol = symbol
    self._node_tree = node_tree
    self._preferred_range = preferred_range

  def _set_node(self, cvs_file, svn_revision_range):
    parent_node = self._get_node(cvs_file.parent_directory, create=True)
    if cvs_file in parent_node:
      raise InternalError(
          '%s appeared twice in sources for %s' % (cvs_file, self._symbol)
          )
    parent_node[cvs_file] = svn_revision_range

  def _get_node(self, cvs_path, create=False):
    if cvs_path == self.cvs_path:
      return self._node_tree
    else:
      parent_node = self._get_node(cvs_path.parent_directory, create=create)
      try:
        return parent_node[cvs_path]
      except KeyError:
        if create:
          node = {}
          parent_node[cvs_path] = node
          return node
        else:
          raise

  def compute_best_revnum(self):
    """Determine the best source_lod and subversion revision number to copy.

    Set self.best_range to the best source found.  If
    SELF._preferred_range is not None and its opening is among the
    sources with the best scores, return it; otherwise, return the
    oldest such revision on the first such source_lod (ordered by the
    natural LOD sort order)."""

    # Aggregate openings and closings from our rev tree
    svn_revision_ranges = self._get_revision_ranges(self._node_tree)

    # Score the lists
    revision_scores = RevisionScores(svn_revision_ranges)

    best_source_lod, best_revnum, best_score = \
        revision_scores.get_best_revnum()

    if (
        self._preferred_range is not None
        and revision_scores.get_score(self._preferred_range,) == best_score
        ):
      best_source_lod = self._preferred_range.source_lod
      best_revnum = self._preferred_range.opening_revnum

    if best_revnum == SVN_INVALID_REVNUM:
      raise FatalError(
          "failed to find a revision to copy from when copying %s"
          % self._symbol.name
          )

    self.best_range = SVNRevisionRange(best_source_lod, best_revnum)

  def _get_revision_ranges(self, node):
    """Return a list of all the SVNRevisionRanges at and under NODE.

    Include duplicates.  This is a helper method used by
    compute_best_revnum()."""

    if isinstance(node, SVNRevisionRange):
      # It is a leaf node.
      return [ node ]
    else:
      # It is an intermediate node.
      revision_ranges = []
      for key, subnode in node.items():
        revision_ranges.extend(self._get_revision_ranges(subnode))
      return revision_ranges

  def get_subsources(self, preferred_range):
    """Generate (cvs_path, FillSource) for all direct subsources."""

    if not isinstance(self._node_tree, SVNRevisionRange):
      for cvs_path, node in self._node_tree.items():
        fill_source = FillSource(
            cvs_path, self._symbol, node, preferred_range
            )
        fill_source.compute_best_revnum()
        yield (cvs_path, fill_source)

  def print_tree(self):
    """Print all nodes to sys.stdout.

    This method is included for debugging purposes."""

    print 'TREE LOD = %s' % (self.best_range.source_lod,)
    self._print_subtree(self._node_tree, self.cvs_path, indent_depth=0)
    print 'TREE', '-' * 75

  def _print_subtree(self, node, cvs_path, indent_depth=0):
    """Print all nodes that are rooted at NODE to sys.stdout.

    INDENT_DEPTH is used to indent the output of recursive calls.
    This method is included for debugging purposes."""

    if isinstance(node, SVNRevisionRange):
      print "TREE:", " " * (indent_depth * 2), cvs_path, node
    else:
      print "TREE:", " " * (indent_depth * 2), cvs_path
      for sub_path, sub_node in node.items():
        self._print_subtree(sub_node, sub_path, indent_depth + 1)


def get_source_set(symbol, range_map):
  """Return a FillSource describing the fill sources for RANGE_MAP.

  SYMBOL is either a Branch or a Tag.  RANGE_MAP is a map { CVSSymbol
  : SVNRevisionRange } as returned by
  SymbolingsReader.get_range_map().

  Use the SVNRevisionRanges from RANGE_MAP to create a FillSource
  instance describing the sources for filling SYMBOL."""

  root_cvs_directory = Ctx()._cvs_file_db.get_file(
      symbol.project.root_cvs_directory_id
      )
  fill_source = FillSource(root_cvs_directory, symbol, {})

  for cvs_symbol, svn_revision_range in range_map.items():
    fill_source._set_node(cvs_symbol.cvs_file, svn_revision_range)

  fill_source.compute_best_revnum()

  return fill_source


