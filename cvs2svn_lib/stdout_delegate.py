# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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


from cvs2svn_lib.boolean import *
from cvs2svn_lib.log import Log
from cvs2svn_lib.svn_repository_mirror import SVNRepositoryMirrorDelegate


class StdoutDelegate(SVNRepositoryMirrorDelegate):
  """Makes no changes to the disk, but writes out information to
  STDOUT about what the SVNRepositoryMirror is doing.  Of course, our
  print statements will state that we're doing something, when in
  reality, we aren't doing anything other than printing out that we're
  doing something.  Kind of zen, really."""

  def __init__(self, total_revs):
    self.total_revs = total_revs

  def start_commit(self, revnum, revprops):
    """Prints out the Subversion revision number of the commit that is
    being started."""

    Log().verbose("=" * 60)
    Log().normal("Starting Subversion r%d / %d" % (revnum, self.total_revs))

  def end_commit(self):
    pass

  def initialize_project(self, project):
    Log().verbose("  Initializing project %s" % (project,))

  def initialize_lod(self, lod):
    Log().verbose("  Initializing %s" % (lod,))

  def mkdir(self, path):
    """Print a line stating that we are creating directory PATH."""

    Log().verbose("  New Directory %s" % (path,))

  def add_path(self, s_item):
    """Print a line stating what path we are 'adding'."""

    Log().verbose("  Adding %s" % (s_item.cvs_rev.get_svn_path(),))

  def change_path(self, s_item):
    """Print a line stating what path we are 'changing'."""

    Log().verbose("  Changing %s" % (s_item.cvs_rev.get_svn_path(),))

  def delete_lod(self, lod):
    """Print a line stating that we are 'deleting' LOD."""

    Log().verbose("  Deleting %s" % (lod.get_path(),))

  def delete_path(self, path):
    """Print a line stating that we are 'deleting' PATH."""

    Log().verbose("  Deleting %s" % (path,))

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Print a line stating that we are 'copying' revision SRC_REVNUM
    of SRC_PATH to DEST_PATH."""

    self.copy_path(src_lod.get_path(), dest_lod.get_path(), src_revnum)

  def copy_path(self, src_path, dest_path, src_revnum):
    """Print a line stating that we are 'copying' revision SRC_REVNUM
    of SRC_PATH to DEST_PATH."""

    Log().verbose(
        "  Copying revision %d of %s\n"
        "                to %s\n"
        % (src_revnum, src_path, dest_path,)
        )

  def finish(self):
    """State that we are done creating our repository."""

    Log().verbose("Finished creating Subversion repository.")
    Log().quiet("Done.")


