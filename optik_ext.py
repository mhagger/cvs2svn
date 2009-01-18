# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
""" Copyright (c) 2003-2005 LOGILAB S.A. (Paris, FRANCE).
 http://www.logilab.fr/ -- mailto:contact@logilab.fr

add an abstraction level to transparently import optik classes from optparse
(python >= 2.3) or the optik package.
It also defines three new types for optik/optparse command line parser :

  * regexp
    argument of this type will be converted using re.compile
  * csv
    argument of this type will be converted using split(',')
  * yn
    argument of this type will be true if 'y' or 'yes', false if 'n' or 'no'
  * named
    argument of this type are in the form <NAME>=<VALUE> or <NAME>:<VALUE>

"""

__revision__ = '$Id: optik_ext.py,v 1.14 2005/04/11 10:50:42 syt Exp $'

from optparse import HelpFormatter

import sys
import time


class ManHelpFormatter(HelpFormatter):
    """Format help using man pages ROFF format"""

    def __init__ (self,
                  indent_increment=0,
                  max_help_position=24,
                  width=79,
                  short_first=0):
        HelpFormatter.__init__ (
            self, indent_increment, max_help_position, width, short_first)

    def format_heading (self, heading):
        return '.SH %s\n' % heading.upper()

    def format_description (self, description):
        return description

    def format_option (self, option):
        opt_help = ' '.join([l.strip() for l in option.help.splitlines()])
        return '''.IP "%s"
%s
''' % (option.option_strings, opt_help)

    def format_head(self, optparser, pkginfo, section=1):
        pgm = optparser._get_prog_name()
        return '%s\n%s\n%s\n%s' % (self.format_title(pgm, section),
                                   self.format_short_description(pgm, pkginfo.short_desc),
                                   self.format_synopsis(pgm),
                                   self.format_long_description(pgm, pkginfo.long_desc))

    def format_title(self, pgm, section):
        date = '-'.join([str(num) for num in time.localtime()[:3]])
        return '.TH %s %s "%s" %s' % (pgm, section, date, pgm)

    def format_short_description(self, pgm, short_desc):
        return '''.SH NAME
.B %s
\- %s
''' % (pgm, short_desc.strip())

    def format_synopsis(self, pgm):
        return '''.SH SYNOPSIS
.B  %s
[
.I OPTIONS
] [
.I <arguments>
]
''' % pgm

    def format_long_description(self, pgm, long_desc):
        long_desc = '\n'.join([line.lstrip()
                               for line in long_desc.splitlines()])
        long_desc = long_desc.replace('\n.\n', '\n\n')
        if long_desc.lower().startswith(pgm):
            long_desc = long_desc[len(pgm):]
        return '''.SH DESCRIPTION
.B %s
%s
''' % (pgm, long_desc.strip())

    def format_tail(self, pkginfo):
        return '''.SH SEE ALSO
/usr/share/doc/pythonX.Y-%s/

.SH COPYRIGHT
%s

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston,
MA 02111-1307 USA.
.SH BUGS
Please report bugs on the project\'s mailing list:
%s

.SH AUTHOR
%s <%s>
''' % (getattr(pkginfo, 'debian_name', pkginfo.modname), pkginfo.copyright,
       pkginfo.mailinglist, pkginfo.author, pkginfo.author_email)


def generate_manpage(optparser, pkginfo, section=1, stream=sys.stdout):
    """generate a man page from an optik parser"""
    formatter = ManHelpFormatter()
    print >> stream, formatter.format_head(optparser, pkginfo, section)
    print >> stream, optparser.format_option_help(formatter)
    print >> stream, formatter.format_tail(pkginfo)

