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
from cvs2svn_lib.common import DB_OPEN_NEW
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
from cvs2svn_lib.cvs_item import CVSBranch
from cvs2svn_lib.cvs_item import CVSTag
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.database import Database
from cvs2svn_lib.database import SDatabase
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

    # The revision numbers of the first commits on any branches on
    # which commits occurred.  This dependency is kept explicitly so
    # that a revision-only topological sort would miss the dependency
    # that exists via branches_data.
    self.branches_revs_data = []

    # The _SymbolData instances of symbols that are closed by this
    # revision.
    self.closed_symbols_data = []

    # The _TagData instances of tags that are connected to this
    # revision.
    self.tags_data = []

    # The id of the metadata record associated with this revision.
    self.metadata_id = None

    # True iff this revision was the head revision on a default branch
    # at some point (as best we can determine).
    self.non_trunk_default_branch_revision = False

    # Iff this is the 1.2 revision at which a non-trunk default branch
    # revision was ended, store the number of the last revision on
    # the default branch here.
    self.default_branch_prev = None

    # Iff this is the last revision of a non-trunk default branch, and
    # the branch is followed by a 1.2 revision, then this holds the
    # number of the 1.2 revision (namely, '1.2').
    self.default_branch_next = None

    # A boolean value indicating whether deltatext was associated with
    # this revision.
    self.deltatext_exists = None

  def get_first_on_branch_id(self):
    return self.parent_branch_data and self.parent_branch_data.id


class _SymbolData:
  """Collection area for information about a CVS symbol (branch or tag)."""

  def __init__(self, id, symbol):
    """Initialize an object for SYMBOL."""

    # The unique id that will be used for this particular symbol in
    # this particular file.  This same id will be used for the CVSItem
    # that is derived from this instance.
    self.id = id

    # An instance of Symbol.
    self.symbol = symbol


class _BranchData(_SymbolData):
  """Collection area for information about a CVSBranch."""

  def __init__(self, id, symbol, branch_number):
    _SymbolData.__init__(self, id, symbol)

    # The branch number (e.g., '1.5.2') of this branch.
    self.branch_number = branch_number

    # The revision number of the revision from which this branch
    # sprouts (e.g., '1.5').
    self.parent = self.branch_number[:self.branch_number.rindex(".")]

    # The revision number of the first commit on this branch, if any
    # (e.g., '1.5.2.1'); otherwise, None.
    self.child = None


class _TagData(_SymbolData):
  """Collection area for information about a CVSTag."""

  def __init__(self, id, symbol, rev):
    _SymbolData.__init__(self, id, symbol)

    # The revision number being tagged (e.g., '1.5.2.3').
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
    self.collect_data.symbol_stats[symbol].register_branch_creation()
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
    self.collect_data.symbol_stats[symbol].register_tag_creation()
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
      self.collect_data.symbol_stats[branch_data.symbol] \
          .register_branch_commit()

  def register_branch_blockers(self):
    for (revision, tag_data_list) in self.tags_data.items():
      if is_branch_revision(revision):
        branch_data_parent = self.rev_to_branch_data(revision)
        for tag_data in tag_data_list:
          self.collect_data.symbol_stats[branch_data_parent.symbol] \
              .register_branch_blocker(tag_data.symbol)

    for branch_data_child in self.branches_data.values():
      if is_branch_revision(branch_data_child.parent):
        branch_data_parent = self.rev_to_branch_data(branch_data_child.parent)
        self.collect_data.symbol_stats[branch_data_parent.symbol] \
            .register_branch_blocker(branch_data_child.symbol)


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

    # The revision number of the root revision in the dependency tree.
    # This is usually '1.1', but could be something else due to
    # cvsadmin -o
    self._root_rev = None

    # If set, this is an RCS branch number -- rcsparse calls this the
    # "principal branch", but CVS and RCS refer to it as the "default
    # branch", so that's what we call it, even though the rcsparse API
    # setter method is still 'set_principal_branch'.
    self.default_branch = None

    # True iff revision 1.1 of the file appears to have been imported
    # (as opposed to added normally).
    self._file_imported = False

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

  def _resolve_primary_dependencies(self):
    """Resolve the dependencies listed in self._primary_dependencies."""

    for (parent, child,) in self._primary_dependencies:
      parent_data = self._rev_data[parent]
      assert parent_data.child is None
      parent_data.child = child

      child_data = self._rev_data[child]
      assert child_data.parent is None
      child_data.parent = parent

  def _resolve_branch_dependencies(self):
    """Resolve dependencies involving branches."""

    for branch_data in self.sdc.branches_data.values():
      # The branch_data's parent has the branch as a child regardless
      # of whether the branch had any subsequent commits:
      try:
        parent_data = self._rev_data[branch_data.parent]
      except KeyError:
        Log().warn(
            'In %r:\n'
            '    branch %r references non-existing revision %s\n'
            '    and will be ignored.'
            % (self.cvs_file.filename, branch_data.symbol.name,
               branch_data.parent,))
        del self.sdc.branches_data[branch_data.branch_number]
      else:
        parent_data.branches_data.append(branch_data)

        if not Ctx().trunk_only and parent_data.child is not None:
          closing_data = self._rev_data[parent_data.child]
          closing_data.closed_symbols_data.append(branch_data)

        # If the branch has a child (i.e., something was committed on
        # the branch), then we store a reference to the branch_data
        # there, define the child's parent to be the branch's parent,
        # and list the child in the branch parent's branches_revs_data:
        if branch_data.child is not None:
          child_data = self._rev_data[branch_data.child]
          assert child_data.parent_branch_data is None
          child_data.parent_branch_data = branch_data
          assert child_data.parent is None
          child_data.parent = branch_data.parent
          parent_data.branches_revs_data.append(branch_data.child)

  def _resolve_tag_dependencies(self):
    """Resolve dependencies involving tags."""

    for (rev, tag_data_list) in self.sdc.tags_data.items():
      try:
        parent_data = self._rev_data[rev]
      except KeyError:
        Log().warn(
            'In %r:\n'
            '    the following tag(s) reference non-existing revision %s\n'
            '    and will be ignored:\n'
            '    %s' % (
                self.cvs_file.filename, rev,
                ', '.join([repr(tag_data.symbol.name)
                           for tag_data in tag_data_list]),))
        del self.sdc.tags_data[rev]
      else:
        if Ctx().trunk_only or parent_data.child is None:
          closed_symbols_data = None
        else:
          closed_symbols_data = \
              self._rev_data[parent_data.child].closed_symbols_data

        for tag_data in tag_data_list:
          assert tag_data.rev == rev
          # The tag_data's rev has the tag as a child:
          parent_data.tags_data.append(tag_data)

          if closed_symbols_data is not None:
            closed_symbols_data.append(tag_data)

  def _determine_root_rev(self):
    """Determine self.root_rev.

    We use the fact that it is the only revision without a parent."""

    for rev_data in self._rev_data.values():
      if rev_data.parent is None:
        assert self._root_rev is None
        self._root_rev = rev_data.rev
    assert self._root_rev is not None

  def tree_completed(self):
    """The revision tree has been parsed.  Analyze it for consistency.

    This is a callback method declared in Sink."""

    for rev in self._rev_order:
      rev_data = self._rev_data[rev]
      self.sdc.register_commit(rev_data)

    self._resolve_primary_dependencies()
    self._resolve_branch_dependencies()
    self._resolve_tag_dependencies()
    self._determine_root_rev()

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

    branch_symbol = self.sdc.rev_to_branch_data(revision)
    if branch_symbol == None:
      branch_name = None
    else:
      branch_name = branch_symbol.symbol.name

    rev_data.metadata_id = self.collect_data.metadata_db.get_key(
        self.project, branch_name, rev_data.author, log)
    rev_data.deltatext_exists = bool(text)

    # If this is revision 1.1, determine whether the file appears to
    # have been created via 'cvs add' instead of 'cvs import'.  The
    # test is that the log message CVS uses for 1.1 in imports is
    # "Initial revision\n" with no period.  (This fact helps determine
    # whether this file might have had a default branch in the past.)
    if revision == '1.1':
      self._file_imported = (log == 'Initial revision\n')

    self._revision_data.append(rev_data)

  def _process_default_branch_revisions(self):
    """Process any non-trunk default branch revisions.

    If a non-trunk default branch is determined to have existed, set
    _RevisionData.non_trunk_default_branch_revision for all revisions
    that were once non-trunk default revisions.

    There are two cases to handle:

    One case is simple.  The RCS file lists a default branch
    explicitly in its header, such as '1.1.1'.  In this case, we know
    that every revision on the vendor branch is to be treated as head
    of trunk at that point in time.

    But there's also a degenerate case.  The RCS file does not
    currently have a default branch, yet we can deduce that for some
    period in the past it probably *did* have one.  For example, the
    file has vendor revisions 1.1.1.1 -> 1.1.1.96, all of which are
    dated before 1.2, and then it has 1.1.1.97 -> 1.1.1.100 dated
    after 1.2.  In this case, we should record 1.1.1.96 as the last
    vendor revision to have been the head of the default branch."""

    if self.default_branch:
      # There is still a default branch; that means that all revisions
      # on that branch get marked.
      rev = self.sdc.branches_data[self.default_branch].child
      while rev:
        rev_data = self._rev_data[rev]
        rev_data.non_trunk_default_branch_revision = True
        rev = rev_data.child
    elif self._file_imported:
      # No default branch, but the file appears to have been imported.
      # So our educated guess is that all revisions on the '1.1.1'
      # branch with timestamps prior to the timestamp of '1.2' were
      # non-trunk default branch revisions.
      #
      # This really only processes standard '1.1.1.*'-style vendor
      # revisions.  One could conceivably have a file whose default
      # branch is 1.1.3 or whatever, or was that at some point in
      # time, with vendor revisions 1.1.3.1, 1.1.3.2, etc.  But with
      # the default branch gone now, we'd have no basis for assuming
      # that the non-standard vendor branch had ever been the default
      # branch anyway.
      #
      # Note that we rely on comparisons between the timestamps of the
      # revisions on the vendor branch and that of revision 1.2, even
      # though the timestamps might be incorrect due to clock skew.
      # We could do a slightly better job if we used the changeset
      # timestamps, as it is possible that the dependencies that went
      # into determining those timestamps are more accurate.  But that
      # would require an extra pass or two.
      vendor_branch_data = self.sdc.branches_data.get('1.1.1')
      if vendor_branch_data is None:
        return

      rev_1_2 = self._rev_data.get('1.2')
      if rev_1_2 is None:
        rev_1_2_timestamp = None
      else:
        rev_1_2_timestamp = rev_1_2.timestamp

      prev_rev_data = None
      rev = vendor_branch_data.child
      while rev:
        rev_data = self._rev_data[rev]
        if rev_1_2_timestamp is not None \
               and rev_data.timestamp >= rev_1_2_timestamp:
          # That's the end of the once-default branch.
          break
        rev_data.non_trunk_default_branch_revision = True
        prev_rev_data = rev_data
        rev = rev_data.child

      if rev_1_2 is not None and prev_rev_data is not None:
        rev_1_2.default_branch_prev = prev_rev_data.rev
        prev_rev_data.default_branch_next = rev_1_2.rev

  def _process_revision_data(self, rev_data):
    if is_branch_revision(rev_data.rev):
      branch_data = self.sdc.rev_to_branch_data(rev_data.rev)
      lod = Branch(branch_data.symbol)
    else:
      lod = Trunk()

    branch_ids = [
        branch_data.id
        for branch_data in rev_data.branches_data
        ]

    branch_commit_ids = [
        self._get_rev_id(rev)
        for rev in rev_data.branches_revs_data
        ]

    tag_ids = [
        tag_data.id
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
        rev_data.get_first_on_branch_id(),
        rev_data.non_trunk_default_branch_revision,
        self._get_rev_id(rev_data.default_branch_prev),
        self._get_rev_id(rev_data.default_branch_next),
        tag_ids, branch_ids, branch_commit_ids,
        closed_symbol_ids)
    rev_data.cvs_rev = cvs_rev
    self.collect_data.add_cvs_item(cvs_rev)

  def _process_symbol_data(self):
    """Store information about the accumulated symbols to collect_data."""

    for branch_data in self.sdc.branches_data.values():
      self.collect_data.add_cvs_item(
          CVSBranch(
              branch_data.id, self.cvs_file, branch_data.symbol,
              branch_data.branch_number,
              self._get_rev_id(branch_data.parent),
              self._get_rev_id(branch_data.child),
              ))

    for tags_data in self.sdc.tags_data.values():
      for tag_data in tags_data:
        self.collect_data.add_cvs_item(
            CVSTag(
                tag_data.id, self.cvs_file, tag_data.symbol,
                self._get_rev_id(tag_data.rev),
                ))

  def parse_completed(self):
    """Finish the processing of this file.

    - Create CVSRevisions for all rev_data seen.

    - Walk through all branches and tags and register them with their
      parent branch in the symbol database.

    This is a callback method declared in Sink."""

    self._process_default_branch_revisions()

    for rev_data in self._revision_data:
      self._process_revision_data(rev_data)

    self.collect_data.add_cvs_file(self.cvs_file)

    self._process_symbol_data()

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
    self.stats_keeper.record_cvs_item(cvs_item)

  def flush(self):
    self._cvs_item_store.close()
    self.symbol_stats.write()


