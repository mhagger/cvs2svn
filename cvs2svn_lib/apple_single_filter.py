# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007-2008 CollabNet.  All rights reserved.
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

"""A stream filter for extracting the data fork from AppleSingle data.

Some Macintosh CVS clients store resource fork data along with the
contents of the file (called the data fork) by encoding both in an
'AppleSingle' data stream before storing them to CVS.  This file
contains a stream filter for extracting the data fork from such data
streams.  (Any other forks are discarded.)

See the following for some random information about this format and
how it is used by Macintosh CVS clients:

    http://users.phg-online.de/tk/netatalk/doc/Apple/v1/
    http://rfc.net/rfc1740.html
    http://ximbiot.com/cvs/cvshome/cyclic/cvs/dev-mac.html
    http://www.maccvs.org/faq.html#resfiles
    http://www.heilancoo.net/MacCVSClient/MacCVSClientDoc/storage-formats.html

"""


import struct
from cStringIO import StringIO


class AppleSingleFormatError(IOError):
  """The stream was not in correct AppleSingle format."""

  pass


class AppleSingleIncorrectMagicError(AppleSingleFormatError):
  """The file didn't start with the correct magic number."""

  def __init__(self, data_read, eof):
    AppleSingleFormatError.__init__(self)
    self.data_read = data_read
    self.eof = eof


class AppleSingleEOFError(AppleSingleFormatError):
  """EOF was reached where AppleSingle doesn't allow it."""

  pass


class AppleSingleFilter(object):
  """A stream that reads the data fork from an AppleSingle stream.

  If the constructor discovers that the file is not a legitimate
  AppleSingle stream, then it raises an AppleSingleFormatError.  In
  the special case that the magic number is incorrect, it raises
  AppleSingleIncorrectMagicError with data_read set to the data that
  have been read so far from the input stream.  (This allows the
  caller the option to fallback to treating the input stream as a
  normal binary data stream.)"""

  # The header is:
  #
  #     Magic number             4 bytes
  #     Version number           4 bytes
  #     File system or filler   16 bytes
  #     Number of entries        2 bytes
  magic_struct = '>i'
  magic_len = struct.calcsize(magic_struct)

  # The part of the header after the magic number:
  rest_of_header_struct = '>i16sH'
  rest_of_header_len = struct.calcsize(rest_of_header_struct)

  # Each entry is:
  #
  #     Entry ID                 4 bytes
  #     Offset                   4 bytes
  #     Length                   4 bytes
  entry_struct = '>iii'
  entry_len = struct.calcsize(entry_struct)

  apple_single_magic = 0x00051600
  apple_single_version_1 = 0x00010000
  apple_single_version_2 = 0x00020000
  apple_single_filler = '\0' * 16

  apple_single_data_fork_entry_id = 1

  def __init__(self, stream):
    self.stream = stream

    # Check for the AppleSingle magic number:
    s = self._read_exactly(self.magic_len)
    if len(s) < self.magic_len:
      raise AppleSingleIncorrectMagicError(s, True)

    (magic,) = struct.unpack(self.magic_struct, s)
    if magic != self.apple_single_magic:
      raise AppleSingleIncorrectMagicError(s, False)

    # Read the rest of the header:
    s = self._read_exactly(self.rest_of_header_len)
    if len(s) < self.rest_of_header_len:
      raise AppleSingleEOFError('AppleSingle header incomplete')

    (version, filler, num_entries) = \
        struct.unpack(self.rest_of_header_struct, s)

    if version == self.apple_single_version_1:
      self._prepare_apple_single_v1_file(num_entries)
    elif version == self.apple_single_version_2:
      if filler != self.apple_single_filler:
        raise AppleSingleFormatError('Incorrect filler')
      self._prepare_apple_single_v2_file(num_entries)
    else:
      raise AppleSingleFormatError('Unknown AppleSingle version')

  def _read_exactly(self, size):
    """Read and return exactly SIZE characters from the stream.

    This method is to deal with the fact that stream.read(size) is
    allowed to return less than size characters.  If EOF is reached
    before SIZE characters have been read, return the characters that
    have been read so far."""

    retval = []
    length_remaining = size
    while length_remaining > 0:
      s = self.stream.read(length_remaining)
      if not s:
        break
      retval.append(s)
      length_remaining -= len(s)

    return ''.join(retval)

  def _prepare_apple_single_file(self, num_entries):
    entries = self._read_exactly(num_entries * self.entry_len)
    if len(entries) < num_entries * self.entry_len:
      raise AppleSingleEOFError('Incomplete entries list')

    for i in range(num_entries):
      entry = entries[i * self.entry_len : (i + 1) * self.entry_len]
      (entry_id, offset, length) = struct.unpack(self.entry_struct, entry)
      if entry_id == self.apple_single_data_fork_entry_id:
        break
    else:
      raise AppleSingleFormatError('No data fork found')

    # The data fork is located at [offset : offset + length].  Read up
    # to the start of the data:
    n = offset - self.magic_len - self.rest_of_header_len - len(entries)
    if n < 0:
      raise AppleSingleFormatError('Invalid offset to AppleSingle data fork')

    max_chunk_size = 65536
    while n > 0:
      s = self.stream.read(min(n, max_chunk_size))
      if not s:
        raise AppleSingleEOFError(
            'Offset to AppleSingle data fork past end of file'
            )
      n -= len(s)

    self.length_remaining = length

  def _prepare_apple_single_v1_file(self, num_entries):
    self._prepare_apple_single_file(num_entries)

  def _prepare_apple_single_v2_file(self, num_entries):
    self._prepare_apple_single_file(num_entries)

  def read(self, size=-1):
    if size == 0 or self.length_remaining == 0:
      return ''
    elif size < 0:
      s = self._read_exactly(self.length_remaining)
      if len(s) < self.length_remaining:
        raise AppleSingleEOFError('AppleSingle data fork truncated')
      self.length_remaining = 0
      return s
    else:
      # The length of this read is allowed to be shorter than the
      # requested size:
      s = self.stream.read(min(size, self.length_remaining))
      if not s:
        raise AppleSingleEOFError()
      self.length_remaining -= len(s)
      return s

  def close(self):
    self.stream.close()
    self.stream = None


class CompoundStream(object):
  """A stream that reads from a series of streams, one after the other."""

  def __init__(self, streams, stream_index=0):
    self.streams = list(streams)
    self.stream_index = stream_index

  def read(self, size=-1):
    if size < 0:
      retval = []
      while self.stream_index < len(self.streams):
        retval.append(self.streams[self.stream_index].read())
        self.stream_index += 1
      return ''.join(retval)
    else:
      while self.stream_index < len(self.streams):
        s = self.streams[self.stream_index].read(size)
        if s:
          # This may not be the full size requested, but that is OK:
          return s
        else:
          # That stream was empty; proceed to the next stream:
          self.stream_index += 1

      # No streams are left:
      return ''

  def close(self):
    for stream in self.streams:
      stream.close()
    self.streams = None


def get_maybe_apple_single_stream(stream):
  """Treat STREAM as AppleSingle if possible; otherwise treat it literally.

  If STREAM is in AppleSingle format, then return a stream that will
  output the data fork of the original stream.  Otherwise, return a
  stream that will output the original file contents literally.

  Be careful not to read from STREAM after it has already hit EOF."""

  try:
    return AppleSingleFilter(stream)
  except AppleSingleIncorrectMagicError, e:
    # This is OK; the file is not AppleSingle, so we read it normally:
    string_io = StringIO(e.data_read)
    if e.eof:
      # The original stream already reached EOF, so the part already
      # read contains the complete file contents.  Nevertheless return
      # a CompoundStream to make sure that the stream's close() method
      # is called:
      return CompoundStream([stream, string_io], stream_index=1)
    else:
      # The stream needs to output the part already read followed by
      # whatever hasn't been read of the original stream:
      return CompoundStream([string_io, stream])


def get_maybe_apple_single(data):
  """Treat DATA as AppleSingle if possible; otherwise treat it literally.

  If DATA is in AppleSingle format, then return its data fork.
  Otherwise, return the original DATA."""

  return get_maybe_apple_single_stream(StringIO(data)).read()


if __name__ == '__main__':
  # For fun and testing, allow use of this file as a pipe if it is
  # invoked as a script.  Specifically, if stdin is in AppleSingle
  # format, then output only its data fork; otherwise, output it
  # unchanged.
  #
  # This might not work on systems where sys.stdin is opened in text
  # mode.
  #
  # Remember to set PYTHONPATH to point to the main cvs2svn directory.

  import sys

  #CHUNK_SIZE = -1
  CHUNK_SIZE = 100

  if CHUNK_SIZE < 0:
    sys.stdout.write(get_maybe_apple_single(sys.stdin.read()))
  else:
    f = get_maybe_apple_single_stream(sys.stdin)
    while True:
      s = f.read(CHUNK_SIZE)
      if not s:
        break
      sys.stdout.write(s)


