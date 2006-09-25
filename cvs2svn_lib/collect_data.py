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


from __future__ import generators

import sys
import os
import re
import time

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import OP_ADD
from cvs2svn_lib.common import OP_CHANGE
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_file import CVSFile
from cvs2svn_lib.line_of_development import Trunk
from cvs2svn_lib.line_of_development import Branch
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.database import Database
from cvs2svn_lib.database import SDatabase
from cvs2svn_lib.database import DB_OPEN_NEW
from cvs2svn_lib.cvs_file_database import CVSFileDatabase
from cvs2svn_lib.cvs_item_database import NewCVSItemStore
from cvs2svn_lib.symbol import Symbol
from cvs2svn_lib.symbol_statistics import SymbolStatisticsCollector
from cvs2svn_lib.metadata_database import MetadataDatabase

import cvs2svn_rcsparse


branch_tag_re = re.compile(r'''
    ^
    ((?:\d+\.\d+\.)+)   # A nonzero even number of digit groups w/trailing dot
    (?:0\.)?            # CVS sticks an extra 0 here; RCS does not
    (\d+)               # And the last digit group
    $
    ''', re.VERBOSE)

# This really only matches standard '1.1.1.*'-style vendor revisions.
# One could conceivably have a file whose default branch is 1.1.3 or
# whatever, or was that at some point in time, with vendor revisions
# 1.1.3.1, 1.1.3.2, etc.  But with the default branch gone now (which
# is the only time this regexp gets used), we'd have no basis for
# assuming that the non-standard vendor branch had ever been the
# default branch anyway, so we don't want this to match them anyway.
vendor_revision = re.compile(r'^1\.1\.1\.\d+$')


def is_trunk_revision(rev):
  """Return True iff REV is a trunk revision."""

  return rev.count('.') == 1


def is_branch_revision(rev):
  """Return True iff REV is a branch revision."""

  return rev.count('.') >= 3


def is_same_line_of_development(rev1, rev2):
  """Return True if rev1 and rev2 are on the same line of
  development (i.e., both on trunk, or both on the same branch);
  return False otherwise.  Either rev1 or rev2 can be None, in
  which case automatically return False."""

  if rev1 is None or rev2 is None:
    return False
  if rev1.count('.') == 1 and rev2.count('.') == 1:
    return True
  if rev1[0:rev1.rfind('.')] == rev2[0:rev2.rfind('.')]:
    return True
  return False


class _RevisionData:
  """We track the state of each revision so that in set_revision_info,
  we can determine if our op is an add/change/delete.  We can do this
  because in set_revision_info, we'll have all of the _RevisionData
  for a file at our fingertips, and we need to examine the state of
  our prev_rev to determine if we're an add or a change.  Without the
  state of the prev_rev, we are unable to distinguish between an add
  and a change."""

  def __init__(self, cvs_rev_id, rev, timestamp, author, state):
    # The id of this revision:
    self.cvs_rev_id = cvs_rev_id
    # The CVSRevision is not yet known.  It will be stored here:
    self.cvs_rev = None
    self.rev = rev
    self.timestamp = timestamp
    self.author = author
    self.original_timestamp = timestamp
    self._adjusted = False
    self.state = state

    # If this is the first revision on a branch, then this is the
    # branch_data of that branch; otherwise it is None.
    self.parent_branch_data = None

    # The revision number of the parent of this revision along the
    # same line of development, if any.
    #
    # For the first revision R on a branch, we consider the revision
    # from which R sprouted to be the 'previous'.
    #
    # Note that this revision can't be determined arithmetically (due
    # to cvsadmin -o, which is why this is necessary).
    #
    # If the key has no previous revision, then this field is None.
    self.parent = None

    # The revision number of the primary child of this revision (the
    # child along the same line of development), if any; otherwise,
    # None.
    self.child = None

    # The _BranchData instances of branches that sprout from this
    # revision.  It would be inconvenient to initialize it here
    # because we would have to scan through all branches known by the
    # _SymbolDataCollector to find the ones having us as the parent.
    # Instead, this information is filled in by
    # _FileDataCollector._resolve_dependencies().
    self.branches_data = []

    # The _SymbolData instances of symbols that are closed by this
    # revision.
    self.closed_symbols_data = []

    # The _TagData instances of tags that are connected to this
    # revision.
    self.tags_data = []

    # The id of the metadata record associated with this revision.
    self.metadata_id = None

    # A boolean value indicating whether deltatext was associated with
    # this revision.
    self.deltatext_exists = None

  def adjust_timestamp(self, timestamp):
    self._adjusted = True
    self.timestamp = timestamp

  def timestamp_was_adjusted(self):
    return self._adjusted

  def is_first_on_branch(self):
    return not self.parent or self.parent_branch_data is not None


class _SymbolData:
  """Collection area for information about a CVS symbol (branch or tag)."""

  def __init__(self, id, symbol):
    self.id = id
    self.symbol = symbol


class _BranchData(_SymbolData):
  """Collection area for information about a CVSBranch."""

  def __init__(self, id, symbol, branch_number):
    _SymbolData.__init__(self, id, symbol)
    self.branch_number = branch_number

    # The revision number of the revision from which this branch
    # sprouts.
    self.parent = self.branch_number[:self.branch_number.rindex(".")]

    # The revision number of the first commit on this branch, if any;
    # otherwise, None.
    self.child = None


class _TagData(_SymbolData):
  """Collection area for information about a CVSTag."""

  def __init__(self, id, symbol, rev):
    _SymbolData.__init__(self, id, symbol)
    self.rev = rev


class _SymbolDataCollector:
  """Collect information about symbols in a CVSFile."""

  def __init__(self, fdc, cvs_file):
    self.fdc = fdc
    self.cvs_file = cvs_file

    self.pdc = self.fdc.pdc
    self.collect_data = self.fdc.collect_data

    # A set containing the names of each known symbol in this file,
    # used to check for duplicates.
    self._known_symbols = set()

    # Map { branch_number : _BranchData }, where branch_number has an
    # odd number of digits.
    self.branches_data = { }

    # Map { revision : [ tag_data ] }, where revision has an even
    # number of digits, and the value is a list of _TagData objects
    # for tags that apply to that revision.
    self.tags_data = { }

  def _add_branch(self, name, branch_number):
    """Record that BRANCH_NUMBER is the branch number for branch NAME,
    and derive and record the revision from which NAME sprouts.
    BRANCH_NUMBER is an RCS branch number with an odd number of
    components, for example '1.7.2' (never '1.7.0.2').  Return the
    _BranchData instance (which is usually newly-created)."""

    branch_data = self.branches_data.get(branch_number)

    if branch_data is not None:
      sys.stderr.write("%s: in '%s':\n"
                       "   branch '%s' already has name '%s',\n"
                       "   cannot also have name '%s', ignoring the latter\n"
                       % (warning_prefix,
                          self.cvs_file.filename, branch_number,
                          branch_data.symbol.name, name))
      return branch_data

    symbol = self.pdc.get_symbol(name)
    self.collect_data.symbol_stats.register_branch_creation(symbol)
    branch_data = _BranchData(
        self.collect_data.key_generator.gen_id(), symbol, branch_number)
    self.branches_data[branch_number] = branch_data
    return branch_data

  def _add_unlabeled_branch(self, branch_number):
    name = "unlabeled-" + branch_number
    return self._add_branch(name, branch_number)

  def _add_tag(self, name, revision):
    """Record that tag NAME refers to the specified REVISION."""

    symbol = self.pdc.get_symbol(name)
    self.collect_data.symbol_stats.register_tag_creation(symbol)
    tag_data = _TagData(
        self.collect_data.key_generator.gen_id(), symbol, revision)
    self.tags_data.setdefault(revision, []).append(tag_data)
    return tag_data

  def define_symbol(self, name, revision):
    """Record a symbol called NAME, which is associated with REVISON.

    REVISION is an unprocessed revision number from the RCS file's
    header, for example: '1.7', '1.7.0.2', or '1.1.1' or '1.1.1.1'.
    NAME is an untransformed branch or tag name.  This function will
    determine by inspection whether it is a branch or a tag, and
    record it in the right places."""

    name = self.cvs_file.project.transform_symbol(self.cvs_file, name)

    # Check that the symbol is not already defined, which can easily
    # happen when --symbol-transform is used:
    if name in self._known_symbols:
      err = "%s: Multiple definitions of the symbol '%s' in '%s'" \
                % (error_prefix, name, self.cvs_file.filename)
      sys.stderr.write(err + "\n")
      self.collect_data.fatal_errors.append(err)
      return

    self._known_symbols.add(name)

    # Determine whether it is a branch or tag, then add it:
    m = branch_tag_re.match(revision)
    if m:
      self._add_branch(name, m.group(1) + m.group(2))
    else:
      self._add_tag(name, revision)

  def rev_to_branch_data(self, revision):
    """Return the branch_data of the branch on which REVISION lies.
    REVISION is a branch revision number with an even number of
    components; for example '1.7.2.1' (never '1.7.2' nor '1.7.0.2').
    For the convenience of callers, REVISION can also be a trunk
    revision such as '1.2', in which case just return None."""

    if is_trunk_revision(revision):
      return None
    return self.branches_data.get(revision[:revision.rindex(".")])

  def register_commit(self, rev_data):
    """If REV_DATA describes a non-trunk revision number, then record
    it as a commit on the corresponding branch.  This records the
    commit in symbol_stats, which is used to generate statistics for
    --force-branch and --force-tag guidance."""

    rev = rev_data.rev
    if is_branch_revision(rev):
      branch_number = rev[:rev.rindex(".")]

      branch_data = self.branches_data[branch_number]

      # Register the commit on this non-trunk branch
      self.collect_data.symbol_stats.register_branch_commit(
          branch_data.symbol)

  def register_branch_blockers(self):
    for (revision, tag_data_list) in self.tags_data.items():
      if is_branch_revision(revision):
        branch_data_parent = self.rev_to_branch_data(revision)
        for tag_data in tag_data_list:
          self.collect_data.symbol_stats.register_branch_blocker(
              branch_data_parent.symbol, tag_data.symbol)

    for branch_data_child in self.branches_data.values():
      if is_branch_revision(branch_data_child.parent):
        branch_data_parent = self.rev_to_branch_data(branch_data_child.parent)
        self.collect_data.symbol_stats.register_branch_blocker(
            branch_data_parent.symbol, branch_data_child.symbol)


class _FileDataCollector(cvs2svn_rcsparse.Sink):
  """Class responsible for collecting RCS data for a particular file.

  Any collected data that need to be remembered are stored into the
  referenced CollectData instance."""

  def __init__(self, pdc, cvs_file):
    """Create an object that is prepared to receive data for CVS_FILE.
    CVS_FILE is a CVSFile instance.  COLLECT_DATA is used to store the
    information collected about the file."""

    self.pdc = pdc
    self.cvs_file = cvs_file

    self.collect_data = self.pdc.collect_data
    self.project = self.cvs_file.project

    # A place to store information about the symbols in this file:
    self.sdc = _SymbolDataCollector(self, self.cvs_file)

    # { revision : _RevisionData instance }
    self._rev_data = { }

    # A list [ revision ] of the revision numbers seen, in the order
    # they were given to us by rcsparse:
    self._rev_order = []

    # Lists [ (parent, child) ] of revision number pairs indicating
    # that revision child depends on revision parent along the main
    # line of development.
    self._primary_dependencies = []

    # If set, this is an RCS branch number -- rcsparse calls this the
    # "principal branch", but CVS and RCS refer to it as the "default
    # branch", so that's what we call it, even though the rcsparse API
    # setter method is still 'set_principal_branch'.
    self.default_branch = None

    # The default RCS branch, if any, for this CVS file.
    #
    # The value is None or a vendor branch revision, such as
    # '1.1.1.1', or '1.1.1.2', or '1.1.1.96'.  The vendor branch
    # revision represents the highest vendor branch revision thought
    # to have ever been head of the default branch.
    #
    # The reason we record a specific vendor revision, rather than a
    # default branch number, is that there are two cases to handle:
    #
    # One case is simple.  The RCS file lists a default branch
    # explicitly in its header, such as '1.1.1'.  In this case, we
    # know that every revision on the vendor branch is to be treated
    # as head of trunk at that point in time.
    #
    # But there's also a degenerate case.  The RCS file does not
    # currently have a default branch, yet we can deduce that for some
    # period in the past it probably *did* have one.  For example, the
    # file has vendor revisions 1.1.1.1 -> 1.1.1.96, all of which are
    # dated before 1.2, and then it has 1.1.1.97 -> 1.1.1.100 dated
    # after 1.2.  In this case, we should record 1.1.1.96 as the last
    # vendor revision to have been the head of the default branch.
    self.cvs_file_default_branch = None

    # If the RCS file doesn't have a default branch anymore, but does
    # have vendor revisions, then we make an educated guess that those
    # revisions *were* the head of the default branch up until the
    # commit of 1.2, at which point the file's default branch became
    # trunk.  This records the date at which 1.2 was committed.
    self.first_non_vendor_revision_date = None

    # A list of rev_data for each revision, in the order that the
    # corresponding set_revision_info() callback was called.  This
    # information is collected while the file is being parsed then
    # processed in _process_revision_data(), which is called by
    # parse_completed().
    self._revision_data = []

  def _get_rev_id(self, revision):
    if revision is None:
      return None
    return self._rev_data[revision].cvs_rev_id

  def set_principal_branch(self, branch):
    """This is a callback method declared in Sink."""

    self.default_branch = branch

  def set_expansion(self, mode):
    """This is a callback method declared in Sink."""

    self.cvs_file.mode = mode

  def define_tag(self, name, revision):
    """Remember the symbol name and revision, but don't process them yet.

    This is a callback method declared in Sink."""

    self.sdc.define_symbol(name, revision)

  def admin_completed(self):
    """This is a callback method declared in Sink."""

    pass

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    """This is a callback method declared in Sink."""

    for branch in branches:
      branch_number = branch[:branch.rindex('.')]

      branch_data = self.sdc.branches_data.get(branch_number)

      if branch_data is None:
        # Normally we learn about the branches from the branch names
        # and numbers parsed from the symbolic name header.  But this
        # must have been an unlabeled branch that slipped through the
        # net.  Generate a name for it and create a _BranchData record
        # for it now.
        branch_data = self.sdc._add_unlabeled_branch(branch_number)

      assert branch_data.child is None
      branch_data.child = branch

    # Record basic information about the revision:
    self._rev_data[revision] = _RevisionData(
        self.collect_data.key_generator.gen_id(),
        revision, int(timestamp), author, state)

    # Remember the order that revisions were defined:
    self._rev_order.append(revision)

    # When on trunk, the RCS 'next' revision number points to what
    # humans might consider to be the 'previous' revision number.  For
    # example, 1.3's RCS 'next' is 1.2.
    #
    # However, on a branch, the RCS 'next' revision number really does
    # point to what humans would consider to be the 'next' revision
    # number.  For example, 1.1.2.1's RCS 'next' would be 1.1.2.2.
    #
    # In other words, in RCS, 'next' always means "where to find the next
    # deltatext that you need this revision to retrieve.
    #
    # That said, we don't *want* RCS's behavior here, so we determine
    # whether we're on trunk or a branch and set the dependencies
    # accordingly.
    if next:
      if is_trunk_revision(revision):
        self._primary_dependencies.append( (next, revision,) )
      else:
        self._primary_dependencies.append( (revision, next,) )

  def _resolve_dependencies(self):
    """Store the primary and branch dependencies into the rev_data objects."""

    for (parent, child,) in self._primary_dependencies:
      parent_data = self._rev_data[parent]
      assert parent_data.child is None
      parent_data.child = child

      child_data = self._rev_data[child]
      assert child_data.parent is None
      child_data.parent = parent

    for branch_data in self.sdc.branches_data.values():
      # The branch_data's parent has the branch as a child regardless
      # of whether the branch had any subsequent commits:
      parent_data = self._rev_data[branch_data.parent]
      parent_data.branches_data.append(branch_data)

      if not Ctx().trunk_only and parent_data.child is not None:
        closing_data = self._rev_data[parent_data.child]
        closing_data.closed_symbols_data.append(branch_data)

      # If the branch has a child (i.e., something was committed on
      # the branch), then we store a reference to the branch_data
      # there, and also define the child's parent to be the branch's
      # parent:
      if branch_data.child is not None:
        child_data = self._rev_data[branch_data.child]
        assert child_data.parent_branch_data is None
        child_data.parent_branch_data = branch_data
        assert child_data.parent is None
        child_data.parent = branch_data.parent

    for tag_data_list in self.sdc.tags_data.values():
      for tag_data in tag_data_list:
        # The tag_data's rev has the tag as a child:
        parent_data = self._rev_data[tag_data.rev]
        parent_data.tags_data.append(tag_data)

        if not Ctx().trunk_only and parent_data.child is not None:
          closing_data = self._rev_data[parent_data.child]
          closing_data.closed_symbols_data.append(tag_data)

  def _update_default_branch(self, rev_data):
    """Ratchet up the highest vendor head revision based on REV_DATA,
    if necessary."""

    if self.default_branch:
      default_branch_root = self.default_branch + "."
      if (rev_data.rev.startswith(default_branch_root)
          and default_branch_root.count('.') == rev_data.rev.count('.')):
        # This revision is on the default branch, so record that it is
        # the new highest default branch head revision.
        self.cvs_file_default_branch = rev_data.rev
    else:
      # No default branch, so make an educated guess.
      if rev_data.rev == '1.2':
        # This is probably the time when the file stopped having a
        # default branch, so make a note of it.
        self.first_non_vendor_revision_date = rev_data.timestamp
      else:
        if vendor_revision.match(rev_data.rev) \
              and (not self.first_non_vendor_revision_date
                   or rev_data.timestamp
                       < self.first_non_vendor_revision_date):
          # We're looking at a vendor revision, and it wasn't
          # committed after this file lost its default branch, so bump
          # the maximum trunk vendor revision in the permanent record.
          self.cvs_file_default_branch = rev_data.rev

  def _resync_chain(self, rev_data):
    """If the REV_DATA.parent revision exists and it occurred later
    than the REV_DATA revision, then shove the previous revision back
    in time (and any before it that may need to shift).  Return True
    iff any resyncing was done.

    We sync backwards and not forwards because any given CVS Revision
    has only one previous revision.  However, a CVS Revision can *be*
    a previous revision for many other revisions (e.g., a revision
    that is the source of multiple branches).  This becomes relevant
    when we do the secondary synchronization in pass 2--we can make
    certain that we don't resync a revision earlier than its previous
    revision, but it would be non-trivial to make sure that we don't
    resync revision R *after* any revisions that have R as a previous
    revision."""

    resynced = False
    while rev_data.parent is not None:
      prev_rev_data = self._rev_data[rev_data.parent]

      if prev_rev_data.timestamp < rev_data.timestamp:
        # No resyncing needed here.
        return resynced

      old_timestamp = prev_rev_data.timestamp
      prev_rev_data.adjust_timestamp(rev_data.timestamp - 1)
      resynced = True
      delta = prev_rev_data.timestamp - old_timestamp
      Log().verbose(
          "PASS1 RESYNC: '%s' (%s): old time='%s' delta=%ds"
          % (self.cvs_file.cvs_path, prev_rev_data.rev,
             time.ctime(old_timestamp), delta))
      if abs(delta) > config.COMMIT_THRESHOLD:
        Log().warn(
            "%s: Significant timestamp change for '%s' (%d seconds)"
            % (warning_prefix, self.cvs_file.cvs_path, delta))
      rev_data = prev_rev_data

    return resynced

  def tree_completed(self):
    """The revision tree has been parsed.  Analyze it for consistency.

    This is a callback method declared in Sink."""

    for rev in self._rev_order:
      rev_data = self._rev_data[rev]
      self.sdc.register_commit(rev_data)
      self._update_default_branch(rev_data)

    self._resolve_dependencies()

    # Our algorithm depends upon the timestamps on the revisions occuring
    # monotonically over time.  That is, we want to see rev 1.34 occur in
    # time before rev 1.35.  If we inserted 1.35 *first* (due to the time-
    # sorting), and then tried to insert 1.34, we'd be screwed.

    # To perform the analysis, we'll simply visit all of the 'previous'
    # links that we have recorded and validate that the timestamp on the
    # previous revision is before the specified revision.

    # If we have to resync some nodes, then we restart the scan.  Just
    # keep looping as long as we need to restart.
    while True:
      for rev_data in self._rev_data.values():
        if self._resync_chain(rev_data):
          # Abort for loop, causing the scan to start again:
          break
      else:
        # Finished the for-loop without having to resync anything.
        # We're done.
        return

  def _determine_operation(self, rev_data):
    # How to tell if a CVSRevision is an add, a change, or a deletion:
    #
    # It's a delete if RCS state is 'dead'
    #
    # It's an add if RCS state is 'Exp.' and
    #      - we either have no previous revision
    #        or
    #      - we have a previous revision whose state is 'dead'
    #
    # Anything else is a change.
    prev_rev_data = self._rev_data.get(rev_data.parent)

    if rev_data.state == 'dead':
      op = OP_DELETE
    elif prev_rev_data is None or prev_rev_data.state == 'dead':
      op = OP_ADD
    else:
      op = OP_CHANGE

    # There can be an odd situation where the tip revision of a branch
    # is alive, but every predecessor on the branch is in state 'dead',
    # yet the revision from which the branch sprouts is alive.  (This
    # is sort of a mirror image of the more common case of adding a
    # file on a branch, in which the first revision on the branch is
    # alive while the revision from which it sprouts is dead.)
    #
    # In this odd situation, we must mark the first live revision on
    # the branch as an OP_CHANGE instead of an OP_ADD, because it
    # reflects, however indirectly, a change w.r.t. the source
    # revision from which the branch sprouts.
    #
    # This is issue #89.
    if is_branch_revision(rev_data.rev) and rev_data.state != 'dead':
      cur_rev_data = rev_data
      while True:
        if cur_rev_data.parent is None:
          break
        prev_rev_data = self._rev_data[cur_rev_data.parent]
        if (not is_same_line_of_development(cur_rev_data.rev,
                                            prev_rev_data.rev)
            and cur_rev_data.state == 'dead'
            and prev_rev_data.state != 'dead'):
          op = OP_CHANGE
        cur_rev_data = prev_rev_data

    return op

  def set_revision_info(self, revision, log, text):
    """This is a callback method declared in Sink."""

    rev_data = self._rev_data[revision]
    rev_data.metadata_id = self.collect_data.metadata_db.get_key(
        self.project, rev_data.author, log)
    rev_data.deltatext_exists = bool(text)

    # "...Give back one kadam to honor the Hebrew God whose Ark this is."
    #       -- Imam to Indy and Sallah, in 'Raiders of the Lost Ark'
    #
    # If revision 1.1 appears to have been created via 'cvs add'
    # instead of 'cvs import', then this file probably never had a
    # default branch, so retroactively remove its record in the
    # default branches db.  The test is that the log message CVS uses
    # for 1.1 in imports is "Initial revision\n" with no period.
    if revision == '1.1' and log != 'Initial revision\n':
      self.cvs_file_default_branch = None

    self._revision_data.append(rev_data)

  def _is_default_branch_revision(self, rev_data):
    """Return True iff REV_DATA.rev is a default branch revision."""

    val = self.cvs_file_default_branch
    if val is not None:
      val_last_dot = val.rindex(".")
      our_last_dot = rev_data.rev.rindex(".")
      default_branch = val[:val_last_dot]
      our_branch = rev_data.rev[:our_last_dot]
      default_rev_component = int(val[val_last_dot + 1:])
      our_rev_component = int(rev_data.rev[our_last_dot + 1:])
      if (default_branch == our_branch
          and our_rev_component <= default_rev_component):
        return True

    return False

  def _process_revision_data(self, rev_data):
    if rev_data.timestamp_was_adjusted():
      # the timestamp on this revision was changed. log it for later
      # resynchronization of other files's revisions that occurred
      # for this time and log message.
      self.collect_data.resync.write(
          '%08lx %x %08lx\n'
          % (rev_data.original_timestamp, rev_data.metadata_id,
             rev_data.timestamp))

    if is_branch_revision(rev_data.rev):
      branch_data = self.sdc.rev_to_branch_data(rev_data.rev)
      lod = Branch(branch_data.symbol)
    else:
      lod = Trunk()

    branch_ids = [
        branch_data.symbol.id
        for branch_data in rev_data.branches_data
        ]

    tag_ids = [
        tag_data.symbol.id
        for tag_data in rev_data.tags_data
        ]

    closed_symbol_ids = [
        closed_symbol_data.symbol.id
        for closed_symbol_data in rev_data.closed_symbols_data
        ]

    cvs_rev = CVSRevision(
        self._get_rev_id(rev_data.rev), self.cvs_file,
        rev_data.timestamp, rev_data.metadata_id,
        self._get_rev_id(rev_data.parent),
        self._get_rev_id(rev_data.child),
        self._determine_operation(rev_data),
        rev_data.rev,
        rev_data.deltatext_exists,
        lod,
        rev_data.is_first_on_branch(),
        self._is_default_branch_revision(rev_data),
        tag_ids, branch_ids, closed_symbol_ids)
    rev_data.cvs_rev = cvs_rev
    self.collect_data.add_cvs_item(cvs_rev)

  def parse_completed(self):
    """Finish the processing of this file.

    - Create CVSRevisions for all rev_data seen.

    - Walk through all branches and tags and register them with their
      parent branch in the symbol database.

    This is a callback method declared in Sink."""

    for rev_data in self._revision_data:
      self._process_revision_data(rev_data)

    self.collect_data.add_cvs_file(self.cvs_file)

    self.sdc.register_branch_blockers()

    # Break a circular linkage, allowing self and sdc to be freed.
    del self.sdc


ctrl_characters_regexp = re.compile('[\\\x00-\\\x1f\\\x7f]')

def verify_filename_legal(filename):
  """Verify that FILENAME does not include any control characters.  If
  it does, raise a FatalError."""

  m = ctrl_characters_regexp.search(filename)
  if m:
    raise FatalError(
        "Character %r in filename %r is not supported by Subversion."
        % (m.group(), filename,))


class _ProjectDataCollector:
  def __init__(self, collect_data, project):
    self.collect_data = collect_data
    self.project = project
    self.found_valid_file = False
    self.fatal_errors = []
    self.num_files = 0

    # A map { name -> Symbol } for all known symbols in this project.
    self.symbols = {}

    os.path.walk(self.project.project_cvs_repos_path,
                 _ProjectDataCollector._visit_directory, self)
    if not self.fatal_errors and not self.found_valid_file:
      self.fatal_errors.append(
          '\n'
          'No RCS files found under %r!\n'
          'Are you absolutely certain you are pointing cvs2svn\n'
          'at a CVS repository?\n'
          % self.project.project_cvs_repos_path)

  def get_symbol(self, name):
    """Return the Symbol object for the symbol named NAME in this project.

    If such a symbol does not yet exist, allocate a new symbol_id,
    create a Symbol instance, store it in self.symbols, and return it."""

    symbol = self.symbols.get(name)
    if symbol is None:
      symbol = Symbol(
          self.collect_data.symbol_key_generator.gen_id(),
          self.project, name)
      self.symbols[name] = symbol
    return symbol

  def _process_file(self, pathname):
    fdc = _FileDataCollector(self, self.project.get_cvs_file(pathname))

    if not fdc.cvs_file.in_attic:
      # If this file also exists in the attic, it's a fatal error
      attic_path = os.path.join(
          os.path.dirname(pathname), 'Attic', os.path.basename(pathname))
      if os.path.exists(attic_path):
        err = "%s: A CVS repository cannot contain both %s and %s" \
              % (error_prefix, pathname, attic_path)
        sys.stderr.write(err + '\n')
        self.fatal_errors.append(err)

    try:
      cvs2svn_rcsparse.parse(open(pathname, 'rb'), fdc)
    except (cvs2svn_rcsparse.common.RCSParseError, ValueError,
            RuntimeError):
      err = "%s: '%s' is not a valid ,v file" \
            % (error_prefix, pathname)
      sys.stderr.write(err + '\n')
      self.fatal_errors.append(err)
    except:
      Log().warn("Exception occurred while parsing %s" % pathname)
      raise
    self.num_files += 1

  def _visit_directory(self, dirname, files):
    for fname in files:
      verify_filename_legal(fname)
      if not fname.endswith(',v'):
        continue
      self.found_valid_file = True
      pathname = os.path.join(dirname, fname)
      Log().normal(pathname)

      self._process_file(pathname)


class CollectData:
  """Repository for data collected by parsing the CVS repository files.

  This class manages the databases into which information collected
  from the CVS repository is stored.  The data are stored into this
  class by _FileDataCollector instances, one of which is created for
  each file to be parsed."""

  def __init__(self, stats_keeper):
    self._cvs_item_store = NewCVSItemStore(
        artifact_manager.get_temp_file(config.CVS_ITEMS_STORE))
    self.resync = open(
        artifact_manager.get_temp_file(config.RESYNC_DATAFILE), 'w')
    self.metadata_db = MetadataDatabase(DB_OPEN_NEW)
    self.fatal_errors = []
    self.num_files = 0
    self.symbol_stats = SymbolStatisticsCollector()
    self.stats_keeper = stats_keeper

    # Key generator to generate unique keys for each CVSRevision object:
    self.key_generator = KeyGenerator()

    self.symbol_key_generator = KeyGenerator(1)

  def process_project(self, project):
    pdc = _ProjectDataCollector(self, project)
    self.num_files += pdc.num_files
    self.fatal_errors.extend(pdc.fatal_errors)
    Log().verbose('Processed', self.num_files, 'files')

  def add_cvs_file(self, cvs_file):
    """Store CVS_FILE to _cvs_file_db under its persistent id."""

    Ctx()._cvs_file_db.log_file(cvs_file)

  def add_cvs_item(self, cvs_item):
    self._cvs_item_store.add(cvs_item)
    if isinstance(cvs_item, CVSRevision):
      self.stats_keeper.record_cvs_rev(cvs_item)

  def flush(self):
    self._cvs_item_store.close()
    self.symbol_stats.write()


