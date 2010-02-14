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

  diff = msplit(diff)
  i = 0

  # The number of lines from the old version that have been processed
  # so far:
  ooff = 0

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
      start -= 1

      if start < ooff:
        raise MalformedDeltaException('Deletion before last edit')
      if start > numlines:
        raise MalformedDeltaException('Deletion past file end')
      if start + count > numlines:
        raise MalformedDeltaException('Deletion beyond file end')

      if ooff < start:
        yield ('c', ooff, start - ooff, [])
      yield (command, start, count, [])
      ooff = start + count
    else:
      # "a" - Add command

      if start < ooff:
        raise MalformedDeltaException('Insertion before last edit')
      if start > numlines:
        raise MalformedDeltaException('Insertion past file end')
      if i + count > len(diff):
        raise MalformedDeltaException('Add block truncated')

      if ooff < start:
        yield ('c', ooff, start - ooff, [])
        ooff = start
      yield (command, start, count, diff[i:i + count])
      i += count

  # Pass along the part of the input that follows all of the delta
  # blocks:
  if ooff < numlines:
    yield ('c', ooff, numlines - ooff, [])


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

  def invert_diff(self, diff):
    """Apply the RCS diff DIFF to the current file content and simultaneously
    generate an RCS diff suitable for reverting the change."""

    new_lines = []

    inverse_diff = StringIO()
    adjust = 0
    edit_commands = list(generate_blocks(len(self._lines), diff))
    i = 0
    while i < len(edit_commands):
      (command, start, count, lines) = edit_commands[i]
      i += 1
      if command == 'c':
        new_lines += self._lines[start:start + count]
      elif command == 'd':
        # Handle substitution explicitly, as add must come after del
        # (last add may end in no newline, so no command can follow).
        if i < len(edit_commands) and edit_commands[i][0] == 'a':
          (command2, start2, count2, lines2) = edit_commands[i]
          i += 1
          inverse_diff.write("d%d %d\n" % (start + 1 + adjust, count2,))
          inverse_diff.write("a%d %d\n" % (start + adjust + count2, count,))
          inverse_diff.writelines(self._lines[start:start + count])
          # Now add the lines from the diff:
          new_lines += lines2
          adjust += count2 - count
        else:
          inverse_diff.write("a%d %d\n" % (start + adjust, count))
          inverse_diff.writelines(self._lines[start:start + count])
          adjust -= count
      else:
        inverse_diff.write("d%d %d\n" % (start + 1 + adjust, count))
        # Add the lines from the diff:
        new_lines += lines
        adjust += count

    self._lines = new_lines

    return inverse_diff.getvalue()


