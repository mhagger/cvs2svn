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


import fileinput

from boolean import *
import config
from common import OP_DELETE
from context import Ctx
from artifact_manager import artifact_manager
from database import DB_OPEN_READ
from cvs_revision_database import CVSRevisionDatabase
from svn_revision_range import SVNRevisionRange


# Constants used in SYMBOL_OPENINGS_CLOSINGS
OPENING = 'O'
CLOSING = 'C'


class SymbolingsLogger:
  """Manage the file that contains lines for symbol openings and
  closings.

  This data will later be used to determine valid SVNRevision ranges
  from which a file can be copied when creating a branch or tag in
  Subversion.  Do this by finding "Openings" and "Closings" for each
  file copied onto a branch or tag.

  An "Opening" is the CVSRevision from which a given branch/tag
  sprouts on a path.

  The "Closing" for that branch/tag and path is the next CVSRevision
  on the same line of development as the opening.

  For example, on file 'foo.c', branch BEE has branch number 1.2.2 and
  obviously sprouts from revision 1.2.  Therefore, 1.2 is the opening
  for BEE on path 'foo.c', and 1.3 is the closing for BEE on path
  'foo.c'.  Note that there may be many revisions chronologically
  between 1.2 and 1.3, for example, revisions on branches of 'foo.c',
  perhaps even including on branch BEE itself.  But 1.3 is the next
  revision *on the same line* as 1.2, that is why it is the closing
  revision for those symbolic names of which 1.2 is the opening.

  The reason for doing all this hullabaloo is to make branch and tag
  creation as efficient as possible by minimizing the number of copies
  and deletes per creation.  For example, revisions 1.2 and 1.3 of
  foo.c might correspond to revisions 17 and 30 in Subversion.  That
  means that when creating branch BEE, there is some motivation to do
  the copy from one of 17-30.  Now if there were another file,
  'bar.c', whose opening and closing CVSRevisions for BEE corresponded
  to revisions 24 and 39 in Subversion, we would know that the ideal
  thing would be to copy the branch from somewhere between 24 and 29,
  inclusive.
  """

  def __init__(self):
    self.symbolings = open(
        artifact_manager.get_temp_file(config.SYMBOL_OPENINGS_CLOSINGS), 'w')
    self.closings = open(
        artifact_manager.get_temp_file(config.SYMBOL_CLOSINGS_TMP), 'w')

    # This keys of this dictionary are *source* cvs_paths for which
    # we've encountered an 'opening' on the default branch.  The
    # values are the (uncleaned) symbolic names that this path has
    # opened.
    self.open_paths_with_default_branches = { }

  def log_revision(self, c_rev, svn_revnum):
    """Log any openings found in C_REV, and if C_REV.next_id is not
    None, a closing.  The opening uses SVN_REVNUM, but the closing (if
    any) will have its revnum determined later."""

    for name in c_rev.tags + c_rev.branches:
      self._note_default_branch_opening(c_rev, name)
      if c_rev.op != OP_DELETE:
        self._log(
            name, svn_revnum,
            c_rev.cvs_file,
            c_rev.cvs_branch.is_branch() and c_rev.cvs_branch.name,
            OPENING)

      # If our c_rev has a next_rev, then that's the closing rev for
      # this source revision.  Log it to closings for later processing
      # since we don't know the svn_revnum yet.
      if c_rev.next_id is not None:
        self.closings.write('%s %x\n' % (name, c_rev.next_id))

  def _log(self, name, svn_revnum, cvs_file, branch_name, type):
    """Write out a single line to the symbol_openings_closings file
    representing that SVN_REVNUM of SVN_FILE on BRANCH_NAME is either
    the opening or closing (TYPE) of NAME (a symbolic name).

    TYPE should only be one of the following constants: OPENING or
    CLOSING."""

    # 8 places gives us 999,999,999 SVN revs.  That *should* be enough.
    self.symbolings.write(
        '%s %.8d %s %s %x\n'
        % (name, svn_revnum, type, branch_name or '*', cvs_file.id))

  def close(self):
    """Iterate through the closings file, lookup the svn_revnum for
    each closing CVSRevision, and write a proper line out to the
    symbolings file."""

    # Use this to get the c_rev of our rev_key
    cvs_revs_db = CVSRevisionDatabase(
        artifact_manager.get_temp_file(config.CVS_REVS_RESYNC_DB),
        DB_OPEN_READ)

    self.closings.close()
    for line in fileinput.FileInput(
            artifact_manager.get_temp_file(config.SYMBOL_CLOSINGS_TMP)):
      (name, rev_key) = line.rstrip().split(" ", 1)
      rev_id = int(rev_key, 16)
      svn_revnum = Ctx()._persistence_manager.get_svn_revnum(rev_id)

      c_rev = cvs_revs_db.get_revision(rev_id)
      self._log(
          name, svn_revnum,
          c_rev.cvs_file,
          c_rev.cvs_branch.is_branch() and c_rev.cvs_branch.name,
          CLOSING)

    self.symbolings.close()

  def _note_default_branch_opening(self, c_rev, symbolic_name):
    """If C_REV is a default branch revision, log C_REV.cvs_path as an
    opening for SYMBOLIC_NAME."""

    self.open_paths_with_default_branches.setdefault(
        c_rev.cvs_path, []).append(symbolic_name)

  def log_default_branch_closing(self, c_rev, svn_revnum):
    """If self.open_paths_with_default_branches contains
    C_REV.cvs_path, then call log each name in
    self.open_paths_with_default_branches[C_REV.cvs_path] as a closing
    with SVN_REVNUM as the closing revision number."""

    path = c_rev.cvs_path
    if self.open_paths_with_default_branches.has_key(path):
      # log each symbol as a closing
      for name in self.open_paths_with_default_branches[path]:
        self._log(name, svn_revnum, c_rev.cvs_file, None, CLOSING)
      # Remove them from the openings list as we're done with them.
      del self.open_paths_with_default_branches[path]


class OpeningsClosingsMap:
  """A dictionary of openings and closings for a symbolic name in the
  current SVNCommit.

  The user should call self.register() for the openings and closings,
  then self.get_node_tree() to retrieve the information as a
  SymbolicNameFillingGuide."""

  def __init__(self, symbolic_name):
    """Initialize OpeningsClosingsMap and prepare it for receiving
    openings and closings."""

    self.name = symbolic_name

    # A dictionary of SVN_PATHS to SVNRevisionRange objects.
    self.things = { }

  def register(self, svn_path, svn_revnum, type):
    """Register an opening or closing revision for this symbolic name.
    SVN_PATH is the source path that needs to be copied into
    self.symbolic_name, and SVN_REVNUM is either the first svn
    revision number that we can copy from (our opening), or the last
    (not inclusive) svn revision number that we can copy from (our
    closing).  TYPE indicates whether this path is an opening or a a
    closing.

    The opening for a given SVN_PATH must be passed before the closing
    for it to have any effect... any closing encountered before a
    corresponding opening will be discarded.

    It is not necessary to pass a corresponding closing for every
    opening."""

    # Always log an OPENING
    if type == OPENING:
      self.things[svn_path] = SVNRevisionRange(svn_revnum)
    # Only log a closing if we've already registered the opening for that
    # path.
    elif type == CLOSING and self.things.has_key(svn_path):
      self.things[svn_path].add_closing(svn_revnum)

  def is_empty(self):
    """Return true if we haven't accumulated any openings or closings,
    false otherwise."""

    return not len(self.things)

  def get_things(self):
    """Return a list of (svn_path, SVNRevisionRange) tuples for all
    svn_paths with registered openings or closings."""

    return self.things.items()


