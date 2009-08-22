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

"""Keep track of counts of different types of changeset links."""



# A cvs_item doesn't depend on any cvs_items in either pred or succ:
LINK_NONE = 0

# A cvs_item depends on one or more cvs_items in pred but none in succ:
LINK_PRED = 1

# A cvs_item depends on one or more cvs_items in succ but none in pred:
LINK_SUCC = 2

# A cvs_item depends on one or more cvs_items in both pred and succ:
LINK_PASSTHRU = LINK_PRED | LINK_SUCC


class ChangesetGraphLink(object):
  def __init__(self, pred, changeset, succ):
    """Represent a link in a loop in a changeset graph.

    This is the link that goes from PRED -> CHANGESET -> SUCC.

    We are mainly concerned with how many CVSItems have LINK_PRED,
    LINK_SUCC, and LINK_PASSTHRU type links to the neighboring
    commitsets.  If necessary, this class can also break up CHANGESET
    into multiple changesets."""

    self.pred = pred
    self.pred_ids = set(pred.cvs_item_ids)

    self.changeset = changeset

    self.succ_ids = set(succ.cvs_item_ids)
    self.succ = succ

    # A count of each type of link for cvs_items in changeset
    # (indexed by LINK_* constants):
    link_counts = [0] * 4

    for cvs_item in list(changeset.iter_cvs_items()):
      link_counts[self.get_link_type(cvs_item)] += 1

    [self.pred_links, self.succ_links, self.passthru_links] = link_counts[1:]

  def get_link_type(self, cvs_item):
    """Return the type of links from CVS_ITEM to self.PRED and self.SUCC.

    The return value is one of LINK_NONE, LINK_PRED, LINK_SUCC, or
    LINK_PASSTHRU."""

    retval = LINK_NONE

    if cvs_item.get_pred_ids() & self.pred_ids:
      retval |= LINK_PRED
    if cvs_item.get_succ_ids() & self.succ_ids:
      retval |= LINK_SUCC

    return retval

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

    pred_items = []
    succ_items = []

    # For each link type, should such CVSItems be moved to the
    # changeset containing the predecessor items or the one containing
    # the successor items?
    destination = {
        LINK_PRED : pred_items,
        LINK_SUCC : succ_items,
        }

    if self.pred_links == 0:
      destination[LINK_NONE] = pred_items
      destination[LINK_PASSTHRU] = pred_items
    elif self.succ_links == 0:
      destination[LINK_NONE] = succ_items
      destination[LINK_PASSTHRU] = succ_items
    elif self.pred_links < self.succ_links:
      destination[LINK_NONE] = succ_items
      destination[LINK_PASSTHRU] = succ_items
    else:
      destination[LINK_NONE] = pred_items
      destination[LINK_PASSTHRU] = pred_items

    for cvs_item in self.changeset.iter_cvs_items():
      link_type = self.get_link_type(cvs_item)
      destination[link_type].append(cvs_item.id)

    # Create new changesets of the same type as the old one:
    return [
        self.changeset.create_split_changeset(
            changeset_key_generator.gen_id(), pred_items),
        self.changeset.create_split_changeset(
            changeset_key_generator.gen_id(), succ_items),
        ]

  def __str__(self):
    return 'Link<%x>(%d, %d, %d)' % (
        self.changeset.id,
        self.pred_links, self.succ_links, self.passthru_links)


