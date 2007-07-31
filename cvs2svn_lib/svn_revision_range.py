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

"""This module contains the SVNRevisionRange class."""


import bisect

from cvs2svn_lib.boolean import *

from cvs2svn_lib.common import SVN_INVALID_REVNUM


class SVNRevisionRange:
  """The range of subversion revision numbers from which a path can be
  copied.  self.opening_revnum is the number of the earliest such
  revision, and self.closing_revnum is one higher than the number of
  the last such revision.  If self.closing_revnum is None, then no
  closings were registered."""

  def __init__(self, opening_revnum):
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


class RevisionScores:
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


