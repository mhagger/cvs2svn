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

"""A node in the changeset dependency graph."""


class ChangesetGraphNode(object):
  """A node in the changeset dependency graph."""

  __slots__ = ['id', 'time_range', 'pred_ids', 'succ_ids']

  def __init__(self, changeset, time_range, pred_ids, succ_ids):
    # The id of the ChangesetGraphNode is the same as the id of the
    # changeset.
    self.id = changeset.id

    # The range of times of CVSItems within this Changeset.
    self.time_range = time_range

    # The set of changeset ids of changesets that are direct
    # predecessors of this one.
    self.pred_ids = pred_ids

    # The set of changeset ids of changesets that are direct
    # successors of this one.
    self.succ_ids = succ_ids

  def __repr__(self):
    """For convenience only.  The format is subject to change at any time."""

    return '%x; pred=[%s]; succ=[%s]' % (
        self.id,
        ','.join(['%x' % id for id in self.pred_ids]),
        ','.join(['%x' % id for id in self.succ_ids]),
        )


