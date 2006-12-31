# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
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

import bisect

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import SVN_INVALID_REVNUM
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_revision_range import SVNRevisionRange


class _RevisionScores:
  """Represent the scores for a range of revisions."""

  def __init__(self, svn_revision_ranges):
    """Initialize based on SVN_REVISION_RANGES.

    SVN_REVISION_RANGES is a list of SVNRevisionRange objects.

    The score of an svn revision is defined to be the number of
    SVNRevisionRanges that include the revision.  A score thus
    indicates that copying the corresponding revision (or any
    following revision up to the next revision in the list) of the
    object in question would yield that many correct paths at or
    underneath the object.  There may be other paths underneath it
    which are not correct and would need to be deleted or recopied;
    those can only be detected by descending and examining their
    scores.

    If SVN_REVISION_RANGES is empty, then all scores are undefined."""

    # A list that looks like:
    #
    #    [(REV1 SCORE1), (REV2 SCORE2), (REV3 SCORE3), ...]
    #
    # where the tuples are sorted by revision number and the revision
    # numbers are distinct.  Score is the number of correct paths that
    # would result from using the specified revision number (or any
    # other revision preceding the next revision listed) as a source.
    # For example, the score of any revision REV in the range REV2 <=
    # REV < REV3 is equal to SCORE2.
    self.scores = []

    # First look for easy out.
    if not svn_revision_ranges:
      return

    # Create lists of opening and closing revisions along with the
    # corresponding delta to the total score:
    openings = [ (x.opening_revnum, +1)
                 for x in svn_revision_ranges ]
    closings = [ (x.closing_revnum, -1)
                 for x in svn_revision_ranges
                 if x.closing_revnum is not None ]

    things = openings + closings
    # Sort by revision number:
    things.sort()
    # Initialize output list with zeroth element of things.  This
    # element must exist, because it was verified that
    # svn_revision_ranges (and therefore openings) is not empty.
    self.scores = [ things[0] ]
    total = things[0][1]
    for (rev, change) in things[1:]:
      total += change
      if rev == self.scores[-1][0]:
        # Same revision as last entry; modify last entry:
        self.scores[-1] = (rev, total)
      else:
        # Previously-unseen revision; create new entry:
        self.scores.append((rev, total))

  def get_score(self, rev):
    """Return the score for svn revision REV.

    If REV doesn't appear explicitly in self.scores, use the score of
    the higest revision preceding REV.  If there are no preceding
    revisions, then the score for REV is unknown; in this case, return
    -1."""

    # Remember, according to the tuple sorting rules,
    #
    #    (rev, anything,) < (rev+1,) < (rev+1, anything,)
    predecessor_index = bisect.bisect(self.scores, (rev+1,)) - 1

    if predecessor_index < 0:
      # raise ValueError('Score for revision %s is unknown' % rev)
      return -1

    return self.scores[predecessor_index][1]

  def get_best_revnum(self):
    """Find the revnum with the highest score.

    Return (revnum, score) for the revnum with the highest score.  If
    the highest score is shared by multiple revisions, select the
    oldest revision."""

    best_revnum = SVN_INVALID_REVNUM
    best_score = 0
    for revnum, score in self.scores:
      if score > best_score:
        best_score = score
        best_revnum = revnum
    return best_revnum, best_score


class FillSource:
  """Representation of a fill source.

  A fill source is a directory (either trunk or a branches
  subdirectory) that can be used as a source for a symbol, along with
  the self-computed score for the source.  FillSources can be
  compared; the comparison is such that it sorts FillSources in
  descending order by score (higher score implies smaller).

  These objects are used by the symbol filler in SVNRepositoryMirror."""

  def __init__(self, symbol, prefix, node, preferred_revnum=None):
    """Create a scored fill source with a prefix and a key."""

    # The Symbol instance for the symbol to be filled:
    self._symbol = symbol

    # The svn path that is the base of this source (e.g.,
    # 'project1/trunk' or 'project1/branches/BRANCH1'):
    self.prefix = prefix

    # The node in the _SymbolFillingGuide corresponding to the prefix
    # path:
    self.node = node

    # SCORE is the score of this source; REVNUM is the revision number
    # with the best score:
    self.revnum, self.score = self._get_best_revnum(preferred_revnum)

  def _get_best_revnum(self, preferred_revnum):
    """Determine the best subversion revision number to use when
    copying the source tree beginning at this source.

    Return (revnum, score) for the best revision found.  If
    PREFERRED_REVNUM is not None and is among the revision numbers
    with the best scores, return it; otherwise, return the oldest such
    revision."""

    # Aggregate openings and closings from our rev tree
    svn_revision_ranges = self._get_revision_ranges(self.node)

    # Score the lists
    revision_scores = _RevisionScores(svn_revision_ranges)

    best_revnum, best_score = revision_scores.get_best_revnum()
    if preferred_revnum is not None \
           and revision_scores.get_score(preferred_revnum) == best_score:
      best_revnum = preferred_revnum

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

  def _get_subsource(self, node, preferred_revnum):
    """Return the FillSource for the specified NODE."""

    return FillSource(self._symbol, self.prefix, node, preferred_revnum)

  def get_subsources(self, preferred_revnum):
    """Generate (entry, FillSource) for all direct subsources."""

    if not isinstance(self.node, SVNRevisionRange):
      for entry, node in self.node.items():
        yield entry, self._get_subsource(node, preferred_revnum)

  def __cmp__(self, other):
    """Comparison operator that sorts FillSources in descending score order.

    If the scores are the same, prefer trunk, or alphabetical order by
    path - these cases are mostly useful to stabilize testsuite
    results."""

    trunk_path = self._symbol.project.trunk_path
    return cmp(other.score, self.score) \
           or cmp(other.prefix == trunk_path, self.prefix == trunk_path) \
           or cmp(self.prefix, other.prefix)


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

  def __init__(self, symbol, openings_closings_map):
    """Initializes a _SymbolFillingGuide for SYMBOL.

    SYMBOL is either a BranchSymbol or a TagSymbol.  Record the
    openings and closings from OPENINGS_CLOSINGS_MAP, which is a map
    {svn_path : SVNRevisionRange} containing the openings and closings
    for svn_paths."""

    self.symbol = symbol

    # The dictionary that holds our root node as a map {
    # path_component : node }.  Subnodes are also dictionaries with
    # the same form.
    self._node_tree = { }

    for svn_path, svn_revision_range in openings_closings_map.items():
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

  def get_sources(self):
    """Return the list of FillSources for this symbolic name.

    The Project instance defines what are legitimate sources
    (basically, the project's trunk or any directory directly under
    its branches path).  Return a list of FillSource objects, one for
    each source that is present in the node tree.  Raise an exception
    if a change occurred outside of the source directories."""

    return list(self._get_sub_sources('', self._node_tree))

  def _get_sub_sources(self, start_svn_path, start_node):
    """Generate the sources within SVN_START_PATH.

    Start the search at path START_SVN_PATH, which is node START_NODE.
    Generate a sequence of FillSource objects.

    This is a helper method, called by get_sources() (see)."""

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


def get_sources(symbol, openings_closings_map):
  return _SymbolFillingGuide(symbol, openings_closings_map).get_sources()


