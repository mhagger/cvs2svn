# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007 CollabNet.  All rights reserved.
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

"""This module processes RCS diffs (deltas)."""


from cStringIO import StringIO
import re


def msplit(s):
  """Split S into an array of lines.

  Only \n is a line separator. The line endings are part of the lines."""

  # return s.splitlines(True) clobbers \r
  re = [ i + "\n" for i in s.split("\n") ]
  re[-1] = re[-1][:-1]
  if not re[-1]:
    del re[-1]
  return re


class MalformedDeltaException(Exception):
  """A malformed RCS delta was encountered."""

  pass


ed_command_re = re.compile(r'^([ad])(\d+)\s(\d+)\n$')


def generate_edits(diff):
  """Generate edit commands from an RCS diff block.

  DIFF is a string holding an entire RCS file delta.  Generate a tuple
  (COMMAND, INPUT_POS, ARG) for each block implied by DIFF.  Tuples
  describe the ed commands:

      ('a', INPUT_POS, LINES) : add LINES at INPUT_POS.  LINES is a
          list of strings.

      ('d', INPUT_POS, COUNT) : delete COUNT input lines starting at
          line INPUT_POS.

  In all cases, INPUT_POS is expressed as a zero-offset line number
  within the input revision."""

  diff = msplit(diff)
  i = 0

  while i < len(diff):
    m = ed_command_re.match(diff[i])
    if not m:
      raise MalformedDeltaException('Bad ed command')
    i += 1
    command = m.group(1)
    start = int(m.group(2))
    count = int(m.group(3))
    if command == 'd':
      # "d" - Delete command
      yield ('d', start - 1, count)
    else:
      # "a" - Add command
      if i + count > len(diff):
        raise MalformedDeltaException('Add block truncated')
      yield ('a', start, diff[i:i + count])
      i += count


def merge_blocks(blocks):
  """Merge adjacent 'r'eplace or 'c'opy blocks."""

  i = iter(blocks)

  try:
    (command1, old_lines1, new_lines1) = i.next()
  except StopIteration:
    return

  for (command2, old_lines2, new_lines2) in i:
    if command1 == 'r' and command2 == 'r':
      old_lines1 += old_lines2
      new_lines1 += new_lines2
    elif command1 == 'c' and command2 == 'c':
      old_lines1 += old_lines2
      new_lines1 = old_lines1
    else:
      yield (command1, old_lines1, new_lines1)
      (command1, old_lines1, new_lines1) = (command2, old_lines2, new_lines2)

  yield (command1, old_lines1, new_lines1)


def invert_blocks(blocks):
  """Invert the blocks in BLOCKS.

  BLOCKS is an iterable over blocks.  Invert them, in the sense that
  the input becomes the output and the output the input."""

  for (command, old_lines, new_lines) in blocks:
    yield (command, new_lines, old_lines)


def generate_edits_from_blocks(blocks):
  """Convert BLOCKS into an equivalent series of RCS edits.

  The edits are generated as tuples in the format described in the
  docstring for generate_edits().

  It is important that deletes are emitted before adds in the output
  for two reasons:

  1. The last line in the last 'add' block might end in a line that is
     not terminated with a newline, in which case no other command is
     allowed to follow it.

  2. This is the canonical order used by RCS; this ensures that
     inverting twice gives back the original delta."""

  # Merge adjacent 'r'eplace blocks to ensure that we emit adds and
  # deletes in the right order:
  blocks = merge_blocks(blocks)

  input_position = 0
  for (command, old_lines, new_lines) in blocks:
    if command == 'c':
      input_position += len(old_lines)
    elif command == 'r':
      if old_lines:
        yield ('d', input_position, len(old_lines))
        input_position += len(old_lines)
      if new_lines:
        yield ('a', input_position, new_lines)


def write_edits(f, edits):
  """Write EDITS to file-like object f as an RCS diff."""

  for (command, input_position, arg) in edits:
    if command == 'd':
      f.write('d%d %d\n' % (input_position + 1, arg,))
    elif command == 'a':
      lines = arg
      f.write('a%d %d\n' % (input_position, len(lines),))
      f.writelines(lines)
      del lines
    else:
      raise MalformedDeltaException('Unknown command %r' % (command,))


class RCSStream:
  """This class allows RCS deltas to be accumulated.

  This file holds the contents of a single RCS version in memory as an
  array of lines.  It is able to apply an RCS delta to the version,
  thereby transforming the stored text into the following RCS version.
  While doing so, it can optionally also return the inverted delta.

  This class holds revisions in memory.  It uses temporary memory
  space of a few times the size of a single revision plus a few times
  the size of a single delta."""

  def __init__(self, text):
    """Instantiate and initialize the file content with TEXT."""

    self.set_text(text)

  def get_text(self):
    """Return the current file content."""

    return "".join(self._lines)

  def set_lines(self, lines):
    """Set the current contents to the specified LINES.

    LINES is an iterable over well-formed lines; i.e., each line
    contains exactly one LF as its last character, except that the
    list line can be unterminated.  LINES will be consumed
    immediately; if it is a sequence, it will be copied."""

    self._lines = list(lines)

  def set_text(self, text):
    """Set the current file content."""

    self._lines = msplit(text)

  def generate_blocks(self, edits):
    """Generate edit blocks from an iterable of RCS edits.

    EDITS is an iterable over RCS edits, as generated by
    generate_edits().  Generate a tuple (COMMAND, OLD_LINES,
    NEW_LINES) for each block implied by EDITS when applied to the
    current contents of SELF.  OLD_LINES and NEW_LINES are lists of
    strings, where each string is one line.  OLD_LINES and NEW_LINES
    are newly-allocated lists, though they might both point at the
    same list.  Blocks consist of copy and replace commands:

        ('c', OLD_LINES, NEW_LINES) : copy the lines from one version
            to the other, unaltered.  In this case
            OLD_LINES==NEW_LINES.

        ('r', OLD_LINES, NEW_LINES) : replace OLD_LINES with
            NEW_LINES.  Either OLD_LINES or NEW_LINES (or both) might
            be empty."""

    # The number of lines from the old version that have been processed
    # so far:
    input_pos = 0

    for (command, start, arg) in edits:
      if command == 'd':
        # "d" - Delete command
        count = arg
        if start < input_pos:
          raise MalformedDeltaException('Deletion before last edit')
        if start > len(self._lines):
          raise MalformedDeltaException('Deletion past file end')
        if start + count > len(self._lines):
          raise MalformedDeltaException('Deletion beyond file end')

        if input_pos < start:
          copied_lines = self._lines[input_pos:start]
          yield ('c', copied_lines, copied_lines)
          del copied_lines
        yield ('r', self._lines[start:start + count], [])
        input_pos = start + count
      else:
        # "a" - Add command
        lines = arg
        if start < input_pos:
          raise MalformedDeltaException('Insertion before last edit')
        if start > len(self._lines):
          raise MalformedDeltaException('Insertion past file end')

        if input_pos < start:
          copied_lines = self._lines[input_pos:start]
          yield ('c', copied_lines, copied_lines)
          del copied_lines
          input_pos = start
        yield ('r', [], lines)

    # Pass along the part of the input that follows all of the delta
    # blocks:
    copied_lines = self._lines[input_pos:]
    if copied_lines:
      yield ('c', copied_lines, copied_lines)

  def apply_diff(self, diff):
    """Apply the RCS diff DIFF to the current file content."""

    lines = []

    blocks = self.generate_blocks(generate_edits(diff))
    for (command, old_lines, new_lines) in blocks:
      lines += new_lines

    self._lines = lines

  def apply_and_invert_edits(self, edits):
    """Apply EDITS and generate their inverse.

    Apply EDITS to the current file content.  Simultaneously generate
    edits suitable for reverting the change."""

    blocks = self.generate_blocks(edits)

    # Blocks have to be merged so that adjacent delete,add edits are
    # generated in that order:
    blocks = merge_blocks(blocks)

    # Convert the iterable into a list (1) so that we can modify
    # self._lines in-place, (2) because we need it twice.
    blocks = list(blocks)

    self._lines = []
    for (command, old_lines, new_lines) in blocks:
      self._lines += new_lines

    return generate_edits_from_blocks(invert_blocks(blocks))

  def invert_diff(self, diff):
    """Apply DIFF and generate its inverse.

    Apply the RCS diff DIFF to the current file content.
    Simultaneously generate an RCS diff suitable for reverting the
    change, and return it as a string."""

    inverse_diff = StringIO()
    write_edits(
        inverse_diff, self.apply_and_invert_edits(generate_edits(diff))
        )
    return inverse_diff.getvalue()


