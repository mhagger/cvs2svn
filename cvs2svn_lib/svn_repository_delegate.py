# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

"""This module contains the SVNRepositoryDelegate class."""


class SVNRepositoryDelegate:
  """Abstract superclass for any delegate to SVNOutputOption.

  Subclasses must implement all of the methods below.

  For each method, a subclass implements, in its own way, the
  Subversion operation implied by the method's name.  For example, for
  the add_path method, the DumpstreamDelegate writes out a 'Node-add:'
  command to a Subversion dumpfile."""

  def start_commit(self, revnum, revprops):
    """An SVN commit is starting.

    Perform any actions needed to start an SVN commit with revision
    number REVNUM and revision properties REVPROPS."""

    raise NotImplementedError()

  def end_commit(self):
    """An SVN commit is ending."""

    raise NotImplementedError()

  def initialize_project(self, project):
    """Initialize PROJECT.

    For Subversion, this means to create the trunk, branches, and tags
    directories for PROJECT."""

    raise NotImplementedError()

  def initialize_lod(self, lod):
    """Initialize LOD with no contents.

    LOD is an instance of LineOfDevelopment.  It is also possible for
    an LOD to be created by copying from another LOD; such events are
    indicated via the copy_lod() callback."""

    raise NotImplementedError()

  def mkdir(self, lod, cvs_directory):
    """Create CVS_DIRECTORY within LOD.

    LOD is a LineOfDevelopment; CVS_DIRECTORY is a CVSDirectory."""

    raise NotImplementedError()

  def add_path(self, cvs_rev):
    """Add the path corresponding to CVS_REV to the repository.

    CVS_REV is a CVSRevisionAdd."""

    raise NotImplementedError()

  def change_path(self, cvs_rev):
    """Change the path corresponding to CVS_REV in the repository.

    CVS_REV is a CVSRevisionChange."""

    raise NotImplementedError()

  def delete_lod(self, lod):
    """Delete LOD from the repository.

    LOD is a LineOfDevelopment instance."""

    raise NotImplementedError()

  def delete_path(self, lod, cvs_path):
    """Delete CVS_PATH from LOD.

    LOD is a LineOfDevelopment; CVS_PATH is a CVSPath."""

    raise NotImplementedError()

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy SRC_LOD in SRC_REVNUM to DEST_LOD.

    SRC_LOD and DEST_LOD are both LODs, and SRC_REVNUM is a subversion
    revision number (int)."""

    raise NotImplementedError()

  def copy_path(self, cvs_path, src_lod, dest_lod, src_revnum):
    """Copy CVS_PATH in SRC_LOD@SRC_REVNUM to DEST_LOD.

    CVS_PATH is a CVSPath, SRC_LOD and DEST_LOD are LODs, and
    SRC_REVNUM is a subversion revision number (int)."""

    raise NotImplementedError()

  def finish(self):
    """All SVN revisions have been committed.

    Perform any necessary cleanup."""

    raise NotImplementedError()


