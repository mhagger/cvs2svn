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

"""Keep track of counts of different types of changeset links."""


from __future__ import generators

from cvs2svn_lib.boolean import *


# A cvs_item doesn't depend on any cvs_items in either pred or succ:
LINK_NONE = 0

# A cvs_item depends on one or more cvs_items in pred but none in succ:
LINK_PRED = 1

# A cvs_item depends on one or more cvs_items in succ but none in pred:
LINK_SUCC = 2

# A cvs_item depends on one or more cvs_items in both pred and succ:
LINK_PASSTHRU = LINK_PRED | LINK_SUCC


def _get_link_type(pred, cvs_item, succ):
  """Return the type of links from CVS_ITEM to changesets PRED and SUCC.

  The return value is one of LINK_NONE, LINK_PRED, LINK_SUCC, or
  LINK_PASSTHRU."""

  retval = LINK_NONE
  if cvs_item.get_pred_ids() & pred.cvs_item_ids:
    retval |= LINK_PRED
  if cvs_item.get_succ_ids() & succ.cvs_item_ids:
    retval |= LINK_SUCC
  return retval


class ChangesetGraphLink(object):
  def __init__(self, pred, changeset, succ):
    """Represent a link in a loop in a changeset graph.

    This is the link that goes from PRED -> CHANGESET -> SUCC.

    We are mainly concerned with how many CVSItems have LINK_PRED,
    LINK_SUCC, and LINK_PASSTHRU type links to the neighboring
    commitsets.  If necessary, this class can also break up CHANGESET
    into multiple changesets."""

    self.pred = pred
    self.changeset = changeset
    self.succ = succ

    # A count of each type of link for cvs_items in changeset
    # (indexed by LINK_* constants):
    link_counts = [0] * 4

    for cvs_item in list(changeset.get_cvs_items()):
      link_counts[_get_link_type(self.pred, cvs_item, self.succ)] += 1

    [self.pred_links, self.succ_links, self.passthru_links] = link_counts[1:]

  def get_links_to_move(self):
    """Return the number of items that would be moved to split changeset."""

    return min(self.pred_links, self.succ_links) \
           or max(self.pred_links, self.succ_links)

  def is_breakable(self):
    """Return True iff breaking the changeset will do any good."""

    return self.pred_links != 0 or self.succ_links != 0

  def __cmp__(self, other):
    """Compare SELF with OTHER in terms of which would be better to break.

    The one that is better to break is considered the lesser."""

    return (
        - cmp(int(self.is_breakable()), int(other.is_breakable()))
        or cmp(self.passthru_links, other.passthru_links)
        or cmp(self.get_links_to_move(), other.get_links_to_move())
        )

  def break_changeset(self, changeset_key_generator):
    """Break up self.changeset and return the fragments.

    Break it up in such a way that the link is weakened as efficiently
    as possible."""

    if not self.is_breakable():
      raise ValueError('Changeset is not breakable: %r' % self.changeset)

    if self.pred_links == 0:
      item_type_to_move = LINK_SUCC
    elif self.succ_links == 0:
      item_type_to_move = LINK_PRED
    elif self.pred_links < self.succ_links:
      item_type_to_move = LINK_PRED
    else:
      item_type_to_move = LINK_SUCC
    items_to_keep = []
    items_to_move = []
    for cvs_item in self.changeset.get_cvs_items():
      if _get_link_type(self.pred, cvs_item, self.succ) == item_type_to_move:
        items_to_move.append(cvs_item.id)
      else:
        items_to_keep.append(cvs_item.id)

    # Create new changesets of the same type as the old one:
    return [
        self.changeset.__class__(
            changeset_key_generator.gen_id(), items_to_keep),
        self.changeset.__class__(
            changeset_key_generator.gen_id(), items_to_move),
        ]

  def __str__(self):
    return 'Link<%x>(%d, %d, %d)' % (
        self.changeset.id,
        self.pred_links, self.succ_links, self.passthru_links)


