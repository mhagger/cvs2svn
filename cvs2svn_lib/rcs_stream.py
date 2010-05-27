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
  (COMMAND, START, ARG) for each block implied by DIFF.  Tuples
  describe the ed commands:

      ('a', INPUT_POS, LINES) : add LINES at INPUT_POS.  LINES is a
          list of strings.

      ('d', INPUT_POS, COUNT) : delete COUNT input lines starting at line
          START.

  In all cases, START is expressed as a zero-offset line number within
  the input revision."""

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


def generate_blocks(numlines, diff):
  """Generate edit blocks from an RCS diff block.

  NUMLINES is the number of lines in the old revision; DIFF is a
  string holding an entire RCS file delta.  Generate a tuple (COMMAND,
  START, COUNT, [LINE,...]) for each block implied by DIFF.  Blocks
  consist of ed commands and copy blocks:

      ('a', START, COUNT, LINES) : add LINES at the current position
          in the output.  START is the logical position in the input
          revision at which the insertion ends up.

      ('d', START, COUNT, []) : ignore the COUNT lines starting at
          line START in the input.

      ('c', START, COUNT, []) : copy COUNT lines, starting at line
          START in the input, to the output at the current position.

  START is expressed as a zero-offset line number within the
  input revision."""

  # The number of lines from the old version that have been processed
  # so far:
  input_pos = 0

  for (command, start, arg) in generate_edits(diff):
    if command == 'd':
      # "d" - Delete command
      count = arg
      if start < input_pos:
        raise MalformedDeltaException('Deletion before last edit')
      if start > numlines:
        raise MalformedDeltaException('Deletion past file end')
      if start + count > numlines:
        raise MalformedDeltaException('Deletion beyond file end')

      if input_pos < start:
        yield ('c', input_pos, start - input_pos, [])
      yield ('d', start, count, [])
      input_pos = start + count
    else:
      # "a" - Add command
      lines = arg
      if start < input_pos:
        raise MalformedDeltaException('Insertion before last edit')
      if start > numlines:
        raise MalformedDeltaException('Insertion past file end')

      if input_pos < start:
        yield ('c', input_pos, start - input_pos, [])
        input_pos = start
      yield ('a', start, len(lines), lines)

  # Pass along the part of the input that follows all of the delta
  # blocks:
  if input_pos < numlines:
    yield ('c', input_pos, numlines - input_pos, [])


def reorder_blocks(blocks):
  """Reorder blocks to reverse delete,add pairs.

  If a delete block is followed by an add block, emit the blocks in
  reverse order.  This is part of inverting diffs, because when the
  blocks are inverted the blocks will be in the original delete,add
  order.

  1. This is required because the last line in the last 'add' block
     might end in a line that is not terminated with a newline, in
     which case no other command is allowed to follow it.

  2. It is also nice to keep deltas in a canonical order; among other
     things, this ensures that inverting twice gives back the original
     delta."""

  i = iter(blocks)

  try:
    (command1, start1, count1, lines1) = i.next()
  except StopIteration:
    return

  for (command2, start2, count2, lines2) in i:
    if command1 == 'd' and command2 == 'a':
      yield ('a', start2 - count1, count2, lines2)
    else:
      yield (command1, start1, count1, lines1)
      (command1, start1, count1, lines1) = (command2, start2, count2, lines2)

  yield (command1, start1, count1, lines1)


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

    self._lines = msplit(text)

  def get_text(self):
    """Return the current file content."""

    return "".join(self._lines)

  def apply_diff(self, diff):
    """Apply the RCS diff DIFF to the current file content."""

    new_lines = []

    for (command, start, count, lines) \
            in generate_blocks(len(self._lines), diff):
      if command == 'c':
        new_lines += self._lines[start:start + count]
      elif command == 'd':
        pass
      else:
        new_lines += lines

    self._lines = new_lines

  def apply_and_invert_diff(self, diff, inverse_diff):
    """Apply DIFF and generate its inverse.

    Apply the RCS diff DIFF to the current file content.
    Simultaneously generate an RCS diff suitable for reverting the
    change, and write it to the file-like object INVERSE_DIFF.  Return
    INVERSE_DIFF."""

    new_lines = []

    adjust = 0
    for (command, start, count, lines) \
            in reorder_blocks(generate_blocks(len(self._lines), diff)):
      if command == 'c':
        new_lines += self._lines[start:start + count]
      elif command == 'd':
        inverse_diff.write("a%d %d\n" % (start + adjust, count))
        inverse_diff.writelines(self._lines[start:start + count])
        adjust -= count
      else:
        inverse_diff.write("d%d %d\n" % (start + 1 + adjust, count))
        # Add the lines from the diff:
        new_lines += lines
        adjust += count

    self._lines = new_lines

  def invert_diff(self, diff):
    """Apply DIFF and generate its inverse.

    Apply the RCS diff DIFF to the current file content.
    Simultaneously generate an RCS diff suitable for reverting the
    change, and return it as a string."""

    inverse_diff = StringIO()
    self.apply_and_invert_diff(diff, inverse_diff)
    return inverse_diff.getvalue()


