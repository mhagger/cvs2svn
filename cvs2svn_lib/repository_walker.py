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

"""Walk through a CVS project, generating CVSPaths."""


import os
import stat

from cvs2svn_lib.common import path_join
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import IllegalSVNPathError
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.project import FileInAndOutOfAtticException
from cvs2svn_lib.cvs_path import CVSDirectory
from cvs2svn_lib.cvs_path import CVSFile


class _RepositoryWalker(object):
  def __init__(self, file_key_generator, error_handler):
    self.file_key_generator = file_key_generator
    self.error_handler = error_handler

  def _get_cvs_file(
        self, parent_directory, basename,
        file_in_attic=False, leave_in_attic=False,
        ):
    """Return a CVSFile describing the file with name BASENAME.

    PARENT_DIRECTORY is the CVSDirectory instance describing the
    directory that physically holds this file in the filesystem.
    BASENAME must be the base name of a *,v file within
    PARENT_DIRECTORY.

    FILE_IN_ATTIC is a boolean telling whether the specified file is
    in an Attic subdirectory.  If FILE_IN_ATTIC is True, then:

    - If LEAVE_IN_ATTIC is True, then leave the 'Attic' component in
      the filename.

    - Otherwise, raise FileInAndOutOfAtticException if a file with the
      same filename appears outside of Attic.

    The CVSFile is assigned a new unique id.  All of the CVSFile
    information is filled in except mode (which can only be determined
    by parsing the file).

    Raise FatalError if the resulting filename would not be legal in
    SVN."""

    filename = os.path.join(parent_directory.rcs_path, basename)
    try:
      Ctx().output_option.verify_filename_legal(basename[:-2])
    except IllegalSVNPathError, e:
      raise FatalError(
          'File %r would result in an illegal SVN filename: %s'
          % (filename, e,)
          )

    if file_in_attic and not leave_in_attic:
      in_attic = True
      logical_parent_directory = parent_directory.parent_directory

      # If this file also exists outside of the attic, it's a fatal
      # error:
      non_attic_filename = os.path.join(
          logical_parent_directory.rcs_path, basename,
          )
      if os.path.exists(non_attic_filename):
        raise FileInAndOutOfAtticException(non_attic_filename, filename)
    else:
      in_attic = False
      logical_parent_directory = parent_directory

    file_stat = os.stat(filename)

    # The size of the file in bytes:
    file_size = file_stat.st_size

    # Whether or not the executable bit is set:
    file_executable = bool(file_stat.st_mode & stat.S_IXUSR)

    # mode is not known, so we temporarily set it to None.
    return CVSFile(
        self.file_key_generator.gen_id(),
        parent_directory.project, logical_parent_directory, basename[:-2],
        in_attic, file_executable, file_size, None, None
        )

  def _get_attic_file(self, parent_directory, basename):
    """Return a CVSFile object for the Attic file at BASENAME.

    PARENT_DIRECTORY is the CVSDirectory that physically contains the
    file on the filesystem (i.e., the Attic directory).  It is not
    necessarily the parent_directory of the CVSFile that will be
    returned.

    Return CVSFile, whose parent directory is usually
    PARENT_DIRECTORY.parent_directory, but might be PARENT_DIRECTORY
    iff CVSFile will remain in the Attic directory."""

    try:
      return self._get_cvs_file(
          parent_directory, basename, file_in_attic=True,
          )
    except FileInAndOutOfAtticException, e:
      if Ctx().retain_conflicting_attic_files:
        logger.warn(
            "%s: %s;\n"
            "   storing the latter into 'Attic' subdirectory.\n"
            % (warning_prefix, e)
            )
      else:
        self.error_handler(str(e))

      # Either way, return a CVSFile object so that the rest of the
      # file processing can proceed:
      return self._get_cvs_file(
          parent_directory, basename, file_in_attic=True, leave_in_attic=True,
          )

  def _generate_attic_cvs_files(self, cvs_directory):
    """Generate CVSFiles for the files in Attic directory CVS_DIRECTORY.

    Also yield CVS_DIRECTORY if any files are being retained in the
    Attic.

    Silently ignore subdirectories named '.svn', but emit a warning if
    any other directories are found within the Attic directory."""

    retained_attic_files = []

    fnames = os.listdir(cvs_directory.rcs_path)
    fnames.sort()
    for fname in fnames:
      pathname = os.path.join(cvs_directory.rcs_path, fname)
      if os.path.isdir(pathname):
        if fname == '.svn':
          logger.debug(
              "Directory %s found within Attic; ignoring" % (pathname,)
              )
        else:
          logger.warn(
              "Directory %s found within Attic; ignoring" % (pathname,)
              )
      elif fname.endswith(',v'):
        cvs_file = self._get_attic_file(cvs_directory, fname)
        if cvs_file.parent_directory == cvs_directory:
          # This file will be retained in the Attic directory.
          retained_attic_files.append(cvs_file)
        else:
          # This is a normal Attic file, which is treated as if it
          # were located one directory up:
          yield cvs_file

    if retained_attic_files:
      # There was at least one file in the attic that will be retained
      # in the attic.  First include the Attic directory itself in the
      # output, then the retained attic files:
      yield cvs_directory
      for cvs_file in retained_attic_files:
        yield cvs_file

  def generate_cvs_paths(self, cvs_directory, exclude_paths):
    """Generate the CVSPaths under non-Attic directory CVS_DIRECTORY.

    Yield CVSDirectory and CVSFile instances as they are found.
    Process directories recursively, including Attic directories.
    Also look for conflicts between the filenames that will result
    from files, attic files, and subdirectories.

    Silently ignore subdirectories named '.svn', as these don't make
    much sense in a real conversion, but they are present in our test
    suite."""

    yield cvs_directory

    # Map {cvs_file.rcs_basename : cvs_file.rcs_path} for files
    # directly in cvs_directory:
    rcsfiles = {}

    attic_dir = None

    # Non-Attic subdirectories of cvs_directory (to be recursed into):
    dirs = []

    fnames = os.listdir(cvs_directory.rcs_path)
    fnames.sort()
    for fname in fnames:
      pathname = os.path.join(cvs_directory.rcs_path, fname)
      path_in_repository = path_join(cvs_directory.get_cvs_path(), fname)
      if path_in_repository in exclude_paths:
        logger.normal(
            "Excluding file from conversion: %s" % (path_in_repository,)
            )
        pass
      elif os.path.isdir(pathname):
        if fname == 'Attic':
          attic_dir = fname
        elif fname == '.svn':
          logger.debug("Directory %s ignored" % (pathname,))
        else:
          dirs.append(fname)
      elif fname.endswith(',v'):
        cvs_file = self._get_cvs_file(cvs_directory, fname)
        rcsfiles[cvs_file.rcs_basename] = cvs_file.rcs_path
        yield cvs_file
      else:
        # Silently ignore other files:
        pass

    # Map {cvs_file.rcs_basename : cvs_file.rcs_path} for files in an
    # Attic directory within cvs_directory:
    attic_rcsfiles = {}

    if attic_dir is not None:
      attic_directory = CVSDirectory(
          self.file_key_generator.gen_id(),
          cvs_directory.project, cvs_directory, 'Attic',
          )

      for cvs_path in self._generate_attic_cvs_files(attic_directory):
        if isinstance(cvs_path, CVSFile) \
               and cvs_path.parent_directory == cvs_directory:
          attic_rcsfiles[cvs_path.rcs_basename] = cvs_path.rcs_path

        yield cvs_path

      alldirs = dirs + [attic_dir]
    else:
      alldirs = dirs

    # Check for conflicts between directory names and the filenames
    # that will result from the rcs files (both in this directory and
    # in attic).  (We recurse into the subdirectories nevertheless, to
    # try to detect more problems.)
    for fname in alldirs:
      for rcsfile_list in [rcsfiles, attic_rcsfiles]:
        if fname in rcsfile_list:
          self.error_handler(
              'Directory name conflicts with filename.  Please remove or '
              'rename one\n'
              'of the following:\n'
              '    "%s"\n'
              '    "%s"' % (
                  os.path.join(cvs_directory.rcs_path, fname),
                  rcsfile_list[fname],
                  )
              )

    # Now recurse into the other subdirectories:
    for fname in dirs:
      dirname = os.path.join(cvs_directory.rcs_path, fname)

      # Verify that the directory name does not contain any illegal
      # characters:
      try:
        Ctx().output_option.verify_filename_legal(fname)
      except IllegalSVNPathError, e:
        raise FatalError(
            'Directory %r would result in an illegal SVN path name: %s'
            % (dirname, e,)
            )

      sub_directory = CVSDirectory(
          self.file_key_generator.gen_id(),
          cvs_directory.project, cvs_directory, fname,
          )

      for cvs_path in self.generate_cvs_paths(sub_directory, exclude_paths):
        yield cvs_path


def walk_repository(project, file_key_generator, error_handler):
  """Generate CVSDirectories and CVSFiles within PROJECT.

  Use FILE_KEY_GENERATOR to generate the IDs used for files.  If there
  is a fatal error, register it by calling ERROR_HANDLER with a string
  argument describing the problem.  (The error will be logged but
  processing will continue through the end of the pass.)  Also:

  * Set PROJECT.root_cvs_directory_id.

  * Handle files in the Attic by generating CVSFile instances with the
    _in_attic member set.

  * Check for naming conflicts that will result from files in and out
    of the Attic.  If Ctx().retain_conflicting_attic_files is set, fix
    the conflicts by leaving the Attic file in the attic.  Otherwise,
    register a fatal error.

  * Check for naming conflicts between files (in or out of the Attic)
    and directories.

  * Check for filenames that contain characters not allowed by
    Subversion.

  """

  root_cvs_directory = CVSDirectory(
      file_key_generator.gen_id(), project, None, ''
      )
  project.root_cvs_directory_id = root_cvs_directory.id
  repository_walker = _RepositoryWalker(file_key_generator, error_handler)
  for cvs_path in repository_walker.generate_cvs_paths(
        root_cvs_directory, project.exclude_paths
        ):
    yield cvs_path


