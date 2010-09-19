# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2009 CollabNet.  All rights reserved.
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


import os
import re

from cvs2svn_lib.log import logger
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import IllegalSVNPathError
from cvs2svn_lib.common import normalize_svn_path
from cvs2svn_lib.common import is_branch_revision_number


class SymbolTransform:
  """Transform symbol names arbitrarily."""

  def transform(self, cvs_file, symbol_name, revision):
    """Possibly transform SYMBOL_NAME, which was found in CVS_FILE.

    Return the transformed symbol name.  If this SymbolTransform
    doesn't apply, return the original SYMBOL_NAME.  If this symbol
    should be ignored entirely, return None.  (Please note that
    ignoring a branch via this mechanism only causes the branch *name*
    to be ignored; the branch contents will still be converted.
    Usually branches should be excluded using --exclude.)

    REVISION contains the CVS revision number to which the symbol was
    attached in the file as a string (with zeros removed).

    This method is free to use the information in CVS_FILE (including
    CVS_FILE.project) to decide whether and/or how to transform
    SYMBOL_NAME."""

    raise NotImplementedError()


class ReplaceSubstringsSymbolTransform(SymbolTransform):
  """Replace specific substrings in symbol names.

  If the substring occurs multiple times, replace all copies."""

  def __init__(self, old, new):
    self.old = old
    self.new = new

  def transform(self, cvs_file, symbol_name, revision):
    return symbol_name.replace(self.old, self.new)


class NormalizePathsSymbolTransform(SymbolTransform):
  def transform(self, cvs_file, symbol_name, revision):
    try:
      return normalize_svn_path(symbol_name)
    except IllegalSVNPathError, e:
      raise FatalError('Problem with %s: %s' % (symbol_name, e,))


class CompoundSymbolTransform(SymbolTransform):
  """A SymbolTransform that applies other SymbolTransforms in series.

  Each of the contained SymbolTransforms is applied, one after the
  other.  If any of them returns None, then None is returned (the
  following SymbolTransforms are ignored)."""

  def __init__(self, symbol_transforms):
    """Ininitialize a CompoundSymbolTransform.

    SYMBOL_TRANSFORMS is an iterable of SymbolTransform instances."""

    self.symbol_transforms = list(symbol_transforms)

  def transform(self, cvs_file, symbol_name, revision):
    for symbol_transform in self.symbol_transforms:
      symbol_name = symbol_transform.transform(
          cvs_file, symbol_name, revision
          )
      if symbol_name is None:
        # Don't continue with other symbol transforms:
        break

    return symbol_name


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

  def transform(self, cvs_file, symbol_name, revision):
    return self.pattern.sub(self.replacement, symbol_name)


class SymbolMapper(SymbolTransform):
  """A SymbolTransform that transforms specific symbol definitions.

  The user has to specify the exact CVS filename, symbol name, and
  revision number to be transformed, and the new name (or None if the
  symbol should be ignored).  The mappings can be set via a
  constructor argument or by calling __setitem__()."""

  def __init__(self, items=[]):
    """Initialize the mapper.

    ITEMS is a list of tuples (cvs_filename, symbol_name, revision,
    new_name) which will be set as mappings."""

    # A map {(cvs_filename, symbol_name, revision) : new_name}:
    self._map = {}

    for (cvs_filename, symbol_name, revision, new_name) in items:
      self[cvs_filename, symbol_name, revision] = new_name

  def __setitem__(self, (cvs_filename, symbol_name, revision), new_name):
    """Set a mapping for a particular file, symbol, and revision."""

    cvs_filename = os.path.normcase(os.path.normpath(cvs_filename))
    key = (cvs_filename, symbol_name, revision)
    if key in self._map:
      logger.warn(
          'Overwriting symbol transform for\n'
          '    filename=%r symbol=%s revision=%s'
          % (cvs_filename, symbol_name, revision,)
          )
    self._map[key] = new_name

  def transform(self, cvs_file, symbol_name, revision):
    # cvs_file.rcs_path is guaranteed to already be normalised the way
    # os.path.normpath() normalises paths.  No need to call it again.
    cvs_filename = os.path.normcase(cvs_file.rcs_path)
    return self._map.get(
        (cvs_filename, symbol_name, revision), symbol_name
        )


class SubtreeSymbolMapper(SymbolTransform):
  """A SymbolTransform that transforms symbols within a whole repo subtree.

  The user has to specify a CVS repository path (a filename or
  directory) and the original symbol name.  All symbols under that
  path will be renamed to the specified new name (which can be None if
  the symbol should be ignored).  The mappings can be set via a
  constructor argument or by calling __setitem__().  Only the most
  specific rule is applied."""

  def __init__(self, items=[]):
    """Initialize the mapper.

    ITEMS is a list of tuples (cvs_path, symbol_name, new_name)
    which will be set as mappings.  cvs_path is a string naming a
    directory within the CVS repository."""

    # A map {symbol_name : {cvs_path : new_name}}:
    self._map = {}

    for (cvs_path, symbol_name, new_name) in items:
      self[cvs_path, symbol_name] = new_name

  def __setitem__(self, (cvs_path, symbol_name), new_name):
    """Set a mapping for a particular file and symbol."""

    try:
      symbol_map = self._map[symbol_name]
    except KeyError:
      symbol_map = {}
      self._map[symbol_name] = symbol_map

    cvs_path = os.path.normcase(os.path.normpath(cvs_path))
    if cvs_path in symbol_map:
      logger.warn(
          'Overwriting symbol transform for\n'
          '    directory=%r symbol=%s'
          % (cvs_path, symbol_name,)
          )
    symbol_map[cvs_path] = new_name

  def transform(self, cvs_file, symbol_name, revision):
    try:
      symbol_map = self._map[symbol_name]
    except KeyError:
      # No rules for that symbol name
      return symbol_name

    # cvs_file.rcs_path is guaranteed to already be normalised the way
    # os.path.normpath() normalises paths.  No need to call it again.
    cvs_path = os.path.normcase(cvs_file.rcs_path)
    while True:
      try:
        return symbol_map[cvs_path]
      except KeyError:
        new_cvs_path = os.path.dirname(cvs_path)
        if new_cvs_path == cvs_path:
          # No rules found for that path; return symbol name unaltered.
          return symbol_name
        else:
          cvs_path = new_cvs_path


class IgnoreSymbolTransform(SymbolTransform):
  """Ignore symbols matching a specified regular expression."""

  def __init__(self, pattern):
    """Create an SymbolTransform that ignores symbols matching PATTERN.

    PATTERN is a regular expression that should match the whole symbol
    name."""

    self.pattern = re.compile('^' + pattern + '$')

  def transform(self, cvs_file, symbol_name, revision):
    if self.pattern.match(symbol_name):
      return None
    else:
      return symbol_name


class SubtreeSymbolTransform(SymbolTransform):
  """A wrapper around another SymbolTransform, that limits it to a
  specified subtree."""

  def __init__(self, cvs_path, inner_symbol_transform):
    """Constructor.

    CVS_PATH is the path in the repository.  INNER_SYMBOL_TRANSFORM is
    the SymbolTransform to wrap."""

    assert isinstance(cvs_path, str)
    self.__subtree = os.path.normcase(os.path.normpath(cvs_path))
    self.__subtree_len = len(self.__subtree)
    self.__inner = inner_symbol_transform

  def __does_rule_apply_to(self, cvs_file):
    #
    # NOTE: This turns out to be a hot path through the code.
    #
    # It used to use logic similar to SubtreeSymbolMapper.transform().  And
    # it used to take 44% of cvs2svn's total runtime on one real-world test.
    # Now it's been optimized, it takes about 2%.
    #
    # This is called about:
    #   (num_files * num_symbols_per_file * num_subtree_symbol_transforms)
    # times.  On a large repository with several of these transforms,
    # that can exceed 100,000,000 calls.
    #

    # cvs_file.rcs_path is guaranteed to already be normalised the way
    # os.path.normpath() normalises paths.  So we don't need to call
    # os.path.normpath() again.  (The os.path.normpath() function does
    # quite a lot, so it's expensive).
    #
    # os.path.normcase is a no-op on POSIX systems (and therefore fast).
    # Even on Windows it's only a memory allocation and case-change, it
    # should be quite fast.
    cvs_path = os.path.normcase(cvs_file.rcs_path)

    # Do most of the work in a single call, without allocating memory.
    if not cvs_path.startswith(self.__subtree):
      # Different prefix.
      # This is the common "no match" case.
      return False

    if len(cvs_path) == self.__subtree_len:
      # Exact match.
      #
      # This is quite rare, as self.__subtree is usually a directory and
      # cvs_path is always a file.
      return True

    # We know cvs_path starts with self.__subtree, check the next character
    # is a '/' (or if we're on Windows, a '\\').  If so, then cvs_path is a
    # file under the self.__subtree directory tree, so we match.  If not,
    # then it's not a match.
    return cvs_path[self.__subtree_len] == os.path.sep

  def transform(self, cvs_file, symbol_name, revision):
    if self.__does_rule_apply_to(cvs_file):
      return self.__inner.transform(cvs_file, symbol_name, revision)
    else:
      # Rule does not apply to that path; return symbol name unaltered.
      return symbol_name


class TagOnlyTransform(SymbolTransform):
  """A wrapper around another SymbolTransform, that limits it to
  CVS tags (not CVS branches)."""

  def __init__(self, inner_symbol_transform):
    """Constructor.

    INNER_SYMBOL_TRANSFORM is the SymbolTransform to wrap."""
    self.__inner = inner_symbol_transform

  def transform(self, cvs_file, symbol_name, revision):
    if is_branch_revision_number(revision):
      # It's a branch
      return symbol_name
    else:
      # It's a tag
      return self.__inner.transform(cvs_file, symbol_name, revision)


class BranchOnlyTransform(SymbolTransform):
  """A wrapper around another SymbolTransform, that limits it to
  CVS branches (not CVS tags)."""

  def __init__(self, inner_symbol_transform):
    """Constructor.

    INNER_SYMBOL_TRANSFORM is the SymbolTransform to wrap."""
    self.__inner = inner_symbol_transform

  def transform(self, cvs_file, symbol_name, revision):
    if is_branch_revision_number(revision):
      # It's a branch
      return self.__inner.transform(cvs_file, symbol_name, revision)
    else:
      # It's a tag
      return symbol_name


