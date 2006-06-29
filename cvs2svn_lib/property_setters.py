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

"""This module contains classes to set Subversion properties on files."""


import sys
import os
import fnmatch
import ConfigParser

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log


class SVNPropertySetter:
  """Abstract class for objects that can set properties on a SVNCommitItem."""

  def set_properties(self, s_item):
    """Set any properties that can be determined for S_ITEM."""

    raise NotImplementedError


class CVSRevisionNumberSetter(SVNPropertySetter):
  """Set the cvs2svn:cvs-rev property to the CVS revision number."""

  def set_properties(self, s_item):
    s_item.svn_props['cvs2svn:cvs-rev'] = s_item.c_rev.rev
    s_item.svn_props_changed = True


class ExecutablePropertySetter(SVNPropertySetter):
  """Set the svn:executable property based on c_rev.cvs_file.executable."""

  def set_properties(self, s_item):
    if s_item.c_rev.cvs_file.executable:
      s_item.svn_props['svn:executable'] = '*'


class BinaryFileEOLStyleSetter(SVNPropertySetter):
  """Set the eol-style for binary files to None."""

  def set_properties(self, s_item):
    if s_item.c_rev.cvs_file.mode == 'b':
      s_item.svn_props['svn:eol-style'] = None


class MimeMapper(SVNPropertySetter):
  """A class that provides mappings from file names to MIME types."""

  def __init__(self, mime_types_file):
    self.mappings = { }

    for line in file(mime_types_file):
      if line.startswith("#"):
        continue

      # format of a line is something like
      # text/plain c h cpp
      extensions = line.split()
      if len(extensions) < 2:
        continue
      type = extensions.pop(0)
      for ext in extensions:
        if ext in self.mappings and self.mappings[ext] != type:
          sys.stderr.write("%s: ambiguous MIME mapping for *.%s (%s or %s)\n"
                           % (warning_prefix, ext, self.mappings[ext], type))
        self.mappings[ext] = type

  def set_properties(self, s_item):
    basename, extension = os.path.splitext(
        os.path.basename(s_item.c_rev.cvs_path)
        )

    # Extension includes the dot, so strip it (will leave extension
    # empty if filename ends with a dot, which is ok):
    extension = extension[1:]

    # If there is no extension (or the file ends with a period), use
    # the base name for mapping.  This allows us to set mappings for
    # files such as README or Makefile:
    if not extension:
      extension = basename

    mime_type = self.mappings.get(extension, None)
    if mime_type is not None:
      s_item.svn_props['svn:mime-type'] = mime_type


class AutoPropsPropertySetter(SVNPropertySetter):
  """Set arbitrary svn properties based on an auto-props configuration.

  This class supports case-sensitive or case-insensitive pattern
  matching.  The 'correct' behavior is not quite clear, because
  subversion itself does an inconsistent job of handling case in
  auto-props patterns; see
  http://subversion.tigris.org/issues/show_bug.cgi?id=2036.

  If a property specified in auto-props has already been set to a
  different value, print a warning and leave the old property value
  unchanged."""

  class Pattern:
    """Describes the properties to be set for files matching a pattern."""

    def __init__(self, pattern, propdict):
      # A glob-like pattern:
      self.pattern = pattern
      # A dictionary of properties that should be set:
      self.propdict = propdict

    def match(self, basename):
      """Does the file with the specified basename match pattern?"""

      return fnmatch.fnmatch(basename, self.pattern)

  def __init__(self, configfilename, ignore_case):
    config = ConfigParser.ConfigParser()
    if ignore_case:
      self.transform_case = self.squash_case
    else:
      config.optionxform = self.preserve_case
      self.transform_case = self.preserve_case

    config.readfp(file(configfilename))
    self.patterns = []
    for section in config.sections():
      if self.transform_case(section) == 'auto-props':
        for pattern in config.options(section):
          value = config.get(section, pattern)
          if value:
            self._add_pattern(pattern, value)

  def squash_case(self, s):
    return s.lower()

  def preserve_case(self, s):
    return s

  def _add_pattern(self, pattern, value):
    props = value.split(';')
    propdict = {}
    for prop in props:
      s = prop.split('=', 1)
      if len(s) == 1:
        propdict[s[0]] = None
      else:
        propdict[s[0]] = s[1]
    self.patterns.append(
        self.Pattern(self.transform_case(pattern), propdict))

  def get_propdict(self, path):
    basename = self.transform_case(os.path.basename(path))
    propdict = {}
    for pattern in self.patterns:
      if pattern.match(basename):
        for (key,value) in pattern.propdict.items():
          if key in propdict:
            if propdict[key] != value:
              Log().warn(
                  "Contradictory values set for property '%s' for file %s."
                  % (key, path,))
          else:
            propdict[key] = value

    return propdict

  def set_properties(self, s_item):
    propdict = self.get_propdict(s_item.c_rev.cvs_path)
    for (k,v) in propdict.items():
      if k in s_item.svn_props:
        if s_item.svn_props[k] != v:
          Log().warn(
              "Property '%s' already set to %r for file %s; "
              "auto-props value (%r) ignored."
              % (k, s_item.svn_props[k], s_item.c_rev.cvs_path, v,))
      else:
        s_item.svn_props[k] = v


class BinaryFileDefaultMimeTypeSetter(SVNPropertySetter):
  """If the file is binary and its svn:mime-type property is not yet
  set, set it to 'application/octet-stream'."""

  def set_properties(self, s_item):
    if 'svn:mime-type' not in s_item.svn_props \
           and s_item.c_rev.cvs_file.mode == 'b':
      s_item.svn_props['svn:mime-type'] = 'application/octet-stream'


class EOLStyleFromMimeTypeSetter(SVNPropertySetter):
  """Set svn:eol-style based on svn:mime-type.

  If svn:mime-type is known but svn:eol-style is not, then set
  svn:eol-style based on svn:mime-type as follows: if svn:mime-type
  starts with 'text/', then set svn:eol-style to native; otherwise,
  force it to remain unset.  See also issue #39."""

  def set_properties(self, s_item):
    if 'svn:eol-style' not in s_item.svn_props \
       and s_item.svn_props.get('svn:mime-type', None) is not None:
      if s_item.svn_props['svn:mime-type'].startswith("text/"):
        s_item.svn_props['svn:eol-style'] = 'native'
      else:
        s_item.svn_props['svn:eol-style'] = None


class DefaultEOLStyleSetter(SVNPropertySetter):
  """Set the eol-style if one has not already been set."""

  def __init__(self, value):
    """Initialize with the specified default VALUE."""

    self.value = value

  def set_properties(self, s_item):
    if 'svn:eol-style' not in s_item.svn_props:
      s_item.svn_props['svn:eol-style'] = self.value


class KeywordsPropertySetter(SVNPropertySetter):
  """If the svn:keywords property is not yet set, set it based on the
  file's mode.  See issue #2."""

  def __init__(self, value):
    """Use VALUE for the value of the svn:keywords property if it is
    to be set."""

    self.value = value

  def set_properties(self, s_item):
    if 'svn:keywords' not in s_item.svn_props \
           and s_item.c_rev.cvs_file.mode in [None, 'kv', 'kvl']:
      s_item.svn_props['svn:keywords'] = self.value


