# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2007 CollabNet.  All rights reserved.
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

"""This module contains classes to transform symbol names."""


from __future__ import generators

import re

from cvs2svn_lib.boolean import *


class SymbolTransform:
  """Transform symbol names arbitrarily."""

  def transform(self, cvs_file, symbol_name, revision, is_branch):
    """Possibly transform SYMBOL_NAME, which was found in CVS_FILE.

    Return the transformed symbol name.  If this SymbolTransform
    doesn't apply, return the original SYMBOL_NAME.  If this symbol
    should be ignored entirely, return None.  (Please note that
    ignoring a branch via this mechanism only causes the branch *name*
    to be ignored; the branch contents will still be converted.
    Usually branches should be excluded using --exclude.)

    REVISION contains the CVS revision number to which the symbol was
    attached in the file as a string (with zeros removed).  IS_BRANCH
    is True iff REVISION is a branch revision number.

    This method is free to use the information in CVS_FILE (including
    CVS_FILE.project) to decide whether and/or how to transform
    SYMBOL_NAME."""

    raise NotImplementedError()


class RegexpSymbolTransform(SymbolTransform):
  """Transform symbols by using a regexp textual substitution."""

  def __init__(self, pattern, replacement):
    """Create a SymbolTransform that transforms symbols matching PATTERN.

    PATTERN is a regular expression that should match the whole symbol
    name.  REPLACEMENT is the replacement text, which may include
    patterns like r'\1' or r'\g<1>' or r'\g<name>' (where 'name' is a
    reference to a named substring in the pattern of the form
    r'(?P<name>...)')."""

    self.pattern = re.compile('^' + pattern + '$')
    self.replacement = replacement

  def transform(self, cvs_file, symbol_name, revision, is_branch):
    return self.pattern.sub(self.replacement, symbol_name)


