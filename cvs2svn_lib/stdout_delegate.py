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


from boolean import *
from log import Log
from svn_repository_mirror import SVNRepositoryMirrorDelegate


class StdoutDelegate(SVNRepositoryMirrorDelegate):
  """Makes no changes to the disk, but writes out information to
  STDOUT about what the SVNRepositoryMirror is doing.  Of course, our
  print statements will state that we're doing something, when in
  reality, we aren't doing anything other than printing out that we're
  doing something.  Kind of zen, really."""

  def __init__(self, total_revs):
    self.total_revs = total_revs

  def start_commit(self, svn_commit):
    """Prints out the Subversion revision number of the commit that is
    being started."""

    Log().verbose("=" * 60)
    Log().normal("Starting Subversion r%d / %d"
                 % (svn_commit.revnum, self.total_revs))

  def mkdir(self, path):
    """Print a line stating that we are creating directory PATH."""

    Log().verbose("  New Directory", path)

  def add_path(self, s_item):
    """Print a line stating that we are 'adding' s_item.c_rev.svn_path."""

    Log().verbose("  Adding", s_item.c_rev.svn_path)

  def change_path(self, s_item):
    """Print a line stating that we are 'changing' s_item.c_rev.svn_path."""

    Log().verbose("  Changing", s_item.c_rev.svn_path)

  def delete_path(self, path):
    """Print a line stating that we are 'deleting' PATH."""

    Log().verbose("  Deleting", path)

  def copy_path(self, src_path, dest_path, src_revnum):
    """Print a line stating that we are 'copying' revision SRC_REVNUM
    of SRC_PATH to DEST_PATH."""

    Log().verbose("  Copying revision", src_revnum, "of", src_path)
    Log().verbose("                to", dest_path)

  def finish(self):
    """State that we are done creating our repository."""

    Log().verbose("Finished creating Subversion repository.")
    Log().quiet("Done.")


