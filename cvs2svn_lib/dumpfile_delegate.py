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


import os
import md5

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import OP_ADD
from cvs2svn_lib.common import OP_CHANGE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.svn_repository_mirror import SVNRepositoryMirrorDelegate


class DumpfileDelegate(SVNRepositoryMirrorDelegate):
  """Create a Subversion dumpfile."""

  def __init__(self, dumpfile_path=None):
    """Return a new DumpfileDelegate instance, attached to a dumpfile
    DUMPFILE_PATH (Ctx().dumpfile, if None), using Ctx().encoding."""

    if dumpfile_path:
      self.dumpfile_path = dumpfile_path
    else:
      self.dumpfile_path = Ctx().dumpfile

    self.dumpfile = open(self.dumpfile_path, 'wb')
    self._write_dumpfile_header(self.dumpfile)

  def _write_dumpfile_header(self, dumpfile):
    # Initialize the dumpfile with the standard headers.
    #
    # Since the CVS repository doesn't have a UUID, and the Subversion
    # repository will be created with one anyway, we don't specify a
    # UUID in the dumpflie
    dumpfile.write('SVN-fs-dump-format-version: 2\n\n')

  def _utf8_path(self, path):
    """Return a copy of PATH encoded in UTF-8."""

    pieces = path.split('/')
    # Convert each path component separately (as they may each use
    # different encodings).
    for i in range(len(pieces)):
      try:
        # Log messages can be converted with the 'replace' strategy,
        # but we can't afford any lossiness here.
        pieces[i] = Ctx().to_utf8(pieces[i], 'strict')
      except UnicodeError:
        raise FatalError(
            "Unable to convert a path '%s' to internal encoding.\n"
            "Consider rerunning with one or more '--encoding' parameters."
            % (path,))
    return '/'.join(pieces)

  def _string_for_prop(self, name, value):
    """Return a property in the form needed for the dumpfile."""

    return 'K %d\n%s\nV %d\n%s\n' % (len(name), name, len(value), value)

  def start_commit(self, svn_commit):
    """Emit the start of SVN_COMMIT (an SVNCommit)."""

    self.revision = svn_commit.revnum

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
    props = svn_commit.get_revprops()
    prop_names = props.keys()
    prop_names.sort()
    prop_strings = []
    for propname in prop_names:
      if props[propname] is not None:
        prop_strings.append(self._string_for_prop(propname, props[propname]))

    all_prop_strings = ''.join(prop_strings) + 'PROPS-END\n'
    total_len = len(all_prop_strings)

    # Print the revision header and props
    self.dumpfile.write('Revision-number: %d\n'
                        'Prop-content-length: %d\n'
                        'Content-length: %d\n'
                        '\n'
                        % (self.revision, total_len, total_len))

    self.dumpfile.write(all_prop_strings)
    self.dumpfile.write('\n')

  def mkdir(self, path):
    """Emit the creation of directory PATH."""

    self.dumpfile.write("Node-path: %s\n"
                        "Node-kind: dir\n"
                        "Node-action: add\n"
                        "\n"
                        "\n" % self._utf8_path(path))

  def _add_or_change_path(self, s_item, op):
    """Emit the addition or change corresponding to S_ITEM.
    OP is either the constant OP_ADD or OP_CHANGE."""

    # Validation stuffs
    if op == OP_ADD:
      action = 'add'
    elif op == OP_CHANGE:
      action = 'change'
    else:
      raise FatalError("_add_or_change_path() called with bad op ('%s')"
                       % (op,))

    # Convenience variables
    c_rev = s_item.c_rev

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
    # For files, the only properties we ever set are set in the first
    # revision; all other revisions (including on branches) inherit
    # from that.  After the first revision, we never change file
    # properties, therefore, there is no need to remember the full set
    # of properties on a given file once we've set it.
    #
    # For directories, the only property we set is "svn:ignore", and
    # while we may change it after the first revision, we always do so
    # based on the contents of a ".cvsignore" file -- in other words,
    # CVS is doing the remembering for us, so we still don't have to
    # preserve the previous value of the property ourselves.

    # Calculate the (sorted-by-name) property string and length, if any.
    if s_item.svn_props_changed:
      svn_props = s_item.svn_props
      prop_contents = ''
      prop_names = svn_props.keys()
      prop_names.sort()
      for pname in prop_names:
        pvalue = svn_props[pname]
        if pvalue is not None:
          prop_contents += self._string_for_prop(pname, pvalue)
      prop_contents += 'PROPS-END\n'
      props_header = 'Prop-content-length: %d\n' % len(prop_contents)
    else:
      prop_contents = ''
      props_header = ''

    # treat .cvsignore as a directory property
    dir_path, basename = os.path.split(c_rev.svn_path)
    if basename == ".cvsignore":
      ignore_vals = generate_ignores(c_rev)
      ignore_contents = '\n'.join(ignore_vals)
      ignore_contents = ('K 10\nsvn:ignore\nV %d\n%s\n' % \
                         (len(ignore_contents), ignore_contents))
      ignore_contents += 'PROPS-END\n'
      ignore_len = len(ignore_contents)

      # write headers, then props
      self.dumpfile.write('Node-path: %s\n'
                          'Node-kind: dir\n'
                          'Node-action: change\n'
                          'Prop-content-length: %d\n'
                          'Content-length: %d\n'
                          '\n'
                          '%s'
                          % (self._utf8_path(dir_path), ignore_len,
                             ignore_len, ignore_contents))

    # If the file has keywords, we must prevent CVS/RCS from expanding
    # the keywords because they must be unexpanded in the repository,
    # or Subversion will get confused.
    pipe_cmd, pipe = Ctx().project.cvs_repository.get_co_pipe(
        c_rev, suppress_keyword_substitution=s_item.has_keywords)

    self.dumpfile.write('Node-path: %s\n'
                        'Node-kind: file\n'
                        'Node-action: %s\n'
                        '%s'  # no property header if no props
                        'Text-content-length: '
                        % (self._utf8_path(c_rev.svn_path),
                           action, props_header))

    pos = self.dumpfile.tell()

    self.dumpfile.write('0000000000000000\n'
                        'Text-content-md5: 00000000000000000000000000000000\n'
                        'Content-length: 0000000000000000\n'
                        '\n')

    if prop_contents:
      self.dumpfile.write(prop_contents)

    # Insert a filter to convert all EOLs to LFs if neccessary
    if s_item.needs_eol_filter:
      data_reader = LF_EOL_Filter(pipe.stdout)
    else:
      data_reader = pipe.stdout

    # Insert the rev contents, calculating length and checksum as we go.
    checksum = md5.new()
    length = 0
    while True:
      buf = data_reader.read(config.PIPE_READ_SIZE)
      if buf == '':
        break
      checksum.update(buf)
      length += len(buf)
      self.dumpfile.write(buf)

    pipe.stdout.close()
    error_output = pipe.stderr.read()
    exit_status = pipe.wait()
    if exit_status:
      raise FatalError("The command '%s' failed with exit status: %s\n"
                       "and the following output:\n"
                       "%s" % (pipe_cmd, exit_status, error_output))

    # Go back to patch up the length and checksum headers:
    self.dumpfile.seek(pos, 0)
    # We left 16 zeros for the text length; replace them with the real
    # length, padded on the left with spaces:
    self.dumpfile.write('%16d' % length)
    # 16... + 1 newline + len('Text-content-md5: ') == 35
    self.dumpfile.seek(pos + 35, 0)
    self.dumpfile.write(checksum.hexdigest())
    # 35... + 32 bytes of checksum + 1 newline + len('Content-length: ') == 84
    self.dumpfile.seek(pos + 84, 0)
    # The content length is the length of property data, text data,
    # and any metadata around/inside around them.
    self.dumpfile.write('%16d' % (length + len(prop_contents)))
    # Jump back to the end of the stream
    self.dumpfile.seek(0, 2)

    # This record is done (write two newlines -- one to terminate
    # contents that weren't themselves newline-termination, one to
    # provide a blank line for readability.
    self.dumpfile.write('\n\n')

  def add_path(self, s_item):
    """Emit the addition corresponding to S_ITEM, an SVNCommitItem."""

    self._add_or_change_path(s_item, OP_ADD)

  def change_path(self, s_item):
    """Emit the change corresponding to S_ITEM, an SVNCommitItem."""

    self._add_or_change_path(s_item, OP_CHANGE)

  def delete_path(self, path):
    """Emit the deletion of PATH."""

    self.dumpfile.write('Node-path: %s\n'
                        'Node-action: delete\n'
                        '\n' % self._utf8_path(path))

  def copy_path(self, src_path, dest_path, src_revnum):
    """Emit the copying of SRC_PATH at SRC_REV to DEST_PATH."""

    # We don't need to include "Node-kind:" for copies; the loader
    # ignores it anyway and just uses the source kind instead.
    self.dumpfile.write('Node-path: %s\n'
                        'Node-action: add\n'
                        'Node-copyfrom-rev: %d\n'
                        'Node-copyfrom-path: /%s\n'
                        '\n'
                        % (self._utf8_path(dest_path),
                           src_revnum,
                           self._utf8_path(src_path)))

  def finish(self):
    """Perform any cleanup necessary after all revisions have been
    committed."""

    self.dumpfile.close()


def generate_ignores(c_rev):
  # Read in props
  pipe_cmd, pipe = Ctx().project.cvs_repository.get_co_pipe(c_rev)
  buf = pipe.stdout.read(config.PIPE_READ_SIZE)
  raw_ignore_val = ""
  while buf:
    raw_ignore_val += buf
    buf = pipe.stdout.read(config.PIPE_READ_SIZE)
  pipe.stdout.close()
  error_output = pipe.stderr.read()
  exit_status = pipe.wait()
  if exit_status:
    raise FatalError("The command '%s' failed with exit status: %s\n"
                     "and the following output:\n"
                     "%s" % (pipe_cmd, exit_status, error_output))

  # Tweak props: First, convert any spaces to newlines...
  raw_ignore_val = '\n'.join(raw_ignore_val.split())
  raw_ignores = raw_ignore_val.split('\n')
  ignore_vals = [ ]
  for ignore in raw_ignores:
    # Reset the list if we encounter a '!'
    # See http://cvsbook.red-bean.com/cvsbook.html#cvsignore
    if ignore == '!':
      ignore_vals = [ ]
      continue
    # Skip empty lines
    if len(ignore) == 0:
      continue
    ignore_vals.append(ignore)
  return ignore_vals


class LF_EOL_Filter:
  """Filter a stream and convert all end-of-line markers (CRLF, CR or LF)
  into LFs only."""

  def __init__(self, stream):
    self.stream = stream
    self.carry_cr = False
    self.eof = False

  def read(self, size):
    while True:
      buf = self.stream.read(size)
      self.eof = len(buf) == 0
      if self.carry_cr:
        buf = '\r' + buf
        self.carry_cr = False
      if not self.eof and buf[-1] == '\r':
        self.carry_cr = True
        buf = buf[:-1]
      buf = buf.replace('\r\n', '\n')
      buf = buf.replace('\r', '\n')
      if len(buf) > 0 or self.eof:
        return buf


