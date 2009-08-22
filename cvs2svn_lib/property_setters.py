# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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


import os
import re
import fnmatch
import ConfigParser
from cStringIO import StringIO

from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log


class SVNPropertySetter:
  """Abstract class for objects that can set properties on a SVNCommitItem."""

  def set_properties(self, s_item):
    """Set any properties that can be determined for S_ITEM.

    S_ITEM is an instance of SVNCommitItem.  This method should modify
    S_ITEM.svn_props in place."""

    raise NotImplementedError


class CVSRevisionNumberSetter(SVNPropertySetter):
  """Set the cvs2svn:cvs-rev property to the CVS revision number."""

  propname = 'cvs2svn:cvs-rev'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    s_item.svn_props[self.propname] = s_item.cvs_rev.rev
    s_item.svn_props_changed = True


class ExecutablePropertySetter(SVNPropertySetter):
  """Set the svn:executable property based on cvs_rev.cvs_file.executable."""

  propname = 'svn:executable'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if s_item.cvs_rev.cvs_file.executable:
      s_item.svn_props[self.propname] = '*'


class CVSBinaryFileEOLStyleSetter(SVNPropertySetter):
  """Set the eol-style to None for files with CVS mode '-kb'."""

  propname = 'svn:eol-style'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if s_item.cvs_rev.cvs_file.mode == 'b':
      s_item.svn_props[self.propname] = None


class MimeMapper(SVNPropertySetter):
  """A class that provides mappings from file names to MIME types."""

  propname = 'svn:mime-type'

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
          Log().error(
              "%s: ambiguous MIME mapping for *.%s (%s or %s)\n"
              % (warning_prefix, ext, self.mappings[ext], type)
              )
        self.mappings[ext] = type

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    basename, extension = os.path.splitext(s_item.cvs_rev.cvs_file.basename)

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
      s_item.svn_props[self.propname] = mime_type


class AutoPropsPropertySetter(SVNPropertySetter):
  """Set arbitrary svn properties based on an auto-props configuration.

  This class supports case-sensitive or case-insensitive pattern
  matching.  The command-line default is case-insensitive behavior,
  consistent with Subversion (see
  http://subversion.tigris.org/issues/show_bug.cgi?id=2036).

  As a special extension to Subversion's auto-props handling, if a
  property name is preceded by a '!' then that property is forced to
  be left unset.

  If a property specified in auto-props has already been set to a
  different value, print a warning and leave the old property value
  unchanged.

  Python's treatment of whitespaces in the ConfigParser module is
  buggy and inconsistent.  Usually spaces are preserved, but if there
  is at least one semicolon in the value, and the *first* semicolon is
  preceded by a space, then that is treated as the start of a comment
  and the rest of the line is silently discarded."""

  property_name_pattern = r'(?P<name>[^\!\=\s]+)'
  property_unset_re = re.compile(
      r'^\!\s*' + property_name_pattern + r'$'
      )
  property_set_re = re.compile(
      r'^' + property_name_pattern + r'\s*\=\s*(?P<value>.*)$'
      )
  property_novalue_re = re.compile(
      r'^' + property_name_pattern + r'$'
      )

  quoted_re = re.compile(
      r'^([\'\"]).*\1$'
      )
  comment_re = re.compile(r'\s;')

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

  def __init__(self, configfilename, ignore_case=True):
    config = ConfigParser.ConfigParser()
    if ignore_case:
      self.transform_case = self.squash_case
    else:
      config.optionxform = self.preserve_case
      self.transform_case = self.preserve_case

    configtext = open(configfilename).read()
    if self.comment_re.search(configtext):
      Log().warn(
          '%s: Please be aware that a space followed by a\n'
          'semicolon is sometimes treated as a comment in configuration\n'
          'files.  This pattern was seen in\n'
          '    %s\n'
          'Please make sure that you have not inadvertently commented\n'
          'out part of an important line.'
          % (warning_prefix, configfilename,)
          )

    config.readfp(StringIO(configtext), configfilename)
    self.patterns = []
    sections = config.sections()
    sections.sort()
    for section in sections:
      if self.transform_case(section) == 'auto-props':
        patterns = config.options(section)
        patterns.sort()
        for pattern in patterns:
          value = config.get(section, pattern)
          if value:
            self._add_pattern(pattern, value)

  def squash_case(self, s):
    return s.lower()

  def preserve_case(self, s):
    return s

  def _add_pattern(self, pattern, props):
    propdict = {}
    if self.quoted_re.match(pattern):
      Log().warn(
          '%s: Quoting is not supported in auto-props; please verify rule\n'
          'for %r.  (Using pattern including quotation marks.)\n'
          % (warning_prefix, pattern,)
          )
    for prop in props.split(';'):
      prop = prop.strip()
      m = self.property_unset_re.match(prop)
      if m:
        name = m.group('name')
        Log().debug(
            'auto-props: For %r, leaving %r unset.' % (pattern, name,)
            )
        propdict[name] = None
        continue

      m = self.property_set_re.match(prop)
      if m:
        name = m.group('name')
        value = m.group('value')
        if self.quoted_re.match(value):
          Log().warn(
              '%s: Quoting is not supported in auto-props; please verify\n'
              'rule %r for pattern %r.  (Using value\n'
              'including quotation marks.)\n'
              % (warning_prefix, prop, pattern,)
              )
        Log().debug(
            'auto-props: For %r, setting %r to %r.' % (pattern, name, value,)
            )
        propdict[name] = value
        continue

      m = self.property_novalue_re.match(prop)
      if m:
        name = m.group('name')
        Log().debug(
            'auto-props: For %r, setting %r to the empty string'
            % (pattern, name,)
            )
        propdict[name] = ''
        continue

      Log().warn(
          '%s: in auto-props line for %r, value %r cannot be parsed (ignored)'
          % (warning_prefix, pattern, prop,)
          )

    self.patterns.append(self.Pattern(self.transform_case(pattern), propdict))

  def get_propdict(self, cvs_file):
    basename = self.transform_case(cvs_file.basename)
    propdict = {}
    for pattern in self.patterns:
      if pattern.match(basename):
        for (key,value) in pattern.propdict.items():
          if key in propdict:
            if propdict[key] != value:
              Log().warn(
                  "Contradictory values set for property '%s' for file %s."
                  % (key, cvs_file,))
          else:
            propdict[key] = value

    return propdict

  def set_properties(self, s_item):
    propdict = self.get_propdict(s_item.cvs_rev.cvs_file)
    for (k,v) in propdict.items():
      if k in s_item.svn_props:
        if s_item.svn_props[k] != v:
          Log().warn(
              "Property '%s' already set to %r for file %s; "
              "auto-props value (%r) ignored."
              % (k, s_item.svn_props[k], s_item.cvs_rev.cvs_path, v,))
      else:
        s_item.svn_props[k] = v


class CVSBinaryFileDefaultMimeTypeSetter(SVNPropertySetter):
  """If the file is binary and its svn:mime-type property is not yet
  set, set it to 'application/octet-stream'."""

  propname = 'svn:mime-type'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if s_item.cvs_rev.cvs_file.mode == 'b':
      s_item.svn_props[self.propname] = 'application/octet-stream'


class EOLStyleFromMimeTypeSetter(SVNPropertySetter):
  """Set svn:eol-style based on svn:mime-type.

  If svn:mime-type is known but svn:eol-style is not, then set
  svn:eol-style based on svn:mime-type as follows: if svn:mime-type
  starts with 'text/', then set svn:eol-style to native; otherwise,
  force it to remain unset.  See also issue #39."""

  propname = 'svn:eol-style'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if s_item.svn_props.get('svn:mime-type', None) is not None:
      if s_item.svn_props['svn:mime-type'].startswith("text/"):
        s_item.svn_props[self.propname] = 'native'
      else:
        s_item.svn_props[self.propname] = None


class DefaultEOLStyleSetter(SVNPropertySetter):
  """Set the eol-style if one has not already been set."""

  propname = 'svn:eol-style'

  def __init__(self, value):
    """Initialize with the specified default VALUE."""

    self.value = value

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    s_item.svn_props[self.propname] = self.value


class SVNBinaryFileKeywordsPropertySetter(SVNPropertySetter):
  """Turn off svn:keywords for files with binary svn:eol-style."""

  propname = 'svn:keywords'

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if not s_item.svn_props.get('svn:eol-style'):
      s_item.svn_props[self.propname] = None


class KeywordsPropertySetter(SVNPropertySetter):
  """If the svn:keywords property is not yet set, set it based on the
  file's mode.  See issue #2."""

  propname = 'svn:keywords'

  def __init__(self, value):
    """Use VALUE for the value of the svn:keywords property if it is
    to be set."""

    self.value = value

  def set_properties(self, s_item):
    if self.propname in s_item.svn_props:
      return

    if s_item.cvs_rev.cvs_file.mode in [None, 'kv', 'kvl']:
      s_item.svn_props[self.propname] = self.value


