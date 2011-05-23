# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2010 CollabNet.  All rights reserved.
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

"""This module contains code to output to Subversion dumpfile format."""


import subprocess

try:
  from hashlib import md5
except ImportError:
  from md5 import new as md5

from cvs2svn_lib.common import CommandError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import path_split
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.cvs_path import CVSDirectory
from cvs2svn_lib.cvs_path import CVSFile
from cvs2svn_lib.svn_repository_delegate import SVNRepositoryDelegate


# Things that can happen to a file.
OP_ADD    = 'add'
OP_CHANGE = 'change'


class DumpstreamDelegate(SVNRepositoryDelegate):
  """Write output in Subversion dumpfile format."""

  def __init__(self, revision_reader, dumpfile):
    """Return a new DumpstreamDelegate instance.

    DUMPFILE should be a file-like object opened in binary mode, to
    which the dump stream will be written.  The only methods called on
    the object are write() and close()."""

    self._revision_reader = revision_reader
    self._dumpfile = dumpfile
    self._write_dumpfile_header()

    # A set of the basic project infrastructure project directories
    # that have been created so far, as SVN paths.  (The root
    # directory is considered to be present at initialization.)  This
    # includes all of the LOD paths, and all of their parent
    # directories etc.
    self._basic_directories = set([''])

  def _write_dumpfile_header(self):
    """Initialize the dumpfile with the standard headers.

    Since the CVS repository doesn't have a UUID, and the Subversion
    repository will be created with one anyway, we don't specify a
    UUID in the dumpfile."""

    self._dumpfile.write('SVN-fs-dump-format-version: 2\n\n')

  def _utf8_path(self, path):
    """Return a copy of PATH encoded in UTF-8."""

    # Convert each path component separately (as they may each use
    # different encodings).
    try:
      return '/'.join([
          Ctx().cvs_filename_decoder(piece).encode('utf8')
          for piece in path.split('/')
          ])
    except UnicodeError:
      raise FatalError(
          "Unable to convert a path '%s' to internal encoding.\n"
          "Consider rerunning with one or more '--encoding' parameters or\n"
          "with '--fallback-encoding'."
          % (path,))

  @staticmethod
  def _string_for_props(properties):
    """Return PROPERTIES in the form needed for the dumpfile."""

    prop_strings = []
    for (k, v) in sorted(properties.iteritems()):
      if k.startswith('_'):
        # Such properties are for internal use only.
        pass
      elif v is None:
        # None indicates that the property should be left unset.
        pass
      else:
        prop_strings.append('K %d\n%s\nV %d\n%s\n' % (len(k), k, len(v), v))

    prop_strings.append('PROPS-END\n')

    return ''.join(prop_strings)

  def start_commit(self, revnum, revprops):
    """Emit the start of SVN_COMMIT (an SVNCommit)."""

    # The start of a new commit typically looks like this:
    #
    #   Revision-number: 1
    #   Prop-content-length: 129
    #   Content-length: 129
    #
    #   K 7
    #   svn:log
    #   V 27
    #   Log message for revision 1.
    #   K 10
    #   svn:author
    #   V 7
    #   jrandom
    #   K 8
    #   svn:date
    #   V 27
    #   2003-04-22T22:57:58.132837Z
    #   PROPS-END
    #
    # Notice that the length headers count everything -- not just the
    # length of the data but also the lengths of the lengths, including
    # the 'K ' or 'V ' prefixes.
    #
    # The reason there are both Prop-content-length and Content-length
    # is that the former includes just props, while the latter includes
    # everything.  That's the generic header form for any entity in a
    # dumpfile.  But since revisions only have props, the two lengths
    # are always the same for revisions.

    # Calculate the output needed for the property definitions.
    all_prop_strings = self._string_for_props(revprops)
    total_len = len(all_prop_strings)

    # Print the revision header and revprops
    self._dumpfile.write(
        'Revision-number: %d\n'
        'Prop-content-length: %d\n'
        'Content-length: %d\n'
        '\n'
        '%s'
        '\n'
        % (revnum, total_len, total_len, all_prop_strings)
        )

  def end_commit(self):
    pass

  def _make_any_dir(self, path):
    """Emit the creation of directory PATH."""

    self._dumpfile.write(
        "Node-path: %s\n"
        "Node-kind: dir\n"
        "Node-action: add\n"
        "\n"
        "\n"
        % self._utf8_path(path)
        )

  def _register_basic_directory(self, path, create):
    """Register the creation of PATH if it is not already there.

    Create any parent directories that do not already exist.  If
    CREATE is set, also create PATH if it doesn't already exist.  This
    method should only be used for the LOD paths and the directories
    containing them, not for directories within an LOD path."""

    if path not in self._basic_directories:
      # Make sure that the parent directory is present:
      self._register_basic_directory(path_split(path)[0], True)
      if create:
        self._make_any_dir(path)
      self._basic_directories.add(path)

  def initialize_project(self, project):
    """Create any initial directories for the project.

    The trunk, tags, and branches directories directories are created
    the first time the project is seen.  Be sure not to create parent
    directories that already exist (e.g., because two directories
    share part of their paths either within or across projects)."""

    for path in project.get_initial_directories():
      self._register_basic_directory(path, True)

  def initialize_lod(self, lod):
    lod_path = lod.get_path()
    if lod_path:
      self._register_basic_directory(lod_path, True)

  def mkdir(self, lod, cvs_directory):
    self._make_any_dir(lod.get_path(cvs_directory.cvs_path))

  def _add_or_change_path(self, cvs_rev, op):
    """Emit the addition or change corresponding to CVS_REV.

    OP is either the constant OP_ADD or OP_CHANGE."""

    assert op in [OP_ADD, OP_CHANGE]

    # The property handling here takes advantage of an undocumented
    # but IMHO consistent feature of the Subversion dumpfile-loading
    # code.  When a node's properties aren't mentioned (that is, the
    # "Prop-content-length:" header is absent, no properties are
    # listed at all, and there is no "PROPS-END\n" line) then no
    # change is made to the node's properties.
    #
    # This is consistent with the way dumpfiles behave w.r.t. text
    # content changes, so I'm comfortable relying on it.  If you
    # commit a change to *just* the properties of some node that
    # already has text contents from a previous revision, then in the
    # dumpfile output for the prop change, no "Text-content-length:"
    # nor "Text-content-md5:" header will be present, and the text of
    # the file will not be given.  But this does not cause the file's
    # text to be erased!  It simply remains unchanged.
    #
    # This works out great for cvs2svn, due to lucky coincidences:
    #
    # For files, we set most properties in the first revision and
    # never change them.  (The only exception is the 'cvs2svn:cvs-rev'
    # property.)  If 'cvs2svn:cvs-rev' is not being used, then there
    # is no need to remember the full set of properties on a given
    # file once we've set it.
    #
    # For directories, the only property we set is "svn:ignore", and
    # while we may change it after the first revision, we always do so
    # based on the contents of a ".cvsignore" file -- in other words,
    # CVS is doing the remembering for us, so we still don't have to
    # preserve the previous value of the property ourselves.

    # Calculate the (sorted-by-name) property string and length, if any.
    svn_props = cvs_rev.get_properties()
    if cvs_rev.properties_changed:
      prop_contents = self._string_for_props(svn_props)
      props_header = 'Prop-content-length: %d\n' % len(prop_contents)
    else:
      prop_contents = ''
      props_header = ''

    data = self._revision_reader.get_content(cvs_rev)

    # treat .cvsignore as a directory property
    dir_path, basename = path_split(cvs_rev.get_svn_path())
    if basename == '.cvsignore':
      ignore_contents = self._string_for_props({
          'svn:ignore' : ''.join((s + '\n') for s in generate_ignores(data))
          })
      ignore_len = len(ignore_contents)

      # write headers, then props
      self._dumpfile.write(
          'Node-path: %s\n'
          'Node-kind: dir\n'
          'Node-action: change\n'
          'Prop-content-length: %d\n'
          'Content-length: %d\n'
          '\n'
          '%s'
          % (self._utf8_path(dir_path),
             ignore_len, ignore_len, ignore_contents)
          )
      if not Ctx().keep_cvsignore:
        return

    checksum = md5()
    checksum.update(data)

    # The content length is the length of property data, text data,
    # and any metadata around/inside around them:
    self._dumpfile.write(
        'Node-path: %s\n'
        'Node-kind: file\n'
        'Node-action: %s\n'
        '%s'  # no property header if no props
        'Text-content-length: %d\n'
        'Text-content-md5: %s\n'
        'Content-length: %d\n'
        '\n' % (
            self._utf8_path(cvs_rev.get_svn_path()), op, props_header,
            len(data), checksum.hexdigest(), len(data) + len(prop_contents),
            )
        )

    if prop_contents:
      self._dumpfile.write(prop_contents)

    self._dumpfile.write(data)

    # This record is done (write two newlines -- one to terminate
    # contents that weren't themselves newline-termination, one to
    # provide a blank line for readability.
    self._dumpfile.write('\n\n')

  def add_path(self, cvs_rev):
    """Emit the addition corresponding to CVS_REV, a CVSRevisionAdd."""

    self._add_or_change_path(cvs_rev, OP_ADD)

  def change_path(self, cvs_rev):
    """Emit the change corresponding to CVS_REV, a CVSRevisionChange."""

    self._add_or_change_path(cvs_rev, OP_CHANGE)

  def delete_lod(self, lod):
    """Emit the deletion of LOD."""

    self._dumpfile.write(
        'Node-path: %s\n'
        'Node-action: delete\n'
        '\n'
        % (self._utf8_path(lod.get_path()),)
        )
    self._basic_directories.remove(lod.get_path())

  def delete_path(self, lod, cvs_path):
    dir_path, basename = path_split(lod.get_path(cvs_path.get_cvs_path()))
    if basename == '.cvsignore':
      # When a .cvsignore file is deleted, the directory's svn:ignore
      # property needs to be deleted.
      ignore_contents = 'PROPS-END\n'
      ignore_len = len(ignore_contents)

      # write headers, then props
      self._dumpfile.write(
          'Node-path: %s\n'
          'Node-kind: dir\n'
          'Node-action: change\n'
          'Prop-content-length: %d\n'
          'Content-length: %d\n'
          '\n'
          '%s'
          % (self._utf8_path(dir_path),
             ignore_len, ignore_len, ignore_contents)
          )
      if not Ctx().keep_cvsignore:
        return

    self._dumpfile.write(
        'Node-path: %s\n'
        'Node-action: delete\n'
        '\n'
        % (self._utf8_path(lod.get_path(cvs_path.cvs_path)),)
        )

  def copy_lod(self, src_lod, dest_lod, src_revnum):
    # Register the main LOD directory, and create parent directories
    # as needed:
    self._register_basic_directory(dest_lod.get_path(), False)

    self._dumpfile.write(
        'Node-path: %s\n'
        'Node-kind: dir\n'
        'Node-action: add\n'
        'Node-copyfrom-rev: %d\n'
        'Node-copyfrom-path: %s\n'
        '\n'
        % (self._utf8_path(dest_lod.get_path()),
           src_revnum, self._utf8_path(src_lod.get_path()))
        )

  def copy_path(self, cvs_path, src_lod, dest_lod, src_revnum):
    if isinstance(cvs_path, CVSFile):
      node_kind = 'file'
      if cvs_path.rcs_basename == '.cvsignore':
        # FIXME: Here we have to adjust the containing directory's
        # svn:ignore property to reflect the addition of the
        # .cvsignore file to the LOD!  This is awkward because we
        # don't have the contents of the .cvsignore file available.
        if not Ctx().keep_cvsignore:
          return
    elif isinstance(cvs_path, CVSDirectory):
      node_kind = 'dir'
    else:
      raise InternalError()

    self._dumpfile.write(
        'Node-path: %s\n'
        'Node-kind: %s\n'
        'Node-action: add\n'
        'Node-copyfrom-rev: %d\n'
        'Node-copyfrom-path: %s\n'
        '\n'
        % (
            self._utf8_path(dest_lod.get_path(cvs_path.cvs_path)),
            node_kind,
            src_revnum,
            self._utf8_path(src_lod.get_path(cvs_path.cvs_path))
            )
        )

  def finish(self):
    """Perform any cleanup necessary after all revisions have been
    committed."""

    self._dumpfile.close()


def generate_ignores(raw_ignore_val):
  ignore_vals = [ ]
  for ignore in raw_ignore_val.split():
    # Reset the list if we encounter a '!'
    # See http://cvsbook.red-bean.com/cvsbook.html#cvsignore
    if ignore == '!':
      ignore_vals = [ ]
    else:
      ignore_vals.append(ignore)
  return ignore_vals


class LoaderPipe(object):
  """A file-like object that writes to 'svnadmin load'.

  Some error checking and reporting are done when writing."""

  def __init__(self, target):
    self.loader_pipe = subprocess.Popen(
        [Ctx().svnadmin_executable, 'load', '-q', target],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        )
    self.loader_pipe.stdout.close()

  def write(self, s):
    try:
      self.loader_pipe.stdin.write(s)
    except IOError:
      raise FatalError(
          'svnadmin failed with the following output while '
          'loading the dumpfile:\n%s'
          % (self.loader_pipe.stderr.read(),)
          )

  def close(self):
    self.loader_pipe.stdin.close()
    error_output = self.loader_pipe.stderr.read()
    exit_status = self.loader_pipe.wait()
    del self.loader_pipe
    if exit_status:
      raise CommandError('svnadmin load', exit_status, error_output)


