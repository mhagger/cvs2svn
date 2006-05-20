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


import sys
import os
import re
import time
import sha
import stat

from boolean import *
import config
from common import warning_prefix
from common import error_prefix
from common import OP_ADD
from common import OP_CHANGE
from common import OP_DELETE
from log import Log
from context import Ctx
from artifact_manager import artifact_manager
from cvs_file import CVSFile
from cvs_revision import CVSRevision
from cvs_revision import CVSRevisionID
from stats_keeper import StatsKeeper
from key_generator import KeyGenerator
from database import Database
from database import SDatabase
from database import DB_OPEN_NEW
from cvs_file_database import CVSFileDatabase
from cvs_revision_database import CVSRevisionDatabase
from symbol_database import SymbolDatabase

import cvs2svn_rcsparse


OS_SEP_PLUS_ATTIC = os.sep + 'Attic'

trunk_rev = re.compile(r'^[0-9]+\.[0-9]+$')
cvs_branch_tag = re.compile(r'^((?:[0-9]+\.[0-9]+\.)+)0\.([0-9]+)$')
rcs_branch_tag = re.compile(r'^(?:[0-9]+\.[0-9]+\.)+[0-9]+$')

# This really only matches standard '1.1.1.*'-style vendor revisions.
# One could conceivably have a file whose default branch is 1.1.3 or
# whatever, or was that at some point in time, with vendor revisions
# 1.1.3.1, 1.1.3.2, etc.  But with the default branch gone now (which
# is the only time this regexp gets used), we'd have no basis for
# assuming that the non-standard vendor branch had ever been the
# default branch anyway, so we don't want this to match them anyway.
vendor_revision = re.compile(r'^(1\.1\.1)\.([0-9])+$')


def is_branch_revision(rev):
  """Return True iff this revision is not a trunk revision."""

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

  def __init__(self, id, rev, timestamp, author, state, branches):
    self.id = id
    self.rev = rev
    self.timestamp = timestamp
    self.author = author
    self.original_timestamp = timestamp
    self._adjusted = False
    self.state = state

    # Numbers of branch first revisions sprouting from this revision,
    # as specified by define_revision():
    self.branches = branches

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
    self.primary_child = None

    # The revision numbers of any children that depend on this revision:
    self.children = []

  def adjust_timestamp(self, timestamp):
    self._adjusted = True
    self.timestamp = timestamp

  def timestamp_was_adjusted(self):
    return self._adjusted


class FileDataCollector(cvs2svn_rcsparse.Sink):
  """Class responsible for collecting RCS data for a particular file.

  Any collected data that need to be remembered are stored into the
  referenced CollectData instance."""

  def __init__(self, collect_data, filename):
    """Create an object that is prepared to receive data for FILENAME.
    FILENAME is the absolute filesystem path to the file in question.
    COLLECT_DATA is used to store the information collected about the
    file."""

    self.collect_data = collect_data

    (dirname, basename,) = os.path.split(filename)
    if dirname.endswith(OS_SEP_PLUS_ATTIC):
      # drop the 'Attic' portion from the filename for the canonical name:
      canonical_filename = os.path.join(
          dirname[:-len(OS_SEP_PLUS_ATTIC)], basename)
      file_in_attic = True
    else:
      canonical_filename = filename
      file_in_attic = False

    # We calculate and save some file metadata here, where we can do
    # it only once per file, instead of waiting until later where we
    # would have to do the same calculations once per CVS *revision*.

    cvs_path = Ctx().cvs_repository.get_cvs_path(canonical_filename)

    file_stat = os.stat(filename)
    # The size of our file in bytes
    file_size = file_stat[stat.ST_SIZE]

    # Whether or not the executable bit is set.
    file_executable = bool(file_stat[0] & stat.S_IXUSR)

    # mode is not known yet, so we temporarily set it to None.
    self.cvs_file = CVSFile(
        None, filename, canonical_filename, cvs_path,
        file_in_attic, file_executable, file_size, None
        )

    # A list [ ( name, revision) ] of each known symbol in this file
    # with the revision number that it corresponds to.
    self._symbols = []

    # A map { revision -> c_rev } of the CVSRevision instances for all
    # revisions related to this file.  Note that items in this map
    # might be pre-filled as CVSRevisionIDs for revisions referred to
    # by earlier revisions but not yet processed.  As the revisions
    # are defined, the values are changed into CVSRevision instances.
    self._c_revs = {}

    # { revision : _RevisionData instance }
    self._rev_data = { }

    # A list [ revision ] of the revision numbers seen, in the order
    # they were given to us by rcsparse:
    self._rev_order = []

    # Lists [ (parent, child) ] of revision number pairs indicating
    # that child depends on parent.  _primary_dependencies are
    # dependencies along the main line of
    # development. _branch_dependencies are dependencies of the first
    # revision on the branch on the sprout revision.
    self._primary_dependencies = []
    self._branch_dependencies = []

    # Hash mapping branch numbers, like '1.7.2', to branch names,
    # like 'Release_1_0_dev'.
    self.branch_names = { }

    # Hash mapping revision numbers, like '1.7', to lists of names
    # indicating which branches sprout from that revision, like
    # ['Release_1_0_dev', 'experimental_driver', ...].
    self.branchlist = { }

    # Like self.branchlist, but the values are lists of tag names that
    # apply to the key revision.
    self.taglist = { }

    # If set, this is an RCS branch number -- rcsparse calls this the
    # "principal branch", but CVS and RCS refer to it as the "default
    # branch", so that's what we call it, even though the rcsparse API
    # setter method is still 'set_principal_branch'.
    self.default_branch = None

    # If the RCS file doesn't have a default branch anymore, but does
    # have vendor revisions, then we make an educated guess that those
    # revisions *were* the head of the default branch up until the
    # commit of 1.2, at which point the file's default branch became
    # trunk.  This records the date at which 1.2 was committed.
    self.first_non_vendor_revision_date = None

  def _make_rev_id(self, revision):
    assert revision is not None
    assert not self._c_revs.has_key(revision)
    rev_id = CVSRevisionID(
        self.collect_data.key_generator.gen_id(), self.cvs_file, revision)
    self._c_revs[revision] = rev_id
    return rev_id.id

  def _get_rev_id(self, revision):
    if revision is None:
      return None
    return self._c_revs.get(revision).id

  def set_principal_branch(self, branch):
    """This is a callback method declared in Sink."""

    self.default_branch = branch

  def set_expansion(self, mode):
    """This is a callback method declared in Sink."""

    self.cvs_file.mode = mode

  def define_tag(self, name, revision):
    """Remember the symbol name and revision, but don't process them yet.

    This is a callback method declared in Sink."""

    self._symbols.append( (name, revision,) )

  def set_branch_name(self, branch_number, name):
    """Record that BRANCH_NUMBER is the branch number for branch NAME,
    and derive and record the revision from which NAME sprouts.
    BRANCH_NUMBER is an RCS branch number with an odd number of
    components, for example '1.7.2' (never '1.7.0.2')."""

    if self.branch_names.has_key(branch_number):
      sys.stderr.write("%s: in '%s':\n"
                       "   branch '%s' already has name '%s',\n"
                       "   cannot also have name '%s', ignoring the latter\n"
                       % (warning_prefix,
                          self.cvs_file.filename, branch_number,
                          self.branch_names[branch_number], name))
      return

    self.branch_names[branch_number] = name
    # The branchlist is keyed on the revision number from which the
    # branch sprouts, so strip off the odd final component.
    sprout_rev = branch_number[:branch_number.rfind(".")]
    self.branchlist.setdefault(sprout_rev, []).append(name)
    self.collect_data.symbol_db.register_branch_creation(name)

  def set_tag_name(self, revision, name):
    """Record that tag NAME refers to the specified REVISION."""

    self.taglist.setdefault(revision, []).append(name)
    self.collect_data.symbol_db.register_tag_creation(name)

  def rev_to_branch_name(self, revision):
    """Return the name of the branch on which REVISION lies.
    REVISION is a non-branch revision number with an even number of,
    components, for example '1.7.2.1' (never '1.7.2' nor '1.7.0.2').
    For the convenience of callers, REVISION can also be a trunk
    revision such as '1.2', in which case just return None."""

    if trunk_rev.match(revision):
      return None
    return self.branch_names.get(revision[:revision.rindex(".")])

  def _process_symbol(self, name, revision):
    """Record a bidirectional mapping between symbolic NAME and REVISION.
    REVISION is an unprocessed revision number from the RCS file's
    header, for example: '1.7', '1.7.0.2', or '1.1.1' or '1.1.1.1'.
    This function will determine what kind of symbolic name it is by
    inspection, and record it in the right places."""

    m = cvs_branch_tag.match(revision)
    if m:
      self.set_branch_name(m.group(1) + m.group(2), name)
    elif rcs_branch_tag.match(revision):
      self.set_branch_name(revision, name)
    else:
      self.set_tag_name(revision, name)

  def _transform_symbol(self, name):
    """Transform the symbol NAME using the renaming rules specified
    with --symbol-transform.  Return the transformed symbol name."""

    for (pattern, replacement) in Ctx().symbol_transforms:
      newname = pattern.sub(replacement, name)
      if newname != name:
        Log().warn("   symbol '%s' transformed to '%s'" % (name, newname))
        name = newname

    return name

  def _process_symbols(self):
    # A list of all symbols defined for the current file.  Used to
    # prevent multiple definitions of a symbol, something which can
    # easily happen when --symbol-transform is used.
    defined_symbols = { }

    for (name, revision,) in self._symbols:
      name = self._transform_symbol(name)

      if defined_symbols.has_key(name):
        err = "%s: Multiple definitions of the symbol '%s' in '%s'" \
                  % (error_prefix, name, self.cvs_file.filename)
        sys.stderr.write(err + "\n")
        self.collect_data.fatal_errors.append(err)

      defined_symbols[name] = None

      self._process_symbol(name, revision)

    # Free memory:
    self._symbols = None

  def admin_completed(self):
    """This is a callback method declared in Sink."""

    self._process_symbols()
    self.collect_data.add_cvs_file(self.cvs_file)

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    """This is a callback method declared in Sink."""

    rev_data = _RevisionData(
        self._make_rev_id(revision),
        revision, int(timestamp), author, state, branches)
    self._rev_order.append(revision)
    self._rev_data[revision] = rev_data

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
    #
    # One last thing.  Note that if REVISION is a branch revision,
    # instead of mapping REVISION to NEXT, we instead map NEXT to
    # REVISION.  Since we loop over all revisions in the file before
    # doing anything with the data we gather here, this 'reverse
    # assignment' effectively does the following:
    #
    # 1. Gives us no 'prev' value for REVISION (in this
    # iteration... it may have been set in a previous iteration)
    #
    # 2. Sets the 'prev' value for the revision with number NEXT to
    # REVISION.  So when we come around to the branch revision whose
    # revision value is NEXT, its 'prev' and 'prev_rev' are already
    # set.
    if next:
      if trunk_rev.match(revision):
        self._primary_dependencies.append( (next, revision,) )
      else:
        self._primary_dependencies.append( (revision, next,) )

  def _set_branch_dependencies(self, rev_data):
    """Set any branches sprouting from REV_DATA to depend on it."""

    for b in rev_data.branches:
      self._branch_dependencies.append( (rev_data.rev, b) )

  def _resolve_dependencies(self):
    """Store the dependencies in self._primary_dependencies and
    self._branch_dependencies into the rev_data objects."""

    for (parent, child,) in self._primary_dependencies:
      parent_data = self._rev_data[parent]
      assert parent_data.primary_child is None
      parent_data.primary_child = child
      parent_data.children.append(child)

      child_data = self._rev_data[child]
      assert child_data.parent is None
      child_data.parent = parent

    for (parent, child,) in self._branch_dependencies:
      parent_data = self._rev_data[parent]
      parent_data.children.append(child)

      child_data = self._rev_data[child]
      assert child_data.parent is None
      child_data.parent = parent

    # Free memory:
    self._primary_dependencies = None
    self._branch_dependencies = None

  def _update_default_branch(self, rev_data):
    """Ratchet up the highest vendor head revision based on REV_DATA,
    if necessary."""

    if self.default_branch:
      default_branch_root = self.default_branch + "."
      if (rev_data.rev.startswith(default_branch_root)
          and default_branch_root.count('.') == rev_data.rev.count('.')):
        # This revision is on the default branch, so record that it is
        # the new highest default branch head revision.
        self.collect_data.default_branches_db[self.cvs_file.cvs_path] = \
            rev_data.rev
    else:
      # No default branch, so make an educated guess.
      if rev_data.rev == '1.2':
        # This is probably the time when the file stopped having a
        # default branch, so make a note of it.
        self.first_non_vendor_revision_date = rev_data.timestamp
      else:
        m = vendor_revision.match(rev_data.rev)
        if m and ((not self.first_non_vendor_revision_date)
                  or (rev_data.timestamp
                      < self.first_non_vendor_revision_date)):
          # We're looking at a vendor revision, and it wasn't
          # committed after this file lost its default branch, so bump
          # the maximum trunk vendor revision in the permanent record.
          self.collect_data.default_branches_db[self.cvs_file.cvs_path] = \
              rev_data.rev

  def _register_branch_commit(self, rev):
    """Register REV, which is a non-trunk revision number, as a commit
    on the corresponding branch."""

    # Check for unlabeled branches, record them.  We tried to collect
    # all branch names when we parsed the symbolic name header
    # earlier, of course, but that didn't catch unlabeled branches.
    # If a branch is unlabeled, this is our first encounter with it,
    # so we have to record its data now.
    branch_number = rev[:rev.rindex(".")]
    if not self.branch_names.has_key(branch_number):
      branch_name = "unlabeled-" + branch_number
      self.set_branch_name(branch_number, branch_name)

    # Register the commit on this non-trunk branch
    branch_name = self.branch_names[branch_number]
    self.collect_data.symbol_db.register_branch_commit(branch_name)

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

      self._set_branch_dependencies(rev_data)

      self._update_default_branch(rev_data)

      if not trunk_rev.match(rev_data.rev):
        self._register_branch_commit(rev_data.rev)

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
    cur_num = rev_data.rev
    if is_branch_revision(rev_data.rev) and rev_data.state != 'dead':
      while 1:
        prev_num = self._rev_data[cur_num].parent
        if not cur_num or not prev_num:
          break
        if (not is_same_line_of_development(cur_num, prev_num)
            and self._rev_data[cur_num].state == 'dead'
            and self._rev_data[prev_num].state != 'dead'):
          op = OP_CHANGE
        cur_num = self._rev_data[cur_num].parent

    return op

  def set_revision_info(self, revision, log, text):
    """This is a callback method declared in Sink."""

    rev_data = self._rev_data[revision]
    digest = sha.new(log + '\0' + rev_data.author).hexdigest()
    if rev_data.timestamp_was_adjusted():
      # the timestamp on this revision was changed. log it for later
      # resynchronization of other files's revisions that occurred
      # for this time and log message.
      self.collect_data.resync.write(
          '%08lx %s %08lx\n'
          % (rev_data.original_timestamp, digest, rev_data.timestamp))

    # "...Give back one kadam to honor the Hebrew God whose Ark this is."
    #       -- Imam to Indy and Sallah, in 'Raiders of the Lost Ark'
    #
    # If revision 1.1 appears to have been created via 'cvs add'
    # instead of 'cvs import', then this file probably never had a
    # default branch, so retroactively remove its record in the
    # default branches db.  The test is that the log message CVS uses
    # for 1.1 in imports is "Initial revision\n" with no period.
    if revision == '1.1' and log != 'Initial revision\n':
      try:
        del self.collect_data.default_branches_db[self.cvs_file.cvs_path]
      except KeyError:
        pass

    # Get the timestamps of the previous and next revisions
    prev_rev = rev_data.parent
    prev_rev_data = self._rev_data.get(prev_rev)
    if prev_rev_data is None:
      prev_timestamp = 0
    else:
      prev_timestamp = prev_rev_data.timestamp

    next_rev = rev_data.primary_child
    next_rev_data = self._rev_data.get(next_rev)
    if next_rev_data is None:
      next_timestamp = 0
    else:
      next_timestamp = next_rev_data.timestamp

    c_rev = CVSRevision(
        self._get_rev_id(revision), self.cvs_file,
        rev_data.timestamp, digest,
        self._get_rev_id(prev_rev), self._get_rev_id(next_rev),
        prev_timestamp, next_timestamp, self._determine_operation(rev_data),
        prev_rev, revision, next_rev,
        bool(text),
        self.rev_to_branch_name(revision),
        self.taglist.get(revision, []), self.branchlist.get(revision, []))
    self._c_revs[revision] = c_rev
    self.collect_data.add_cvs_revision(c_rev)

    if not self.collect_data.metadata_db.has_key(digest):
      self.collect_data.metadata_db[digest] = (rev_data.author, log)

  def parse_completed(self):
    """Walk through all branches and tags and register them with their
    parent branch in the symbol database.

    This is a callback method declared in Sink."""

    for revision, symbols in self.taglist.items() + self.branchlist.items():
      for symbol in symbols:
        name = self.rev_to_branch_name(revision)
        if name is not None:
          self.collect_data.symbol_db.register_branch_blocker(name, symbol)

    self.collect_data.num_files += 1


class CollectData:
  """Repository for data collected by parsing the CVS repository files.

  This class manages the databases into which information collected
  from the CVS repository is stored.  The data are stored into this
  class by FileDataCollector instances, one of which is created for
  each file to be parsed."""

  def __init__(self):
    self._cvs_file_db = CVSFileDatabase(
        artifact_manager.get_temp_file(config.CVS_FILES_DB), DB_OPEN_NEW)
    self._cvs_revs_db = CVSRevisionDatabase(
        self._cvs_file_db,
        artifact_manager.get_temp_file(config.CVS_REVS_DB), DB_OPEN_NEW)
    self._all_revs = open(
        artifact_manager.get_temp_file(config.ALL_REVS_DATAFILE), 'w')
    self.resync = open(
        artifact_manager.get_temp_file(config.RESYNC_DATAFILE), 'w')
    self.default_branches_db = SDatabase(
        artifact_manager.get_temp_file(config.DEFAULT_BRANCHES_DB),
        DB_OPEN_NEW)
    self.metadata_db = Database(
        artifact_manager.get_temp_file(config.METADATA_DB), DB_OPEN_NEW)
    self.fatal_errors = []
    self.num_files = 0
    self.symbol_db = SymbolDatabase()

    # 1 if we've collected data for at least one file, None otherwise.
    self.found_valid_file = None

    # Key generator to generate unique keys for each CVSFile object:
    self.file_key_generator = KeyGenerator(1)

    # Key generator to generate unique keys for each CVSRevision object:
    self.key_generator = KeyGenerator()

  def add_cvs_file(self, cvs_file):
    """If CVS_FILE is not already stored to _cvs_revs_db, give it a
    persistent id and store it now.  The way we tell whether it was
    already stored is by whether it already has a non-None id."""

    assert cvs_file.id is None
    cvs_file.id = self.file_key_generator.gen_id()
    self._cvs_file_db.log_file(cvs_file)

  def add_cvs_revision(self, c_rev):
    self._cvs_revs_db.log_revision(c_rev)
    self._all_revs.write('%s\n' % (c_rev.unique_key(),))
    StatsKeeper().record_c_rev(c_rev)

  def write_symbol_db(self):
    self.symbol_db.write()


