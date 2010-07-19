# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2009 CollabNet.  All rights reserved.
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

"""This module contains the ManWriter class for outputting manpages."""


import optparse
import re


whitespace_re = re.compile(r'\s+')

def wrap(s, width=70):
  # Convert all whitespace substrings to single spaces:
  s = whitespace_re.sub(' ', s)
  s = s.strip()
  retval = []
  while s:
    if len(s) <= width:
      retval.append(s)
      break
    i = s.rfind(' ', 0, width + 1)
    if i == -1:
      # There were no spaces within the first width+1 characters; break
      # at the next space after width:
      i = s.find(' ', width + 1)
      if i == -1:
        # There were no spaces in s at all.
        retval.append(s)
        break

    retval.append(s[:i].rstrip())
    s = s[i+1:].lstrip()

  for (i,line) in enumerate(retval):
    if line.startswith('\'') or line.startswith('.'):
      # These are roff control characters and have to be escaped:
      retval[i] = '\\' + line

  return '\n'.join(retval)


class ManOption(optparse.Option):
  """An optparse.Option that holds an explicit string for the man page."""

  def __init__(self, *args, **kw):
    self.man_help = kw.pop('man_help')
    optparse.Option.__init__(self, *args, **kw)


class ManWriter(object):
  def __init__(
        self,
        parser,
        section=None, date=None, source=None, manual=None,
        short_desc=None, synopsis=None, long_desc=None,
        files=None, authors=None, see_also=None,
        ):
    self.parser = parser
    self.section = section
    self.date = date
    self.source = source
    self.manual = manual
    self.short_desc = short_desc
    self.synopsis = synopsis
    self.long_desc = long_desc
    self.files = files
    self.authors = authors
    self.see_also = see_also

  def write_title(self, f):
    f.write('.\\" Process this file with\n')
    f.write(
        '.\\" groff -man -Tascii %s.%s\n' % (
            self.parser.get_prog_name(),
            self.section,
            )
        )
    f.write(
        '.TH %s "%s" "%s" "%s" "%s"\n' % (
            self.parser.get_prog_name().upper(),
            self.section,
            self.date.strftime('%b %d, %Y'),
            self.source,
            self.manual,
            )
        )

  def write_name(self, f):
    f.write('.SH "NAME"\n')
    f.write(
        '%s \- %s\n' % (
            self.parser.get_prog_name(),
            self.short_desc,
            )
        )

  def write_synopsis(self, f):
    f.write('.SH "SYNOPSIS"\n')
    f.write(self.synopsis)

  def write_description(self, f):
    f.write('.SH "DESCRIPTION"\n')
    f.write(self.long_desc)

  def _get_option_strings(self, option):
    """Return a list of option strings formatted with their metavariables.

    This method is very similar to
    optparse.HelpFormatter.format_option_strings().

    """

    if option.takes_value():
      metavar = (option.metavar or option.dest).lower()
      short_opts = [
          '\\fB%s\\fR \\fI%s\\fR' % (opt, metavar)
          for opt in option._short_opts
          ]
      long_opts = [
          '\\fB%s\\fR=\\fI%s\\fR' % (opt, metavar)
          for opt in option._long_opts
          ]
    else:
      short_opts = [
          '\\fB%s\\fR' % (opt,)
          for opt in option._short_opts
          ]
      long_opts = [
          '\\fB%s\\fR' % (opt,)
          for opt in option._long_opts
          ]

    return short_opts + long_opts

  def _write_option(self, f, option):
    man_help = getattr(option, 'man_help', option.help)

    if man_help is not optparse.SUPPRESS_HELP:
      man_help = wrap(man_help)
      f.write('.IP "%s"\n' % (', '.join(self._get_option_strings(option)),))
      f.write('%s\n' % (man_help,))

  def _write_container_help(self, f, container):
    for option in container.option_list:
      if option.help is not optparse.SUPPRESS_HELP:
        self._write_option(f, option)

  def write_options(self, f):
    f.write('.SH "OPTIONS"\n')
    if self.parser.option_list:
      (self._write_container_help(f, self.parser))
    for group in self.parser.option_groups:
      f.write('.SH "%s"\n' % (group.title.upper(),))
      if group.description:
        f.write(self.format_description(group.description) + '\n')
      self._write_container_help(f, group)

  def write_files(self, f):
    f.write('.SH "FILES"\n')
    f.write(self.files)

  def write_authors(self, f):
    f.write('.SH "AUTHORS"\n')
    f.write("Main authors are:\n")
    for author in self.authors:
      f.write(".br\n")
      f.write(author + "\n")
    f.write(".PP\n")
    f.write(
      "Manpage was written for the Debian GNU/Linux system by\n"
      "Laszlo 'GCS' Boszormenyi <gcs@lsc.hu> (but may be used by others).\n")

  def write_see_also(self, f):
    f.write('.SH "SEE ALSO"\n')
    f.write(', '.join([
          '%s(%s)' % (name, section,)
          for (name, section,) in self.see_also
          ]) + '\n')

  def write_manpage(self, f):
    self.write_title(f)
    self.write_name(f)
    self.write_synopsis(f)
    self.write_description(f)
    self.write_options(f)
    self.write_files(f)
    self.write_authors(f)
    self.write_see_also(f)


