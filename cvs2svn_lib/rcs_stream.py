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

class RCSStream:
  """This class represents a single file object to which RCS deltas can be
  applied in various ways."""

  ad_command = re.compile(r'^([ad])(\d+)\s(\d+)\n$')
  a_command = re.compile(r'^a(\d+)\s(\d+)\n$')

  def __init__(self, text):
    """Instantiate and initialize the file content with TEXT."""

    self._texts = msplit(text)

  def get_text(self):
    """Return the current file content."""

    return "".join(self._texts)

  def apply_diff(self, diff):
    """Apply the RCS diff DIFF to the current file content."""

    ntexts = []
    ooff = 0
    diffs = msplit(diff)
    i = 0
    while i < len(diffs):
      admatch = self.ad_command.match(diffs[i])
      if not admatch:
        raise MalformedDeltaException('Bad ed command')
      i += 1
      sl = int(admatch.group(2))
      cn = int(admatch.group(3))
      if admatch.group(1) == 'd': # "d" - Delete command
        sl -= 1
        if sl < ooff:
          raise MalformedDeltaException('Deletion before last edit')
        if sl > len(self._texts):
          raise MalformedDeltaException('Deletion past file end')
        if sl + cn > len(self._texts):
          raise MalformedDeltaException('Deletion beyond file end')
        ntexts += self._texts[ooff:sl]
        ooff = sl + cn
      else: # "a" - Add command
        if sl < ooff: # Also catches same place
          raise MalformedDeltaException('Insertion before last edit')
        if sl > len(self._texts):
          raise MalformedDeltaException('Insertion past file end')
        ntexts += self._texts[ooff:sl] + diffs[i:i + cn]
        ooff = sl
        i += cn
    self._texts = ntexts + self._texts[ooff:]

  def invert_diff(self, diff):
    """Apply the RCS diff DIFF to the current file content and simultaneously
    generate an RCS diff suitable for reverting the change."""

    ntexts = []
    ooff = 0
    diffs = msplit(diff)
    ndiffs = []
    adjust = 0
    i = 0
    while i < len(diffs):
      admatch = self.ad_command.match(diffs[i])
      if not admatch:
        raise MalformedDeltaException('Bad ed command')
      i += 1
      sl = int(admatch.group(2))
      cn = int(admatch.group(3))
      if admatch.group(1) == 'd': # "d" - Delete command
        sl -= 1
        if sl < ooff:
          raise MalformedDeltaException('Deletion before last edit')
        if sl > len(self._texts):
          raise MalformedDeltaException('Deletion past file end')
        if sl + cn > len(self._texts):
          raise MalformedDeltaException('Deletion beyond file end')
        # Handle substitution explicitly, as add must come after del
        # (last add may end in no newline, so no command can follow).
        if i < len(diffs):
          amatch = self.a_command.match(diffs[i])
        else:
          amatch = None
        if amatch and int(amatch.group(1)) == sl + cn:
          cn2 = int(amatch.group(2))
          i += 1
          ndiffs += ["d%d %d\na%d %d\n" % \
                        (sl + 1 + adjust, cn2, sl + adjust + cn2, cn)] + \
                    self._texts[sl:sl + cn]
          ntexts += self._texts[ooff:sl] + diffs[i:i + cn2]
          adjust += cn2 - cn
          i += cn2
        else:
          ndiffs += ["a%d %d\n" % (sl + adjust, cn)] + \
                    self._texts[sl:sl + cn]
          ntexts += self._texts[ooff:sl]
          adjust -= cn
        ooff = sl + cn
      else: # "a" - Add command
        if sl < ooff: # Also catches same place
          raise MalformedDeltaException('Insertion before last edit')
        if sl > len(self._texts):
          raise MalformedDeltaException('Insertion past file end')
        ndiffs += ["d%d %d\n" % (sl + 1 + adjust, cn)]
        ntexts += self._texts[ooff:sl] + diffs[i:i + cn]
        ooff = sl
        adjust += cn
        i += cn
    self._texts = ntexts + self._texts[ooff:]
    return "".join(ndiffs)

