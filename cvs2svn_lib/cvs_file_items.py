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

"""This module contains a class to manage the CVSItems related to one file."""


import re

from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import logger
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.symbol import ExcludedSymbol
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSRevisionModification
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionAbsent
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.cvs_item import cvs_revision_type_map
from cvs2svn_lib.cvs_item import cvs_branch_type_map
from cvs2svn_lib.cvs_item import cvs_tag_type_map


class VendorBranchError(Exception):
  """There is an error in the structure of the file revision tree."""

  pass


class LODItems(object):
  def __init__(self, lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags):
    # The LineOfDevelopment described by this instance.
    self.lod = lod

    # The CVSBranch starting this LOD, if any; otherwise, None.
    self.cvs_branch = cvs_branch

    # The list of CVSRevisions on this LOD, if any.  The CVSRevisions
    # are listed in dependency order.
    self.cvs_revisions = cvs_revisions

    # A list of CVSBranches that sprout from this LOD (either from
    # cvs_branch or from one of the CVSRevisions).
    self.cvs_branches = cvs_branches

    # A list of CVSTags that sprout from this LOD (either from
    # cvs_branch or from one of the CVSRevisions).
    self.cvs_tags = cvs_tags

  def is_trivial_import(self):
    """Return True iff this LOD is a trivial import branch in this file.

    A trivial import branch is a branch that was used for a single
    import and nothing else.  Such a branch is eligible for being
    grafted onto trunk, even if it has branch blockers."""

    return (
        len(self.cvs_revisions) == 1
        and self.cvs_revisions[0].ntdbr
        )

  def is_pure_ntdb(self):
    """Return True iff this LOD is a pure NTDB in this file.

    A pure non-trunk default branch is defined to be a branch that
    contains only NTDB revisions (and at least one of them).  Such a
    branch is eligible for being grafted onto trunk, even if it has
    branch blockers."""

    return (
        self.cvs_revisions
        and self.cvs_revisions[-1].ntdbr
        )

  def iter_blockers(self):
    if self.is_pure_ntdb():
      # Such a branch has no blockers, because the blockers can be
      # grafted to trunk.
      pass
    else:
      # Other branches are only blocked by symbols that sprout from
      # non-NTDB revisions:
      non_ntdbr_revision_ids = set()
      for cvs_revision in self.cvs_revisions:
        if not cvs_revision.ntdbr:
          non_ntdbr_revision_ids.add(cvs_revision.id)

      for cvs_tag in self.cvs_tags:
        if cvs_tag.source_id in non_ntdbr_revision_ids:
          yield cvs_tag

      for cvs_branch in self.cvs_branches:
        if cvs_branch.source_id in non_ntdbr_revision_ids:
          yield cvs_branch


class CVSFileItems(object):
  def __init__(self, cvs_file, trunk, cvs_items, original_ids=None):
    # The file whose data this instance holds.
    self.cvs_file = cvs_file

    # The symbol that represents "Trunk" in this file.
    self.trunk = trunk

    # A map from CVSItem.id to CVSItem:
    self._cvs_items = {}

    # The cvs_item_id of each root in the CVSItem forest.  (A root is
    # defined to be any CVSRevision with no prev_id.)
    self.root_ids = set()

    for cvs_item in cvs_items:
      self.add(cvs_item)
      if isinstance(cvs_item, CVSRevision) and cvs_item.prev_id is None:
        self.root_ids.add(cvs_item.id)

    # self.original_ids is a dict {cvs_rev.rev : cvs_rev.id} holding
    # the IDs originally allocated to each CVS revision number.  This
    # member is stored for the convenience of RevisionCollectors.
    if original_ids is not None:
      self.original_ids = original_ids
    else:
      self.original_ids = {}
      for cvs_item in cvs_items:
        if isinstance(cvs_item, CVSRevision):
          self.original_ids[cvs_item.rev] = cvs_item.id

  def __getstate__(self):
    return (self.cvs_file.id, self.values(), self.original_ids,)

  def __setstate__(self, state):
    (cvs_file_id, cvs_items, original_ids,) = state
    cvs_file = Ctx()._cvs_path_db.get_path(cvs_file_id)
    CVSFileItems.__init__(
        self, cvs_file, cvs_file.project.get_trunk(), cvs_items,
        original_ids=original_ids,
        )

  def add(self, cvs_item):
    self._cvs_items[cvs_item.id] = cvs_item

  def __getitem__(self, id):
    """Return the CVSItem with the specified ID."""

    return self._cvs_items[id]

  def get(self, id, default=None):
    return self._cvs_items.get(id, default)

  def __delitem__(self, id):
    assert id not in self.root_ids
    del self._cvs_items[id]

  def values(self):
    return self._cvs_items.values()

  def check_link_consistency(self):
    """Check that the CVSItems are linked correctly with each other."""

    for cvs_item in self.values():
      try:
        cvs_item.check_links(self)
      except AssertionError:
        logger.error(
            'Link consistency error in %s\n'
            'This is probably a bug internal to cvs2svn.  Please file a bug\n'
            'report including the following stack trace (see FAQ for more '
            'info).'
            % (cvs_item,))
        raise

  def _get_lod(self, lod, cvs_branch, start_id):
    """Return the indicated LODItems.

    LOD is the corresponding LineOfDevelopment.  CVS_BRANCH is the
    CVSBranch instance that starts the LOD if any; otherwise it is
    None.  START_ID is the id of the first CVSRevision on this LOD, or
    None if there are none."""

    cvs_revisions = []
    cvs_branches = []
    cvs_tags = []

    def process_subitems(cvs_item):
      """Process the branches and tags that are rooted in CVS_ITEM.

      CVS_ITEM can be a CVSRevision or a CVSBranch."""

      for branch_id in cvs_item.branch_ids[:]:
        cvs_branches.append(self[branch_id])

      for tag_id in cvs_item.tag_ids:
        cvs_tags.append(self[tag_id])

    if cvs_branch is not None:
      # Include the symbols sprouting directly from the CVSBranch:
      process_subitems(cvs_branch)

    id = start_id
    while id is not None:
      cvs_rev = self[id]
      cvs_revisions.append(cvs_rev)
      process_subitems(cvs_rev)
      id = cvs_rev.next_id

    return LODItems(lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags)

  def get_lod_items(self, cvs_branch):
    """Return an LODItems describing the branch that starts at CVS_BRANCH.

    CVS_BRANCH must be an instance of CVSBranch contained in this
    CVSFileItems."""

    return self._get_lod(cvs_branch.symbol, cvs_branch, cvs_branch.next_id)

  def iter_root_lods(self):
    """Iterate over the LODItems for all root LODs (non-recursively)."""

    for id in list(self.root_ids):
      cvs_item = self[id]
      if isinstance(cvs_item, CVSRevision):
        # This LOD doesn't have a CVSBranch associated with it.
        # Either it is Trunk, or it is a branch whose CVSBranch has
        # been deleted.
        yield self._get_lod(cvs_item.lod, None, id)
      elif isinstance(cvs_item, CVSBranch):
        # This is a Branch that has been severed from the rest of the
        # tree.
        yield self._get_lod(cvs_item.symbol, cvs_item, cvs_item.next_id)
      else:
        raise InternalError('Unexpected root item: %s' % (cvs_item,))

  def _iter_tree(self, lod, cvs_branch, start_id):
    """Iterate over the tree that starts at the specified line of development.

    LOD is the LineOfDevelopment where the iteration should start.
    CVS_BRANCH is the CVSBranch instance that starts the LOD if any;
    otherwise it is None.  START_ID is the id of the first CVSRevision
    on this LOD, or None if there are none.

    There are two cases handled by this routine: trunk (where LOD is a
    Trunk instance, CVS_BRANCH is None, and START_ID is the id of the
    1.1 revision) and a branch (where LOD is a Branch instance,
    CVS_BRANCH is a CVSBranch instance, and START_ID is either the id
    of the first CVSRevision on the branch or None if there are no
    CVSRevisions on the branch).  Note that CVS_BRANCH and START_ID cannot
    simultaneously be None.

    Yield an LODItems instance for each line of development."""

    cvs_revisions = []
    cvs_branches = []
    cvs_tags = []

    def process_subitems(cvs_item):
      """Process the branches and tags that are rooted in CVS_ITEM.

      CVS_ITEM can be a CVSRevision or a CVSBranch."""

      for branch_id in cvs_item.branch_ids[:]:
        # Recurse into the branch:
        branch = self[branch_id]
        for lod_items in self._iter_tree(
              branch.symbol, branch, branch.next_id
              ):
          yield lod_items
        # The caller might have deleted the branch that we just
        # yielded.  If it is no longer present, then do not add it to
        # the list of cvs_branches.
        try:
          cvs_branches.append(self[branch_id])
        except KeyError:
          pass

      for tag_id in cvs_item.tag_ids:
        cvs_tags.append(self[tag_id])

    if cvs_branch is not None:
      # Include the symbols sprouting directly from the CVSBranch:
      for lod_items in process_subitems(cvs_branch):
        yield lod_items

    id = start_id
    while id is not None:
      cvs_rev = self[id]
      cvs_revisions.append(cvs_rev)

      for lod_items in process_subitems(cvs_rev):
        yield lod_items

      id = cvs_rev.next_id

    yield LODItems(lod, cvs_branch, cvs_revisions, cvs_branches, cvs_tags)

  def iter_lods(self):
    """Iterate over LinesOfDevelopment in this file, in depth-first order.

    For each LOD, yield an LODItems instance.  The traversal starts at
    each root node but returns the LODs in depth-first order.

    It is allowed to modify the CVSFileItems instance while the
    traversal is occurring, but only in ways that don't affect the
    tree structure above (i.e., towards the trunk from) the current
    LOD."""

    # Make a list out of root_ids so that callers can change it:
    for id in list(self.root_ids):
      cvs_item = self[id]
      if isinstance(cvs_item, CVSRevision):
        # This LOD doesn't have a CVSBranch associated with it.
        # Either it is Trunk, or it is a branch whose CVSBranch has
        # been deleted.
        lod = cvs_item.lod
        cvs_branch = None
      elif isinstance(cvs_item, CVSBranch):
        # This is a Branch that has been severed from the rest of the
        # tree.
        lod = cvs_item.symbol
        id = cvs_item.next_id
        cvs_branch = cvs_item
      else:
        raise InternalError('Unexpected root item: %s' % (cvs_item,))

      for lod_items in self._iter_tree(lod, cvs_branch, id):
        yield lod_items

  def iter_deltatext_ancestors(self, cvs_rev):
    """Generate the delta-dependency ancestors of CVS_REV.

    Generate then ancestors of CVS_REV in deltatext order; i.e., back
    along branches towards trunk, then outwards along trunk towards
    HEAD."""

    while True:
      # Determine the next candidate source revision:
      if isinstance(cvs_rev.lod, Trunk):
        if cvs_rev.next_id is None:
          # HEAD has no ancestors, so we are done:
          return
        else:
          cvs_rev = self[cvs_rev.next_id]
      else:
        cvs_rev = self[cvs_rev.prev_id]

      yield cvs_rev

  def _sever_branch(self, lod_items):
    """Sever the branch from its source and discard the CVSBranch.

    LOD_ITEMS describes a branch that should be severed from its
    source, deleting the CVSBranch and creating a new root.  Also set
    LOD_ITEMS.cvs_branch to None.

    If LOD_ITEMS has no source (e.g., because it is the trunk branch
    or because it has already been severed), do nothing.

    This method can only be used before symbols have been grafted onto
    CVSBranches.  It does not adjust NTDBR, NTDBR_PREV_ID or
    NTDBR_NEXT_ID even if LOD_ITEMS describes a NTDB."""

    cvs_branch = lod_items.cvs_branch
    if cvs_branch is None:
      return

    assert not cvs_branch.tag_ids
    assert not cvs_branch.branch_ids
    source_rev = self[cvs_branch.source_id]

    # We only cover the following case, even though after
    # FilterSymbolsPass cvs_branch.source_id might refer to another
    # CVSBranch.
    assert isinstance(source_rev, CVSRevision)

    # Delete the CVSBranch itself:
    lod_items.cvs_branch = None
    del self[cvs_branch.id]

    # Delete the reference from the source revision to the CVSBranch:
    source_rev.branch_ids.remove(cvs_branch.id)

    # Delete the reference from the first revision on the branch to
    # the CVSBranch:
    if lod_items.cvs_revisions:
      first_rev = lod_items.cvs_revisions[0]

      # Delete the reference from first_rev to the CVSBranch:
      first_rev.first_on_branch_id = None

      # Delete the reference from the source revision to the first
      # revision on the branch:
      source_rev.branch_commit_ids.remove(first_rev.id)

      # ...and vice versa:
      first_rev.prev_id = None

      # Change the type of first_rev (e.g., from Change to Add):
      first_rev.__class__ = cvs_revision_type_map[
          (isinstance(first_rev, CVSRevisionModification), False,)
          ]

      # Now first_rev is a new root:
      self.root_ids.add(first_rev.id)

  def adjust_ntdbrs(self, ntdbr_cvs_revs):
    """Adjust the specified non-trunk default branch revisions.

    NTDBR_CVS_REVS is a list of CVSRevision instances in this file
    that have been determined to be non-trunk default branch
    revisions.

    The first revision on the default branch is handled strangely by
    CVS.  If a file is imported (as opposed to being added), CVS
    creates a 1.1 revision, then creates a vendor branch 1.1.1 based
    on 1.1, then creates a 1.1.1.1 revision that is identical to the
    1.1 revision (i.e., its deltatext is empty).  The log message that
    the user typed when importing is stored with the 1.1.1.1 revision.
    The 1.1 revision always contains a standard, generated log
    message, 'Initial revision\n'.

    When we detect a straightforward import like this, we want to
    handle it by deleting the 1.1 revision (which doesn't contain any
    useful information) and making 1.1.1.1 into an independent root in
    the file's dependency tree.  In SVN, 1.1.1.1 will be added
    directly to the vendor branch with its initial content.  Then in a
    special 'post-commit', the 1.1.1.1 revision is copied back to
    trunk.

    If the user imports again to the same vendor branch, then CVS
    creates revisions 1.1.1.2, 1.1.1.3, etc. on the vendor branch,
    *without* counterparts in trunk (even though these revisions
    effectively play the role of trunk revisions).  So after we add
    such revisions to the vendor branch, we also copy them back to
    trunk in post-commits.

    Set the ntdbr members of the revisions listed in NTDBR_CVS_REVS to
    True.  Also, if there is a 1.2 revision, then set that revision to
    depend on the last non-trunk default branch revision and possibly
    adjust its type accordingly."""

    for cvs_rev in ntdbr_cvs_revs:
      cvs_rev.ntdbr = True

    # Look for a 1.2 revision:
    rev_1_1 = self[ntdbr_cvs_revs[0].prev_id]

    rev_1_2 = self.get(rev_1_1.next_id)
    if rev_1_2 is not None:
      # Revision 1.2 logically follows the imported revisions, not
      # 1.1.  Accordingly, connect it to the last NTDBR and possibly
      # change its type.
      last_ntdbr = ntdbr_cvs_revs[-1]
      rev_1_2.ntdbr_prev_id = last_ntdbr.id
      last_ntdbr.ntdbr_next_id = rev_1_2.id
      rev_1_2.__class__ = cvs_revision_type_map[(
          isinstance(rev_1_2, CVSRevisionModification),
          isinstance(last_ntdbr, CVSRevisionModification),
          )]

  def process_live_ntdb(self, vendor_lod_items):
    """VENDOR_LOD_ITEMS is a live default branch; process it.

    In this case, all revisions on the default branch are NTDBRs and
    it is an error if there is also a '1.2' revision.

    Return True iff this transformation really does something.  Raise
    a VendorBranchError if there is a '1.2' revision."""

    rev_1_1 = self[vendor_lod_items.cvs_branch.source_id]
    rev_1_2_id = rev_1_1.next_id
    if rev_1_2_id is not None:
      raise VendorBranchError(
          'File \'%s\' has default branch=%s but also a revision %s'
          % (self.cvs_file.rcs_path,
             vendor_lod_items.cvs_branch.branch_number, self[rev_1_2_id].rev,)
          )

    ntdbr_cvs_revs = list(vendor_lod_items.cvs_revisions)

    if ntdbr_cvs_revs:
      self.adjust_ntdbrs(ntdbr_cvs_revs)
      return True
    else:
      return False

  def process_historical_ntdb(self, vendor_lod_items):
    """There appears to have been a non-trunk default branch in the past.

    There is currently no default branch, but the branch described by
    file appears to have been imported.  So our educated guess is that
    all revisions on the '1.1.1' branch (described by
    VENDOR_LOD_ITEMS) with timestamps prior to the timestamp of '1.2'
    were non-trunk default branch revisions.

    Return True iff this transformation really does something.

    This really only handles standard '1.1.1.*'-style vendor
    revisions.  One could conceivably have a file whose default branch
    is 1.1.3 or whatever, or was that at some point in time, with
    vendor revisions 1.1.3.1, 1.1.3.2, etc.  But with the default
    branch gone now, we'd have no basis for assuming that the
    non-standard vendor branch had ever been the default branch
    anyway.

    Note that we rely on comparisons between the timestamps of the
    revisions on the vendor branch and that of revision 1.2, even
    though the timestamps might be incorrect due to clock skew.  We
    could do a slightly better job if we used the changeset
    timestamps, as it is possible that the dependencies that went into
    determining those timestamps are more accurate.  But that would
    require an extra pass or two."""

    rev_1_1 = self[vendor_lod_items.cvs_branch.source_id]
    rev_1_2_id = rev_1_1.next_id

    if rev_1_2_id is None:
      rev_1_2_timestamp = None
    else:
      rev_1_2_timestamp = self[rev_1_2_id].timestamp

    ntdbr_cvs_revs = []
    for cvs_rev in vendor_lod_items.cvs_revisions:
      if rev_1_2_timestamp is not None \
             and cvs_rev.timestamp >= rev_1_2_timestamp:
        # That's the end of the once-default branch.
        break
      ntdbr_cvs_revs.append(cvs_rev)

    if ntdbr_cvs_revs:
      self.adjust_ntdbrs(ntdbr_cvs_revs)
      return True
    else:
      return False

  def imported_remove_1_1(self, vendor_lod_items):
    """This file was imported.  Remove the 1.1 revision if possible.

    VENDOR_LOD_ITEMS is the LODItems instance for the vendor branch.
    See adjust_ntdbrs() for more information."""

    assert vendor_lod_items.cvs_revisions
    cvs_rev = vendor_lod_items.cvs_revisions[0]

    if isinstance(cvs_rev, CVSRevisionModification) \
           and not cvs_rev.deltatext_exists:
      cvs_branch = vendor_lod_items.cvs_branch
      rev_1_1 = self[cvs_branch.source_id]
      assert isinstance(rev_1_1, CVSRevision)
      logger.debug('Removing unnecessary revision %s' % (rev_1_1,))

      # Delete the 1.1.1 CVSBranch and sever the vendor branch from trunk:
      self._sever_branch(vendor_lod_items)

      # Delete rev_1_1:
      self.root_ids.remove(rev_1_1.id)
      del self[rev_1_1.id]
      rev_1_2_id = rev_1_1.next_id
      if rev_1_2_id is not None:
        rev_1_2 = self[rev_1_2_id]
        rev_1_2.prev_id = None
        self.root_ids.add(rev_1_2.id)

      # Move any tags and branches from rev_1_1 to cvs_rev:
      cvs_rev.tag_ids.extend(rev_1_1.tag_ids)
      for id in rev_1_1.tag_ids:
        cvs_tag = self[id]
        cvs_tag.source_lod = cvs_rev.lod
        cvs_tag.source_id = cvs_rev.id
      cvs_rev.branch_ids[0:0] = rev_1_1.branch_ids
      for id in rev_1_1.branch_ids:
        cvs_branch = self[id]
        cvs_branch.source_lod = cvs_rev.lod
        cvs_branch.source_id = cvs_rev.id
      cvs_rev.branch_commit_ids[0:0] = rev_1_1.branch_commit_ids
      for id in rev_1_1.branch_commit_ids:
        cvs_rev2 = self[id]
        cvs_rev2.prev_id = cvs_rev.id

  def _is_unneeded_initial_trunk_delete(self, cvs_item, metadata_db):
    if not isinstance(cvs_item, CVSRevisionNoop):
      # This rule can only be applied to dead revisions.
      return False

    if cvs_item.rev != '1.1':
      return False

    if not isinstance(cvs_item.lod, Trunk):
      return False

    if cvs_item.closed_symbols:
      return False

    if cvs_item.ntdbr:
      return False

    log_msg = metadata_db[cvs_item.metadata_id].log_msg
    return bool(
        re.match(
            r'file .* was initially added on branch .*\.\n$',
            log_msg,
            )
        or re.match(
            # This variant commit message was reported by one user:
            r'file .* was added on branch .*\n$',
            log_msg,
            )
        )

  def remove_unneeded_initial_trunk_delete(self, metadata_db):
    """Remove unneeded deletes for this file.

    If a file is added on a branch, then a trunk revision is added at
    the same time in the 'Dead' state.  This revision doesn't do
    anything useful, so delete it."""

    for id in self.root_ids:
      cvs_item = self[id]
      if self._is_unneeded_initial_trunk_delete(cvs_item, metadata_db):
        logger.debug('Removing unnecessary delete %s' % (cvs_item,))

        # Sever any CVSBranches rooted at cvs_item.
        for cvs_branch_id in cvs_item.branch_ids[:]:
          cvs_branch = self[cvs_branch_id]
          self._sever_branch(self.get_lod_items(cvs_branch))

        # Tagging a dead revision doesn't do anything, so remove any
        # CVSTags that refer to cvs_item:
        while cvs_item.tag_ids:
          del self[cvs_item.tag_ids.pop()]

        # Now delete cvs_item itself:
        self.root_ids.remove(cvs_item.id)
        del self[cvs_item.id]
        if cvs_item.next_id is not None:
          cvs_rev_next = self[cvs_item.next_id]
          cvs_rev_next.prev_id = None
          self.root_ids.add(cvs_rev_next.id)

        # This can only happen once per file, so we're done:
        return

  def _is_unneeded_initial_branch_delete(self, lod_items, metadata_db):
    """Return True iff the initial revision in LOD_ITEMS can be deleted."""

    if not lod_items.cvs_revisions:
      return False

    cvs_revision = lod_items.cvs_revisions[0]

    if cvs_revision.ntdbr:
      return False

    if not isinstance(cvs_revision, CVSRevisionAbsent):
      return False

    if cvs_revision.branch_ids:
      return False

    log_msg = metadata_db[cvs_revision.metadata_id].log_msg
    return bool(re.match(
        r'file .* was added on branch .* on '
        r'\d{4}\-\d{2}\-\d{2} \d{2}\:\d{2}\:\d{2}( [\+\-]\d{4})?'
        '\n$',
        log_msg,
        ))

  def remove_initial_branch_deletes(self, metadata_db):
    """If the first revision on a branch is an unnecessary delete, remove it.

    If a file is added on a branch (whether or not it already existed
    on trunk), then new versions of CVS add a first branch revision in
    the 'dead' state (to indicate that the file did not exist on the
    branch when the branch was created) followed by the second branch
    revision, which is an add.  When we encounter this situation, we
    sever the branch from trunk and delete the first branch
    revision."""

    for lod_items in self.iter_lods():
      if self._is_unneeded_initial_branch_delete(lod_items, metadata_db):
        cvs_revision = lod_items.cvs_revisions[0]
        logger.debug(
            'Removing unnecessary initial branch delete %s' % (cvs_revision,)
            )

        # Sever the branch from its source if necessary:
        self._sever_branch(lod_items)

        # Delete the first revision on the branch:
        self.root_ids.remove(cvs_revision.id)
        del self[cvs_revision.id]

        # If it had a successor, adjust its backreference and add it
        # to the root_ids:
        if cvs_revision.next_id is not None:
          cvs_rev_next = self[cvs_revision.next_id]
          cvs_rev_next.prev_id = None
          self.root_ids.add(cvs_rev_next.id)

        # Tagging a dead revision doesn't do anything, so remove any
        # tags that were set on it:
        for tag_id in cvs_revision.tag_ids:
          del self[tag_id]

  def _exclude_tag(self, cvs_tag):
    """Exclude the specified CVS_TAG."""

    del self[cvs_tag.id]

    # A CVSTag is the successor of the CVSRevision that it
    # sprouts from.  Delete this tag from that revision's
    # tag_ids:
    self[cvs_tag.source_id].tag_ids.remove(cvs_tag.id)

  def _exclude_branch(self, lod_items):
    """Exclude the branch described by LOD_ITEMS, including its revisions.

    (Do not update the LOD_ITEMS instance itself.)

    If the LOD starts with non-trunk default branch revisions, leave
    the branch and the NTDB revisions in place, but delete any
    subsequent revisions that are not NTDB revisions.  In this case,
    return True; otherwise return False"""

    if lod_items.cvs_revisions and lod_items.cvs_revisions[0].ntdbr:
      for cvs_rev in lod_items.cvs_revisions:
        if not cvs_rev.ntdbr:
          # We've found the first non-NTDBR, and it's stored in cvs_rev:
          break
      else:
        # There was no revision following the NTDBRs:
        cvs_rev = None

      if cvs_rev:
        last_ntdbr = self[cvs_rev.prev_id]
        last_ntdbr.next_id = None
        while True:
          del self[cvs_rev.id]
          if cvs_rev.next_id is None:
            break
          cvs_rev = self[cvs_rev.next_id]

      return True

    else:
      if lod_items.cvs_branch is not None:
        # Delete the CVSBranch itself:
        cvs_branch = lod_items.cvs_branch

        del self[cvs_branch.id]

        # A CVSBranch is the successor of the CVSRevision that it
        # sprouts from.  Delete this branch from that revision's
        # branch_ids:
        self[cvs_branch.source_id].branch_ids.remove(cvs_branch.id)

      if lod_items.cvs_revisions:
        # The first CVSRevision on the branch has to be either detached
        # from the revision from which the branch sprang, or removed
        # from self.root_ids:
        cvs_rev = lod_items.cvs_revisions[0]
        if cvs_rev.prev_id is None:
          self.root_ids.remove(cvs_rev.id)
        else:
          self[cvs_rev.prev_id].branch_commit_ids.remove(cvs_rev.id)

        for cvs_rev in lod_items.cvs_revisions:
          del self[cvs_rev.id]

      return False

  def graft_ntdbr_to_trunk(self):
    """Graft the non-trunk default branch revisions to trunk.

    They should already be alone on a branch that may or may not have
    a CVSBranch connecting it to trunk."""

    for lod_items in self.iter_lods():
      if lod_items.cvs_revisions and lod_items.cvs_revisions[0].ntdbr:
        assert lod_items.is_pure_ntdb()

        first_rev = lod_items.cvs_revisions[0]
        last_rev = lod_items.cvs_revisions[-1]
        rev_1_1 = self.get(first_rev.prev_id)
        rev_1_2 = self.get(last_rev.ntdbr_next_id)

        self._sever_branch(lod_items)

        if rev_1_1 is not None:
          rev_1_1.next_id = first_rev.id
          first_rev.prev_id = rev_1_1.id

          self.root_ids.remove(first_rev.id)

          first_rev.__class__ = cvs_revision_type_map[(
              isinstance(first_rev, CVSRevisionModification),
              isinstance(rev_1_1, CVSRevisionModification),
              )]

        if rev_1_2 is not None:
          rev_1_2.ntdbr_prev_id = None
          last_rev.ntdbr_next_id = None

          if rev_1_2.prev_id is None:
            self.root_ids.remove(rev_1_2.id)

          rev_1_2.prev_id = last_rev.id
          last_rev.next_id = rev_1_2.id

          # The effective_pred_id of rev_1_2 was not changed, so we
          # don't have to change rev_1_2's type.

        for cvs_rev in lod_items.cvs_revisions:
          cvs_rev.ntdbr = False
          cvs_rev.lod = self.trunk

        for cvs_branch in lod_items.cvs_branches:
          cvs_branch.source_lod = self.trunk

        for cvs_tag in lod_items.cvs_tags:
          cvs_tag.source_lod = self.trunk

        return

  def exclude_non_trunk(self):
    """Delete all tags and branches."""

    ntdbr_excluded = False
    for lod_items in self.iter_lods():
      for cvs_tag in lod_items.cvs_tags[:]:
        self._exclude_tag(cvs_tag)
        lod_items.cvs_tags.remove(cvs_tag)

      if not isinstance(lod_items.lod, Trunk):
        assert not lod_items.cvs_branches

        ntdbr_excluded |= self._exclude_branch(lod_items)

    if ntdbr_excluded:
      self.graft_ntdbr_to_trunk()

  def filter_excluded_symbols(self):
    """Delete any excluded symbols and references to them."""

    ntdbr_excluded = False
    for lod_items in self.iter_lods():
      # Delete any excluded tags:
      for cvs_tag in lod_items.cvs_tags[:]:
        if isinstance(cvs_tag.symbol, ExcludedSymbol):
          self._exclude_tag(cvs_tag)

          lod_items.cvs_tags.remove(cvs_tag)

      # Delete the whole branch if it is to be excluded:
      if isinstance(lod_items.lod, ExcludedSymbol):
        # A symbol can only be excluded if no other symbols spring
        # from it.  This was already checked in CollateSymbolsPass, so
        # these conditions should already be satisfied.
        assert not list(lod_items.iter_blockers())

        ntdbr_excluded |= self._exclude_branch(lod_items)

    if ntdbr_excluded:
      self.graft_ntdbr_to_trunk()

  def _mutate_branch_to_tag(self, cvs_branch):
    """Mutate the branch CVS_BRANCH into a tag."""

    if cvs_branch.next_id is not None:
      # This shouldn't happen because it was checked in
      # CollateSymbolsPass:
      raise FatalError('Attempt to exclude a branch with commits.')
    cvs_tag = CVSTag(
        cvs_branch.id, cvs_branch.cvs_file, cvs_branch.symbol,
        cvs_branch.source_lod, cvs_branch.source_id,
        cvs_branch.revision_reader_token,
        )
    self.add(cvs_tag)
    cvs_revision = self[cvs_tag.source_id]
    cvs_revision.branch_ids.remove(cvs_tag.id)
    cvs_revision.tag_ids.append(cvs_tag.id)

  def _mutate_tag_to_branch(self, cvs_tag):
    """Mutate the tag into a branch."""

    cvs_branch = CVSBranch(
        cvs_tag.id, cvs_tag.cvs_file, cvs_tag.symbol,
        None, cvs_tag.source_lod, cvs_tag.source_id, None,
        cvs_tag.revision_reader_token,
        )
    self.add(cvs_branch)
    cvs_revision = self[cvs_branch.source_id]
    cvs_revision.tag_ids.remove(cvs_branch.id)
    cvs_revision.branch_ids.append(cvs_branch.id)

  def _mutate_symbol(self, cvs_symbol):
    """Mutate CVS_SYMBOL if necessary."""

    symbol = cvs_symbol.symbol
    if isinstance(cvs_symbol, CVSBranch) and isinstance(symbol, Tag):
      self._mutate_branch_to_tag(cvs_symbol)
    elif isinstance(cvs_symbol, CVSTag) and isinstance(symbol, Branch):
      self._mutate_tag_to_branch(cvs_symbol)

  def mutate_symbols(self):
    """Force symbols to be tags/branches based on self.symbol_db."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        # This CVSRevision may be affected by the mutation of any
        # CVSSymbols that it references, but there is nothing to do
        # here directly.
        pass
      elif isinstance(cvs_item, CVSSymbol):
        self._mutate_symbol(cvs_item)
      else:
        raise RuntimeError('Unknown cvs item type')

  def _adjust_tag_parent(self, cvs_tag):
    """Adjust the parent of CVS_TAG if possible and preferred.

    CVS_TAG is an instance of CVSTag.  This method must be called in
    leaf-to-trunk order."""

    # The Symbol that cvs_tag would like to have as a parent:
    preferred_parent = Ctx()._symbol_db.get_symbol(
        cvs_tag.symbol.preferred_parent_id)

    if cvs_tag.source_lod == preferred_parent:
      # The preferred parent is already the parent.
      return

    # The CVSRevision that is its direct parent:
    source = self[cvs_tag.source_id]
    assert isinstance(source, CVSRevision)

    if isinstance(preferred_parent, Trunk):
      # It is not possible to graft *onto* Trunk:
      return

    # Try to find the preferred parent among the possible parents:
    for branch_id in source.branch_ids:
      if self[branch_id].symbol == preferred_parent:
        # We found it!
        break
    else:
      # The preferred parent is not a possible parent in this file.
      return

    parent = self[branch_id]
    assert isinstance(parent, CVSBranch)

    logger.debug('Grafting %s from %s (on %s) onto %s' % (
                cvs_tag, source, source.lod, parent,))
    # Switch parent:
    source.tag_ids.remove(cvs_tag.id)
    parent.tag_ids.append(cvs_tag.id)
    cvs_tag.source_lod = parent.symbol
    cvs_tag.source_id = parent.id

  def _adjust_branch_parents(self, cvs_branch):
    """Adjust the parent of CVS_BRANCH if possible and preferred.

    CVS_BRANCH is an instance of CVSBranch.  This method must be
    called in leaf-to-trunk order."""

    # The Symbol that cvs_branch would like to have as a parent:
    preferred_parent = Ctx()._symbol_db.get_symbol(
        cvs_branch.symbol.preferred_parent_id)

    if cvs_branch.source_lod == preferred_parent:
      # The preferred parent is already the parent.
      return

    # The CVSRevision that is its direct parent:
    source = self[cvs_branch.source_id]
    # This is always a CVSRevision because we haven't adjusted it yet:
    assert isinstance(source, CVSRevision)

    if isinstance(preferred_parent, Trunk):
      # It is not possible to graft *onto* Trunk:
      return

    # Try to find the preferred parent among the possible parents:
    for branch_id in source.branch_ids:
      possible_parent = self[branch_id]
      if possible_parent.symbol == preferred_parent:
        # We found it!
        break
      elif possible_parent.symbol == cvs_branch.symbol:
        # Only branches that precede the branch to be adjusted are
        # considered possible parents.  Leave parentage unchanged:
        return
    else:
      # This point should never be reached.
      raise InternalError(
          'Possible parent search did not terminate as expected')

    parent = possible_parent
    assert isinstance(parent, CVSBranch)

    logger.debug('Grafting %s from %s (on %s) onto %s' % (
                cvs_branch, source, source.lod, parent,))
    # Switch parent:
    source.branch_ids.remove(cvs_branch.id)
    parent.branch_ids.append(cvs_branch.id)
    cvs_branch.source_lod = parent.symbol
    cvs_branch.source_id = parent.id

  def adjust_parents(self):
    """Adjust the parents of symbols to their preferred parents.

    If a CVSSymbol has a preferred parent that is different than its
    current parent, and if the preferred parent is an allowed parent
    of the CVSSymbol in this file, then graft the CVSSymbol onto its
    preferred parent."""

    for lod_items in self.iter_lods():
      for cvs_tag in lod_items.cvs_tags:
        self._adjust_tag_parent(cvs_tag)

      # It is important to process branches in reverse order, so that
      # a branch graft target (which necessarily occurs earlier in the
      # list than the branch itself) is not moved before the branch
      # itself.
      for cvs_branch in reversed(lod_items.cvs_branches):
        self._adjust_branch_parents(cvs_branch)

  def _get_revision_source(self, cvs_symbol):
    """Return the CVSRevision that is the ultimate source of CVS_SYMBOL."""

    while True:
      cvs_item = self[cvs_symbol.source_id]
      if isinstance(cvs_item, CVSRevision):
        return cvs_item
      else:
        cvs_symbol = cvs_item

  def refine_symbols(self):
    """Refine the types of the CVSSymbols in this file.

    Adjust the symbol types based on whether the source exists:
    CVSBranch vs. CVSBranchNoop and CVSTag vs. CVSTagNoop."""

    for lod_items in self.iter_lods():
      for cvs_tag in lod_items.cvs_tags:
        source = self._get_revision_source(cvs_tag)
        cvs_tag.__class__ = cvs_tag_type_map[
            isinstance(source, CVSRevisionModification)
            ]

      for cvs_branch in lod_items.cvs_branches:
        source = self._get_revision_source(cvs_branch)
        cvs_branch.__class__ = cvs_branch_type_map[
            isinstance(source, CVSRevisionModification)
            ]

  def determine_revision_properties(self, revision_property_setters):
    """Set the properties and properties_changed fields on CVSRevisions."""

    for lod_items in self.iter_lods():
      for cvs_rev in lod_items.cvs_revisions:
        cvs_rev.properties = {}
        for revision_property_setter in revision_property_setters:
          revision_property_setter.set_properties(cvs_rev)

    for lod_items in self.iter_lods():
      for cvs_rev in lod_items.cvs_revisions:
        if isinstance(cvs_rev, CVSRevisionAdd):
          cvs_rev.properties_changed = True
        elif isinstance(cvs_rev, CVSRevisionChange):
          prev_properties = self[
              cvs_rev.get_effective_prev_id()
              ].get_properties()
          properties = cvs_rev.get_properties()

          cvs_rev.properties_changed = properties != prev_properties
        else:
          cvs_rev.properties_changed = False

  def record_opened_symbols(self):
    """Set CVSRevision.opened_symbols for the surviving revisions."""

    for cvs_item in self.values():
      if isinstance(cvs_item, (CVSRevision, CVSBranch)):
        cvs_item.opened_symbols = []
        for cvs_symbol_opened_id in cvs_item.get_cvs_symbol_ids_opened():
          cvs_symbol_opened = self[cvs_symbol_opened_id]
          cvs_item.opened_symbols.append(
              (cvs_symbol_opened.symbol.id, cvs_symbol_opened.id,)
              )

  def record_closed_symbols(self):
    """Set CVSRevision.closed_symbols for the surviving revisions.

    A CVSRevision closes the symbols that were opened by the CVSItems
    that the CVSRevision closes.  Got it?

    This method must be called after record_opened_symbols()."""

    for cvs_item in self.values():
      if isinstance(cvs_item, CVSRevision):
        cvs_item.closed_symbols = []
        for cvs_item_closed_id in cvs_item.get_ids_closed():
          cvs_item_closed = self[cvs_item_closed_id]
          cvs_item.closed_symbols.extend(cvs_item_closed.opened_symbols)


