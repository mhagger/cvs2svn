# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

"""Classes for outputting the converted repository to SVN."""


import os
import re

from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import format_date
from cvs2svn_lib.common import IllegalSVNPathError
from cvs2svn_lib.common import PathsNotDisjointException
from cvs2svn_lib.common import verify_paths_disjoint
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.process import CommandFailedException
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import call_command
from cvs2svn_lib.cvs_path import CVSDirectory
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import LineOfDevelopment
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.repository_mirror import RepositoryMirror
from cvs2svn_lib.repository_mirror import PathExistsError
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.fill_source import get_source_set
from cvs2svn_lib.svn_dump import DumpstreamDelegate
from cvs2svn_lib.svn_dump import LoaderPipe
from cvs2svn_lib.output_option import OutputOption


class SVNOutputOption(OutputOption):
  """An OutputOption appropriate for output to Subversion."""

  name = 'Subversion'

  class ParentMissingError(Exception):
    """The parent of a path is missing.

    Exception raised if an attempt is made to add a path to the
    repository mirror but the parent's path doesn't exist in the
    youngest revision of the repository."""

    pass

  class ExpectedDirectoryError(Exception):
    """A file was found where a directory was expected."""

    pass

  def __init__(self, author_transforms=None):
    self._mirror = RepositoryMirror()

    def to_utf8(s):
      if isinstance(s, unicode):
        return s.encode('utf8')
      else:
        return s

    self.author_transforms = {}
    if author_transforms is not None:
      for (cvsauthor, name) in author_transforms.iteritems():
        cvsauthor = to_utf8(cvsauthor)
        name = to_utf8(name)
        self.author_transforms[cvsauthor] = name

  def register_artifacts(self, which_pass):
    # These artifacts are needed for SymbolingsReader:
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OPENINGS_CLOSINGS_SORTED, which_pass
        )
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OFFSETS_DB, which_pass
        )

    self._mirror.register_artifacts(which_pass)
    Ctx().revision_reader.register_artifacts(which_pass)

  # Characters not allowed in Subversion filenames:
  illegal_filename_characters_re = re.compile('[\\\x00-\\\x1f\\\x7f]')

  def verify_filename_legal(self, filename):
    OutputOption.verify_filename_legal(self, filename)

    m = SVNOutputOption.illegal_filename_characters_re.search(filename)
    if m:
      raise IllegalSVNPathError(
          '%s does not allow character %r in filename %r.'
          % (self.name, m.group(), filename,)
          )

  def check_symbols(self, symbol_map):
    """Check that the paths of all included LODs are set and disjoint."""

    error_found = False

    # Check that all included LODs have their base paths set, and
    # collect the paths into a list:
    paths = []
    for lod in symbol_map.itervalues():
      if isinstance(lod, LineOfDevelopment):
        if lod.base_path is None:
          logger.error('%s: No path was set for %r\n' % (error_prefix, lod,))
          error_found = True
        else:
          paths.append(lod.base_path)

    # Check that the SVN paths of all LODS are disjoint:
    try:
      verify_paths_disjoint(*paths)
    except PathsNotDisjointException, e:
      logger.error(str(e))
      error_found = True

    if error_found:
      raise FatalException(
          'Please fix the above errors and restart CollateSymbolsPass'
          )

  def setup(self, svn_rev_count):
    self._symbolings_reader = SymbolingsReader()
    self._mirror.open()
    self._delegates = []
    Ctx().revision_reader.start()
    self.svn_rev_count = svn_rev_count

  def _get_author(self, svn_commit):
    author = svn_commit.get_author()
    name = self.author_transforms.get(author, author)
    return name

  def _get_revprops(self, svn_commit):
    """Return the Subversion revprops for this SVNCommit."""

    return {
        'svn:author' : self._get_author(svn_commit),
        'svn:log'    : svn_commit.get_log_msg(),
        'svn:date'   : format_date(svn_commit.date),
        }

  def start_commit(self, revnum, revprops):
    """Start a new commit."""

    logger.verbose("=" * 60)
    logger.normal(
        "Starting Subversion r%d / %d" % (revnum, self.svn_rev_count)
        )

    self._mirror.start_commit(revnum)
    self._invoke_delegates('start_commit', revnum, revprops)

  def end_commit(self):
    """Called at the end of each commit.

    This method copies the newly created nodes to the on-disk nodes
    db."""

    self._mirror.end_commit()
    self._invoke_delegates('end_commit')

  def delete_lod(self, lod):
    """Delete the main path for LOD from the tree.

    The path must currently exist.  Silently refuse to delete trunk
    paths."""

    if isinstance(lod, Trunk):
      # Never delete a Trunk path.
      return

    logger.verbose("  Deleting %s" % (lod.get_path(),))
    self._mirror.get_current_lod_directory(lod).delete()
    self._invoke_delegates('delete_lod', lod)

  def delete_path(self, cvs_path, lod, should_prune=False):
    """Delete CVS_PATH from LOD."""

    if cvs_path.parent_directory is None:
      self.delete_lod(lod)
      return

    logger.verbose("  Deleting %s" % (lod.get_path(cvs_path.cvs_path),))
    parent_node = self._mirror.get_current_path(
        cvs_path.parent_directory, lod
        )
    del parent_node[cvs_path]
    self._invoke_delegates('delete_path', lod, cvs_path)

    if should_prune:
      while parent_node is not None and len(parent_node) == 0:
        # A drawback of this code is that we issue a delete for each
        # path and not just a single delete for the topmost directory
        # pruned.
        node = parent_node
        cvs_path = node.cvs_path
        if cvs_path.parent_directory is None:
          parent_node = None
          self.delete_lod(lod)
        else:
          parent_node = node.parent_mirror_dir
          node.delete()
          logger.verbose("  Deleting %s" % (lod.get_path(cvs_path.cvs_path),))
          self._invoke_delegates('delete_path', lod, cvs_path)

  def initialize_project(self, project):
    """Create the basic structure for PROJECT."""

    logger.verbose("  Initializing project %s" % (project,))
    self._invoke_delegates('initialize_project', project)

    # Don't invoke delegates.
    self._mirror.add_lod(project.get_trunk())
    if Ctx().include_empty_directories:
      self._make_empty_subdirectories(
          project.get_root_cvs_directory(), project.get_trunk()
          )

  def change_path(self, cvs_rev):
    """Register a change in self._youngest for the CVS_REV's svn_path."""

    logger.verbose("  Changing %s" % (cvs_rev.get_svn_path(),))
    # We do not have to update the nodes because our mirror is only
    # concerned with the presence or absence of paths, and a file
    # content change does not cause any path changes.
    self._invoke_delegates('change_path', cvs_rev)

  def _make_empty_subdirectories(self, cvs_directory, lod):
    """Make any empty subdirectories of CVS_DIRECTORY in LOD."""

    for empty_subdirectory_id in cvs_directory.empty_subdirectory_ids:
      empty_subdirectory = Ctx()._cvs_path_db.get_path(empty_subdirectory_id)
      logger.verbose(
          "  New Directory %s" % (lod.get_path(empty_subdirectory.cvs_path),)
          )
      # There is no need to record the empty subdirectories in the
      # mirror, since they live and die with their parent directories.
      self._invoke_delegates('mkdir', lod, empty_subdirectory)
      self._make_empty_subdirectories(empty_subdirectory, lod)

  def _mkdir_p(self, cvs_directory, lod):
    """Make sure that CVS_DIRECTORY exists in LOD.

    If not, create it, calling delegates.  Return the node for
    CVS_DIRECTORY."""

    ancestry = cvs_directory.get_ancestry()

    try:
      node = self._mirror.get_current_lod_directory(lod)
    except KeyError:
      logger.verbose("  Initializing %s" % (lod,))
      node = self._mirror.add_lod(lod)
      self._invoke_delegates('initialize_lod', lod)
      if ancestry and Ctx().include_empty_directories:
        self._make_empty_subdirectories(ancestry[0], lod)

    for sub_path in ancestry[1:]:
      try:
        node = node[sub_path]
      except KeyError:
        logger.verbose(
            "  New Directory %s" % (lod.get_path(sub_path.cvs_path),)
            )
        node = node.mkdir(sub_path)
        self._invoke_delegates('mkdir', lod, sub_path)
        if Ctx().include_empty_directories:
          self._make_empty_subdirectories(sub_path, lod)
      if node is None:
        raise self.ExpectedDirectoryError(
            'File found at \'%s\' where directory was expected.' % (sub_path,)
            )

    return node

  def add_path(self, cvs_rev):
    """Add the CVS_REV's svn_path to the repository mirror.

    Create any missing intermediate paths."""

    cvs_file = cvs_rev.cvs_file
    parent_path = cvs_file.parent_directory
    lod = cvs_rev.lod
    parent_node = self._mkdir_p(parent_path, lod)
    logger.verbose("  Adding %s" % (cvs_rev.get_svn_path(),))
    parent_node.add_file(cvs_file)
    self._invoke_delegates('add_path', cvs_rev)

  def _show_copy(self, src_path, dest_path, src_revnum):
    """Print a line stating that we are 'copying' revision SRC_REVNUM
    of SRC_PATH to DEST_PATH."""

    logger.verbose(
        "  Copying revision %d of %s\n"
        "                to %s\n"
        % (src_revnum, src_path, dest_path,)
        )

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    """Copy all of SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination LOD
    *must not* already exist.

    Return the new node at DEST_LOD.  Note that this node is not
    necessarily writable, though its parent node necessarily is."""

    self._show_copy(src_lod.get_path(), dest_lod.get_path(), src_revnum)
    node = self._mirror.copy_lod(src_lod, dest_lod, src_revnum)
    self._invoke_delegates('copy_lod', src_lod, dest_lod, src_revnum)
    return node

  def copy_path(
        self, cvs_path, src_lod, dest_lod, src_revnum, create_parent=False
        ):
    """Copy CVS_PATH from SRC_LOD at SRC_REVNUM to DST_LOD.

    In the youngest revision of the repository, the destination's
    parent *must* exist unless CREATE_PARENT is specified.  But the
    destination itself *must not* exist.

    Return the new node at (CVS_PATH, DEST_LOD), as a
    CurrentMirrorDirectory."""

    if cvs_path.parent_directory is None:
      return self.copy_lod(src_lod, dest_lod, src_revnum)

    # Get the node of our source, or None if it is a file:
    src_node = self._mirror.get_old_path(cvs_path, src_lod, src_revnum)

    # Get the parent path of the destination:
    if create_parent:
      dest_parent_node = self._mkdir_p(cvs_path.parent_directory, dest_lod)
    else:
      try:
        dest_parent_node = self._mirror.get_current_path(
            cvs_path.parent_directory, dest_lod
            )
      except KeyError:
        raise self.ParentMissingError(
            'Attempt to add path \'%s\' to repository mirror, '
            'but its parent directory doesn\'t exist in the mirror.'
            % (dest_lod.get_path(cvs_path.cvs_path),)
            )

    if cvs_path in dest_parent_node:
      raise PathExistsError(
          'Attempt to add path \'%s\' to repository mirror '
          'when it already exists in the mirror.'
          % (dest_lod.get_path(cvs_path.cvs_path),)
          )

    self._show_copy(
        src_lod.get_path(cvs_path.cvs_path),
        dest_lod.get_path(cvs_path.cvs_path),
        src_revnum,
        )
    dest_parent_node[cvs_path] = src_node
    self._invoke_delegates(
        'copy_path', cvs_path, src_lod, dest_lod, src_revnum
        )

    return dest_parent_node[cvs_path]

  def fill_symbol(self, svn_symbol_commit, fill_source):
    """Perform all copies for the CVSSymbols in SVN_SYMBOL_COMMIT.

    The symbolic name is guaranteed to exist in the Subversion
    repository by the end of this call, even if there are no paths
    under it."""

    symbol = svn_symbol_commit.symbol

    try:
      dest_node = self._mirror.get_current_lod_directory(symbol)
    except KeyError:
      self._fill_directory(symbol, None, fill_source, None)
    else:
      self._fill_directory(symbol, dest_node, fill_source, None)

  def _fill_directory(self, symbol, dest_node, fill_source, parent_source):
    """Fill the tag or branch SYMBOL at the path indicated by FILL_SOURCE.

    Use items from FILL_SOURCE, and recurse into the child items.

    Fill SYMBOL starting at the path FILL_SOURCE.cvs_path.  DEST_NODE
    is the node of this destination path, or None if the destination
    does not yet exist.  All directories above this path have already
    been filled.  FILL_SOURCE is a FillSource instance describing the
    items within a subtree of the repository that still need to be
    copied to the destination.

    PARENT_SOURCE is the SVNRevisionRange that was used to copy the
    parent directory, if it was copied in this commit.  We prefer to
    copy from the same source as was used for the parent, since it
    typically requires less touching-up.  If PARENT_SOURCE is None,
    then the parent directory was not copied in this commit, so no
    revision is preferable to any other."""

    copy_source = fill_source.compute_best_source(parent_source)

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if dest_node is None:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      dest_node = self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    elif (parent_source is not None) and (
          copy_source.source_lod != parent_source.source_lod
          or copy_source.opening_revnum != parent_source.opening_revnum
          ):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent then re-copy from the correct source:
      self.delete_path(fill_source.cvs_path, symbol)
      dest_node = self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    else:
      copy_source = parent_source

    # The map {CVSPath : FillSource} of entries within this directory
    # that need filling:
    src_entries = fill_source.get_subsource_map()

    if copy_source is not None:
      self._prune_extra_entries(
          fill_source.cvs_path, symbol, dest_node, src_entries
          )

    return self._cleanup_filled_directory(
        symbol, dest_node, src_entries, copy_source
        )

  def _cleanup_filled_directory(
        self, symbol, dest_node, src_entries, copy_source
        ):
    """The directory at DEST_NODE has been filled and pruned; recurse.

    Recurse into the SRC_ENTRIES, in alphabetical order.  If DEST_NODE
    was copied in this revision, COPY_SOURCE should indicate where it
    was copied from; otherwise, COPY_SOURCE should be None."""

    cvs_paths = src_entries.keys()
    cvs_paths.sort()
    for cvs_path in cvs_paths:
      if isinstance(cvs_path, CVSDirectory):
        # Path is a CVSDirectory:
        try:
          dest_subnode = dest_node[cvs_path]
        except KeyError:
          # Path doesn't exist yet; it has to be created:
          dest_node = self._fill_directory(
              symbol, None, src_entries[cvs_path], None
              ).parent_mirror_dir
        else:
          # Path already exists, but might have to be cleaned up:
          dest_node = self._fill_directory(
              symbol, dest_subnode, src_entries[cvs_path], copy_source
              ).parent_mirror_dir
      else:
        # Path is a CVSFile:
        self._fill_file(
            symbol, cvs_path in dest_node, src_entries[cvs_path], copy_source
            )
        # Reread dest_node since the call to _fill_file() might have
        # made it writable:
        dest_node = self._mirror.get_current_path(
            dest_node.cvs_path, dest_node.lod
            )

    return dest_node

  def _fill_file(self, symbol, dest_existed, fill_source, parent_source):
    """Fill the tag or branch SYMBOL at the path indicated by FILL_SOURCE.

    Use items from FILL_SOURCE.

    Fill SYMBOL at path FILL_SOURCE.cvs_path.  DEST_NODE is the node
    of this destination path, or None if the destination does not yet
    exist.  All directories above this path have already been filled
    as needed.  FILL_SOURCE is a FillSource instance describing the
    item that needs to be copied to the destination.

    PARENT_SOURCE is the source from which the parent directory was
    copied, or None if the parent directory was not copied during this
    commit.  We prefer to copy from PARENT_SOURCE, since it typically
    requires less touching-up.  If PARENT_SOURCE is None, then the
    parent directory was not copied in this commit, so no revision is
    preferable to any other."""

    copy_source = fill_source.compute_best_source(parent_source)

    # Figure out if we shall copy to this destination and delete any
    # destination path that is in the way.
    if not dest_existed:
      # The destination does not exist at all, so it definitely has to
      # be copied:
      self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )
    elif (parent_source is not None) and (
          copy_source.source_lod != parent_source.source_lod
          or copy_source.opening_revnum != parent_source.opening_revnum
          ):
      # The parent path was copied from a different source than we
      # need to use, so we have to delete the version that was copied
      # with the parent and then re-copy from the correct source:
      self.delete_path(fill_source.cvs_path, symbol)
      self.copy_path(
          fill_source.cvs_path, copy_source.source_lod,
          symbol, copy_source.opening_revnum
          )

  def _prune_extra_entries(
        self, dest_cvs_path, symbol, dest_node, src_entries
        ):
    """Delete any entries in DEST_NODE that are not in SRC_ENTRIES."""

    delete_list = [
        cvs_path
        for cvs_path in dest_node
        if cvs_path not in src_entries
        ]

    # Sort the delete list so that the output is in a consistent
    # order:
    delete_list.sort()
    for cvs_path in delete_list:
      logger.verbose("  Deleting %s" % (symbol.get_path(cvs_path.cvs_path),))
      del dest_node[cvs_path]
      self._invoke_delegates('delete_path', symbol, cvs_path)

  def add_delegate(self, delegate):
    """Adds DELEGATE to self._delegates.

    For every delegate you add, whenever a repository action method is
    performed, delegate's corresponding repository action method is
    called.  Multiple delegates will be called in the order that they
    are added.  See SVNRepositoryDelegate for more information."""

    self._delegates.append(delegate)

  def _invoke_delegates(self, method, *args):
    """Invoke a method on each delegate.

    Iterate through each of our delegates, in the order that they were
    added, and call the delegate's method named METHOD with the
    arguments in ARGS."""

    for delegate in self._delegates:
      getattr(delegate, method)(*args)

  def process_initial_project_commit(self, svn_commit):
    self.start_commit(svn_commit.revnum, self._get_revprops(svn_commit))

    for project in svn_commit.projects:
      self.initialize_project(project)

    self.end_commit()

  def process_primary_commit(self, svn_commit):
    self.start_commit(svn_commit.revnum, self._get_revprops(svn_commit))

    # This actually commits CVSRevisions
    if len(svn_commit.cvs_revs) > 1:
      plural = "s"
    else:
      plural = ""
    logger.verbose("Committing %d CVSRevision%s"
                  % (len(svn_commit.cvs_revs), plural))
    for cvs_rev in svn_commit.cvs_revs:
      if isinstance(cvs_rev, CVSRevisionNoop):
        pass

      elif isinstance(cvs_rev, CVSRevisionDelete):
        self.delete_path(cvs_rev.cvs_file, cvs_rev.lod, Ctx().prune)

      elif isinstance(cvs_rev, CVSRevisionAdd):
        self.add_path(cvs_rev)

      elif isinstance(cvs_rev, CVSRevisionChange):
        self.change_path(cvs_rev)

    self.end_commit()

  def process_post_commit(self, svn_commit):
    self.start_commit(svn_commit.revnum, self._get_revprops(svn_commit))

    logger.verbose(
        'Synchronizing default branch motivated by %d'
        % (svn_commit.motivating_revnum,)
        )

    for cvs_rev in svn_commit.cvs_revs:
      trunk = cvs_rev.cvs_file.project.get_trunk()
      if isinstance(cvs_rev, CVSRevisionAdd):
        # Copy from branch to trunk:
        self.copy_path(
            cvs_rev.cvs_file, cvs_rev.lod, trunk,
            svn_commit.motivating_revnum, True
            )
      elif isinstance(cvs_rev, CVSRevisionChange):
        # Delete old version of the path on trunk...
        self.delete_path(cvs_rev.cvs_file, trunk)
        # ...and copy the new version over from branch:
        self.copy_path(
            cvs_rev.cvs_file, cvs_rev.lod, trunk,
            svn_commit.motivating_revnum, True
            )
      elif isinstance(cvs_rev, CVSRevisionDelete):
        # Delete trunk path:
        self.delete_path(cvs_rev.cvs_file, trunk)
      elif isinstance(cvs_rev, CVSRevisionNoop):
        # Do nothing
        pass
      else:
        raise InternalError('Unexpected CVSRevision type: %s' % (cvs_rev,))

    self.end_commit()

  def process_branch_commit(self, svn_commit):
    self.start_commit(svn_commit.revnum, self._get_revprops(svn_commit))
    logger.verbose('Filling branch:', svn_commit.symbol.name)

    # Get the set of sources for the symbolic name:
    source_set = get_source_set(
        svn_commit.symbol,
        self._symbolings_reader.get_range_map(svn_commit),
        )

    self.fill_symbol(svn_commit, source_set)

    self.end_commit()

  def process_tag_commit(self, svn_commit):
    self.start_commit(svn_commit.revnum, self._get_revprops(svn_commit))
    logger.verbose('Filling tag:', svn_commit.symbol.name)

    # Get the set of sources for the symbolic name:
    source_set = get_source_set(
        svn_commit.symbol,
        self._symbolings_reader.get_range_map(svn_commit),
        )

    self.fill_symbol(svn_commit, source_set)

    self.end_commit()

  def cleanup(self):
    self._invoke_delegates('finish')
    logger.verbose("Finished creating Subversion repository.")
    logger.quiet("Done.")
    self._mirror.close()
    self._mirror = None
    Ctx().revision_reader.finish()
    self._symbolings_reader.close()
    del self._symbolings_reader


class DumpfileOutputOption(SVNOutputOption):
  """Output the result of the conversion into a dumpfile."""

  def __init__(self, dumpfile_path, author_transforms=None):
    SVNOutputOption.__init__(self, author_transforms)
    self.dumpfile_path = dumpfile_path

  def check(self):
    pass

  def setup(self, svn_rev_count):
    logger.quiet("Starting Subversion Dumpfile.")
    SVNOutputOption.setup(self, svn_rev_count)
    if not Ctx().dry_run:
      self.add_delegate(
          DumpstreamDelegate(
              Ctx().revision_reader, open(self.dumpfile_path, 'wb')
              )
          )


class RepositoryOutputOption(SVNOutputOption):
  """Output the result of the conversion into an SVN repository."""

  def __init__(self, target, author_transforms=None):
    SVNOutputOption.__init__(self, author_transforms)
    self.target = target

  def check(self):
    if not Ctx().dry_run:
      # Verify that svnadmin can be executed.  The 'help' subcommand
      # should be harmless.
      try:
        check_command_runs([Ctx().svnadmin_executable, 'help'], 'svnadmin')
      except CommandFailedException, e:
        raise FatalError(
            '%s\n'
            'svnadmin could not be executed.  Please ensure that it is\n'
            'installed and/or use the --svnadmin option.' % (e,))

  def setup(self, svn_rev_count):
    logger.quiet("Starting Subversion Repository.")
    SVNOutputOption.setup(self, svn_rev_count)
    if not Ctx().dry_run:
      self.add_delegate(
          DumpstreamDelegate(Ctx().revision_reader, LoaderPipe(self.target))
          )


class NewRepositoryOutputOption(RepositoryOutputOption):
  """Output the result of the conversion into a new SVN repository."""

  def __init__(
        self, target,
        fs_type=None, bdb_txn_nosync=None,
        author_transforms=None, create_options=[],
        ):
    RepositoryOutputOption.__init__(self, target, author_transforms)
    self.bdb_txn_nosync = bdb_txn_nosync

    # Determine the options to be passed to "svnadmin create":
    if not fs_type:
      # User didn't say what kind repository (bdb, fsfs, etc).  We
      # still pass --bdb-txn-nosync.  It's a no-op if the default
      # repository type doesn't support it, but we definitely want it
      # if BDB is the default.
      self.create_options = ['--bdb-txn-nosync']
    elif fs_type == 'bdb':
      # User explicitly specified bdb.
      #
      # Since this is a BDB repository, pass --bdb-txn-nosync, because
      # it gives us a 4-5x speed boost (if cvs2svn is creating the
      # repository, cvs2svn should be the only program accessing the
      # svn repository until cvs2svn is done).  But we'll turn no-sync
      # off in self.finish(), unless instructed otherwise.
      self.create_options = ['--fs-type=bdb', '--bdb-txn-nosync']
    else:
      # User specified something other than bdb.
      self.create_options = ['--fs-type=%s' % fs_type]

    # Now append the user's explicitly-set create options:
    self.create_options += create_options

  def check(self):
    RepositoryOutputOption.check(self)
    if not Ctx().dry_run and os.path.exists(self.target):
      raise FatalError("the svn-repos-path '%s' exists.\n"
                       "Remove it, or pass '--existing-svnrepos'."
                       % self.target)

  def setup(self, svn_rev_count):
    logger.normal("Creating new repository '%s'" % (self.target))
    if Ctx().dry_run:
      # Do not actually create repository:
      pass
    else:
      call_command([
          Ctx().svnadmin_executable, 'create',
          ] + self.create_options + [
          self.target
          ])

    RepositoryOutputOption.setup(self, svn_rev_count)

  def cleanup(self):
    RepositoryOutputOption.cleanup(self)

    # If this is a BDB repository, and we created the repository, and
    # --bdb-no-sync wasn't passed, then comment out the DB_TXN_NOSYNC
    # line in the DB_CONFIG file, because txn syncing should be on by
    # default in BDB repositories.
    #
    # We determine if this is a BDB repository by looking for the
    # DB_CONFIG file, which doesn't exist in FSFS, rather than by
    # checking self.fs_type.  That way this code will Do The Right
    # Thing in all circumstances.
    db_config = os.path.join(self.target, "db/DB_CONFIG")
    if Ctx().dry_run:
      # Do not change repository:
      pass
    elif not self.bdb_txn_nosync and os.path.exists(db_config):
      no_sync = 'set_flags DB_TXN_NOSYNC\n'

      f = open(db_config, 'r')
      contents = f.readlines()
      f.close()

      index = contents.index(no_sync)
      contents[index] = '# ' + no_sync

      f = open(db_config, 'w')
      f.writelines(contents)
      f.close()


class ExistingRepositoryOutputOption(RepositoryOutputOption):
  """Output the result of the conversion into an existing SVN repository."""

  def __init__(self, target, author_transforms=None):
    RepositoryOutputOption.__init__(self, target, author_transforms)

  def check(self):
    RepositoryOutputOption.check(self)
    if not os.path.isdir(self.target):
      raise FatalError("the svn-repos-path '%s' is not an "
                       "existing directory." % self.target)


