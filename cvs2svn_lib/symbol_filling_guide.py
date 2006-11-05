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

"""This module contains database facilities used by cvs2svn."""


import bisect

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import path_split
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import SVN_INVALID_REVNUM
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_revision_range import SVNRevisionRange
from cvs2svn_lib.fill_source import FillSource


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
    #    [(REV1 SCORE1), (REV2 SCORE2), ...]
    #
    # where the tuples are sorted by revision number and score is the
    # number of correct paths that would result from using the
    # specified revision number as a source.
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


class SymbolFillingGuide:
  """A node tree representing the source paths to be copied to fill a
  symbol in the current SVNCommit.

  self._node_tree is the root of the directory tree, in the form {
  path_component : subnode }.  Leaf nodes are instances of
  SVNRevisionRange.  Intermediate (directory) nodes are dictionaries
  mapping path_components to subnodes.

  By walking self._node_tree and calling self.get_best_revnum() on
  each node, the caller can determine what subversion revision number
  to copy the path corresponding to that node from.  self._node_tree
  should be treated as read-only.

  The caller can then descend to sub-nodes to see if their "best
  revnum" differs from their parents' and if it does, take appropriate
  actions to "patch up" the subtrees."""

  def __init__(self, symbol, openings_closings_map):
    """Initializes a SymbolFillingGuide for SYMBOL and store into it
    the openings and closings from OPENINGS_CLOSINGS_MAP.
    OPENINGS_CLOSINGS_MAP is a map {svn_path : SVNRevisionRange}
    containing the openings and closings for svn_paths."""

    self.symbol = symbol

    # The dictionary that holds our node tree as a map { node_key :
    # node }.
    self._node_tree = { }

    for svn_path, svn_revision_range in openings_closings_map.items():
      (head, tail) = path_split(svn_path)
      self._get_node_for_path(head)[tail] = svn_revision_range

    #self.print_node_tree(self._node_tree)

  def _get_node_for_path(self, svn_path):
    """Return the node key for svn_path, creating new nodes as needed."""

    # Walk down the path, one node at a time.
    node = self._node_tree

    for component in svn_path.split('/'):
      node = node.setdefault(component, {})

    return node

  def get_best_revnum(self, node, preferred_revnum):
    """Determine the best subversion revision number to use when
    copying the source tree beginning at NODE.

    Return (revnum, score) for the best revision found.  If
    PREFERRED_REVNUM is not None and is among the revision numbers
    with the best scores, return it; otherwise, return the oldest such
    revision."""

    # Aggregate openings and closings from the rev tree
    svn_revision_ranges = self._get_revision_ranges(node)

    # Score the lists
    revision_scores = _RevisionScores(svn_revision_ranges)

    best_revnum, best_score = revision_scores.get_best_revnum()
    if preferred_revnum is not None \
           and revision_scores.get_score(preferred_revnum) == best_score:
      best_revnum = preferred_revnum

    if best_revnum == SVN_INVALID_REVNUM:
      raise FatalError(
          "failed to find a revision to copy from when copying %s"
          % self.symbol.name)
    return best_revnum, best_score

  def _get_revision_ranges(self, node):
    """Return a list of all the SVNRevisionRanges at and under NODE.

    Include duplicates."""

    if isinstance(node, SVNRevisionRange):
      # It is a leaf node.
      return [ node ]
    else:
      # It is an intermediate node.
      revision_ranges = []
      for key, subnode in node.items():
        revision_ranges.extend(self._get_revision_ranges(subnode))
      return revision_ranges

  def get_sources(self):
    """Return the list of sources for this symbolic name.

    The Project instance defines what are legitimate sources
    (basically, the project's trunk or any directory directly under
    its branches path).  Raise an exception if a change occurred
    outside of the source directories."""

    return self._get_sub_sources('', self._node_tree)

  def _get_sub_sources(self, start_svn_path, start_node):
    """Return the list of sources within SVN_START_PATH.

    Start the search at path START_SVN_PATH, which is node START_NODE.
    Return a list of FillSource objects.

    This is a helper method, called by get_sources() (see)."""

    if isinstance(start_node, SVNRevisionRange):
      # This implies that a change was found outside of the
      # legitimate sources.  This should never happen.
      raise
    elif self.symbol.project.is_source(start_svn_path):
      # This is a legitimate source.  Add it to list.
      return [ FillSource(self.symbol.project, start_svn_path, start_node) ]
    else:
      # This is a directory that is not a legitimate source.  (That's
      # OK because it hasn't changed directly.)  But directories
      # within it have been changed, so we need to search recursively
      # to find their enclosing sources.
      sources = []
      for entry, node in start_node.items():
        svn_path = path_join(start_svn_path, entry)
        sources.extend(self._get_sub_sources(svn_path, node))

    return sources

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


