# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

"""This module contains the SVNRevisionRange class."""


import bisect

from cvs2svn_lib.common import SVN_INVALID_REVNUM


class SVNRevisionRange:
  """The range of subversion revision numbers from which a path can be
  copied.  self.opening_revnum is the number of the earliest such
  revision, and self.closing_revnum is one higher than the number of
  the last such revision.  If self.closing_revnum is None, then no
  closings were registered."""

  def __init__(self, source_lod, opening_revnum):
    self.source_lod = source_lod
    self.opening_revnum = opening_revnum
    self.closing_revnum = None

  def add_closing(self, closing_revnum):
    # When we have a non-trunk default branch, we may have multiple
    # closings--only register the first closing we encounter.
    if self.closing_revnum is None:
      self.closing_revnum = closing_revnum

  def __contains__(self, revnum):
    """Return True iff REVNUM is contained in the range."""

    return (
        self.opening_revnum <= revnum \
        and (self.closing_revnum is None or revnum < self.closing_revnum)
        )

  def __str__(self):
    if self.closing_revnum is None:
      return '[%d:]' % (self.opening_revnum,)
    else:
      return '[%d:%d]' % (self.opening_revnum, self.closing_revnum,)

  def __repr__(self):
    return str(self)


class RevisionScores:
  """Represent the scores for a range of revisions."""

  def __init__(self, svn_revision_ranges):
    """Initialize based on SVN_REVISION_RANGES.

    SVN_REVISION_RANGES is a list of SVNRevisionRange objects.

    The score of an svn source is defined to be the number of
    SVNRevisionRanges on that LOD that include the revision.  A score
    thus indicates that copying the corresponding revision (or any
    following revision up to the next revision in the list) of the
    object in question would yield that many correct paths at or
    underneath the object.  There may be other paths underneath it
    that are not correct and would need to be deleted or recopied;
    those can only be detected by descending and examining their
    scores.

    If SVN_REVISION_RANGES is empty, then all scores are undefined."""

    deltas_map = {}

    for range in svn_revision_ranges:
      source_lod = range.source_lod
      try:
        deltas = deltas_map[source_lod]
      except:
        deltas = []
        deltas_map[source_lod] = deltas
      deltas.append((range.opening_revnum, +1))
      if range.closing_revnum is not None:
        deltas.append((range.closing_revnum, -1))

    # A map:
    #
    #    {SOURCE_LOD : [(REV1 SCORE1), (REV2 SCORE2), (REV3 SCORE3), ...]}
    #
    # where the tuples are sorted by revision number and the revision
    # numbers are distinct.  Score is the number of correct paths that
    # would result from using the specified SOURCE_LOD and revision
    # number (or any other revision preceding the next revision
    # listed) as a source.  For example, the score of any revision REV
    # in the range REV2 <= REV < REV3 is equal to SCORE2.
    self._scores_map = {}

    for (source_lod,deltas) in deltas_map.items():
      # Sort by revision number:
      deltas.sort()

      # Initialize output list with zeroth element of deltas.  This
      # element must exist, because it was verified that
      # svn_revision_ranges (and therefore openings) is not empty.
      scores = [ deltas[0] ]
      total = deltas[0][1]
      for (rev, change) in deltas[1:]:
        total += change
        if rev == scores[-1][0]:
          # Same revision as last entry; modify last entry:
          scores[-1] = (rev, total)
        else:
          # Previously-unseen revision; create new entry:
          scores.append((rev, total))
      self._scores_map[source_lod] = scores

  def get_score(self, range):
    """Return the score for RANGE's opening revision.

    If RANGE doesn't appear explicitly in self.scores, use the score
    of the higest revision preceding RANGE.  If there are no preceding
    revisions, then the score for RANGE is unknown; in this case,
    return -1."""

    try:
      scores = self._scores_map[range.source_lod]
    except KeyError:
      return -1

    # Remember, according to the tuple sorting rules,
    #
    #    (revnum, anything,) < (revnum+1,) < (revnum+1, anything,)
    predecessor_index = bisect.bisect_right(
        scores, (range.opening_revnum + 1,)
        ) - 1

    if predecessor_index < 0:
      return -1

    return scores[predecessor_index][1]

  def get_best_revnum(self):
    """Find the revnum with the highest score.

    Return (revnum, score) for the revnum with the highest score.  If
    the highest score is shared by multiple revisions, select the
    oldest revision."""

    best_source_lod = None
    best_revnum = SVN_INVALID_REVNUM
    best_score = 0

    source_lods = self._scores_map.keys()
    source_lods.sort()
    for source_lod in source_lods:
      for revnum, score in self._scores_map[source_lod]:
        if score > best_score:
          best_source_lod = source_lod
          best_score = score
          best_revnum = revnum
    return best_source_lod, best_revnum, best_score


