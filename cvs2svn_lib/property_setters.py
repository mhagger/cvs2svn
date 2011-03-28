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
from cvs2svn_lib.log import logger


def _squash_case(s):
  return s.lower()


def _preserve_case(s):
  return s


def cvs_file_is_binary(cvs_file):
  return cvs_file.mode == 'b'


class FilePropertySetter(object):
  """Abstract class for objects that set properties on a CVSFile."""

  def maybe_set_property(self, cvs_file, name, value):
    """Set a property on CVS_FILE if it does not already have a value.

    This method is here for the convenience of derived classes."""

    if name not in cvs_file.properties:
      cvs_file.properties[name] = value

  def set_properties(self, cvs_file):
    """Set any properties needed for CVS_FILE.

    CVS_FILE is an instance of CVSFile.  This method should modify
    CVS_FILE.properties in place."""

    raise NotImplementedError()


class ExecutablePropertySetter(FilePropertySetter):
  """Set the svn:executable property based on cvs_file.executable."""

  def set_properties(self, cvs_file):
    if cvs_file.executable:
      self.maybe_set_property(cvs_file, 'svn:executable', '*')


class DescriptionPropertySetter(FilePropertySetter):
  """Set the cvs:description property based on cvs_file.description."""

  def __init__(self, propname='cvs:description'):
    self.propname = propname

  def set_properties(self, cvs_file):
    if cvs_file.description:
      self.maybe_set_property(cvs_file, self.propname, cvs_file.description)


class CVSBinaryFileEOLStyleSetter(FilePropertySetter):
  """Set the eol-style to None for files with CVS mode '-kb'."""

  def set_properties(self, cvs_file):
    if cvs_file.mode == 'b':
      self.maybe_set_property(cvs_file, 'svn:eol-style', None)


class MimeMapper(FilePropertySetter):
  """A class that provides mappings from file names to MIME types."""

  propname = 'svn:mime-type'

  def __init__(
          self, mime_types_file=None, mime_mappings=None,
          ignore_case=False
          ):
    """Constructor.

    Arguments:

      mime_types_file -- a path to a MIME types file on disk.  Each
          line of the file should contain the MIME type, then a
          whitespace-separated list of file extensions; e.g., one line
          might be 'text/plain txt c h cpp hpp'.  (See
          http://en.wikipedia.org/wiki/Mime.types for information
          about mime.types files):

      mime_mappings -- a dictionary mapping a file extension to a MIME
          type; e.g., {'txt': 'text/plain', 'cpp': 'text/plain'}.

      ignore_case -- True iff case should be ignored in filename
          extensions.  Setting this option to True can be useful if
          your CVS repository was used on systems with
          case-insensitive filenames, in which case you might have a
          mix of uppercase and lowercase filenames."""

    self.mappings = { }
    if ignore_case:
      self.transform_case = _squash_case
    else:
      self.transform_case = _preserve_case

    if mime_types_file is None and mime_mappings is None:
      logger.error('Should specify MIME types file or dict.\n')

    if mime_types_file is not None:
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
          ext = self.transform_case(ext)
          if ext in self.mappings and self.mappings[ext] != type:
            logger.error(
                "%s: ambiguous MIME mapping for *.%s (%s or %s)\n"
                % (warning_prefix, ext, self.mappings[ext], type)
                )
          self.mappings[ext] = type

    if mime_mappings is not None:
      for ext, type in mime_mappings.iteritems():
        ext = self.transform_case(ext)
        if ext in self.mappings and self.mappings[ext] != type:
          logger.error(
              "%s: ambiguous MIME mapping for *.%s (%s or %s)\n"
              % (warning_prefix, ext, self.mappings[ext], type)
              )
        self.mappings[ext] = type

  def set_properties(self, cvs_file):
    if self.propname in cvs_file.properties:
      return

    basename, extension = os.path.splitext(cvs_file.rcs_basename)

    # Extension includes the dot, so strip it (will leave extension
    # empty if filename ends with a dot, which is ok):
    extension = extension[1:]

    # If there is no extension (or the file ends with a period), use
    # the base name for mapping.  This allows us to set mappings for
    # files such as README or Makefile:
    if not extension:
      extension = basename

    extension = self.transform_case(extension)

    mime_type = self.mappings.get(extension, None)
    if mime_type is not None:
      cvs_file.properties[self.propname] = mime_type


class AutoPropsPropertySetter(FilePropertySetter):
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
      self.transform_case = _squash_case
    else:
      config.optionxform = _preserve_case
      self.transform_case = _preserve_case

    configtext = open(configfilename).read()
    if self.comment_re.search(configtext):
      logger.warn(
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

  def _add_pattern(self, pattern, props):
    propdict = {}
    if self.quoted_re.match(pattern):
      logger.warn(
          '%s: Quoting is not supported in auto-props; please verify rule\n'
          'for %r.  (Using pattern including quotation marks.)\n'
          % (warning_prefix, pattern,)
          )
    for prop in props.split(';'):
      prop = prop.strip()
      m = self.property_unset_re.match(prop)
      if m:
        name = m.group('name')
        logger.debug(
            'auto-props: For %r, leaving %r unset.' % (pattern, name,)
            )
        propdict[name] = None
        continue

      m = self.property_set_re.match(prop)
      if m:
        name = m.group('name')
        value = m.group('value')
        if self.quoted_re.match(value):
          logger.warn(
              '%s: Quoting is not supported in auto-props; please verify\n'
              'rule %r for pattern %r.  (Using value\n'
              'including quotation marks.)\n'
              % (warning_prefix, prop, pattern,)
              )
        logger.debug(
            'auto-props: For %r, setting %r to %r.' % (pattern, name, value,)
            )
        propdict[name] = value
        continue

      m = self.property_novalue_re.match(prop)
      if m:
        name = m.group('name')
        logger.debug(
            'auto-props: For %r, setting %r to the empty string'
            % (pattern, name,)
            )
        propdict[name] = ''
        continue

      logger.warn(
          '%s: in auto-props line for %r, value %r cannot be parsed (ignored)'
          % (warning_prefix, pattern, prop,)
          )

    self.patterns.append(self.Pattern(self.transform_case(pattern), propdict))

  def get_propdict(self, cvs_file):
    basename = self.transform_case(cvs_file.rcs_basename)
    propdict = {}
    for pattern in self.patterns:
      if pattern.match(basename):
        for (key,value) in pattern.propdict.items():
          if key in propdict:
            if propdict[key] != value:
              logger.warn(
                  "Contradictory values set for property '%s' for file %s."
                  % (key, cvs_file,))
          else:
            propdict[key] = value

    return propdict

  def set_properties(self, cvs_file):
    propdict = self.get_propdict(cvs_file)
    for (k,v) in propdict.items():
      if k in cvs_file.properties:
        if cvs_file.properties[k] != v:
          logger.warn(
              "Property '%s' already set to %r for file %s; "
              "auto-props value (%r) ignored."
              % (k, cvs_file.properties[k], cvs_file.cvs_path, v,)
              )
      else:
        cvs_file.properties[k] = v


class CVSBinaryFileDefaultMimeTypeSetter(FilePropertySetter):
  """If the file is binary and its svn:mime-type property is not yet
  set, set it to 'application/octet-stream'."""

  def set_properties(self, cvs_file):
    if cvs_file.mode == 'b':
      self.maybe_set_property(
          cvs_file, 'svn:mime-type', 'application/octet-stream'
          )


class EOLStyleFromMimeTypeSetter(FilePropertySetter):
  """Set svn:eol-style based on svn:mime-type.

  If svn:mime-type is known but svn:eol-style is not, then set
  svn:eol-style based on svn:mime-type as follows: if svn:mime-type
  starts with 'text/', then set svn:eol-style to native; otherwise,
  force it to remain unset.  See also issue #39."""

  propname = 'svn:eol-style'

  def set_properties(self, cvs_file):
    if self.propname in cvs_file.properties:
      return

    mime_type = cvs_file.properties.get('svn:mime-type', None)
    if mime_type:
      if mime_type.startswith("text/"):
        cvs_file.properties[self.propname] = 'native'
      else:
        cvs_file.properties[self.propname] = None


class DefaultEOLStyleSetter(FilePropertySetter):
  """Set the eol-style if one has not already been set."""

  valid_values = {
      None : None,
      # Also treat "binary" as None:
      'binary' : None,
      'native' : 'native',
      'CRLF' : 'CRLF', 'LF' : 'LF', 'CR' : 'CR',
      }

  def __init__(self, value):
    """Initialize with the specified default VALUE."""

    try:
      # Check that value is valid, and translate it to the proper case
      self.value = self.valid_values[value]
    except KeyError:
      raise ValueError(
          'Illegal value specified for the default EOL option: %r' % (value,)
          )

  def set_properties(self, cvs_file):
    self.maybe_set_property(cvs_file, 'svn:eol-style', self.value)


class SVNBinaryFileKeywordsPropertySetter(FilePropertySetter):
  """Turn off svn:keywords for files with binary svn:eol-style."""

  propname = 'svn:keywords'

  def set_properties(self, cvs_file):
    if self.propname in cvs_file.properties:
      return

    if not cvs_file.properties.get('svn:eol-style'):
      cvs_file.properties[self.propname] = None


class KeywordsPropertySetter(FilePropertySetter):
  """If the svn:keywords property is not yet set, set it based on the
  file's mode.  See issue #2."""

  def __init__(self, value):
    """Use VALUE for the value of the svn:keywords property if it is
    to be set."""

    self.value = value

  def set_properties(self, cvs_file):
    if cvs_file.mode in [None, 'kv', 'kvl']:
      self.maybe_set_property(cvs_file, 'svn:keywords', self.value)


class ConditionalPropertySetter(object):
  """Delegate to the passed property setters when the passed predicate applies.
  The predicate should be a function that takes a CVSFile or CVSRevision
  argument and return True if the property setters should be applied."""

  def __init__(self, predicate, *property_setters):
    self.predicate = predicate
    self.property_setters = property_setters

  def set_properties(self, cvs_file_or_rev):
    if self.predicate(cvs_file_or_rev):
      for property_setter in self.property_setters:
        property_setter.set_properties(cvs_file_or_rev)


class RevisionPropertySetter:
  """Abstract class for objects that can set properties on a CVSRevision."""

  def set_properties(self, cvs_rev):
    """Set any properties that can be determined for CVS_REV.

    CVS_REV is an instance of CVSRevision.  This method should modify
    CVS_REV.properties in place."""

    raise NotImplementedError()


class CVSRevisionNumberSetter(RevisionPropertySetter):
  """Store the CVS revision number to an SVN property."""

  def __init__(self, propname='cvs2svn:cvs-rev'):
    self.propname = propname

  def set_properties(self, cvs_rev):
    if self.propname in cvs_rev.properties:
      return

    cvs_rev.properties[self.propname] = cvs_rev.rev


