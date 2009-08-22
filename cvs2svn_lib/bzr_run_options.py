# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

"""This module manages cvs2bzr run options."""


import sys
import datetime
import codecs

from cvs2svn_lib.version import VERSION
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.run_options import authors
from cvs2svn_lib.man_writer import ManWriter
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.git_run_options import GitRunOptions
from cvs2svn_lib.git_output_option import GitRevisionInlineWriter
from cvs2svn_lib.git_output_option import GitOutputOption
from cvs2svn_lib.revision_manager import NullRevisionRecorder
from cvs2svn_lib.revision_manager import NullRevisionExcluder


short_desc = 'convert a cvs repository into a Bazaar repository'

synopsis = """\
.B cvs2bzr
[\\fIOPTION\\fR]... \\fIOUTPUT-OPTIONS CVS-REPOS-PATH\\fR
.br
.B cvs2bzr
[\\fIOPTION\\fR]... \\fI--options=PATH\\fR
"""

description="""\
Convert a CVS repository into a Bazaar repository, including history.

"""
long_desc = """\
Create a new Bazaar repository based on the version history stored in a
CVS repository. Each CVS commit will be mirrored in the Bazaar
repository, including such information as date of commit and id of the
committer.
.P
The output of this program is a "fast-import dumpfile", which
can be loaded into a Bazaar repository using the Bazaar FastImport
Plugin, available from https://launchpad.net/bzr-fastimport.

.P
\\fICVS-REPOS-PATH\\fR is the filesystem path of the part of the CVS
repository that you want to convert.  This path doesn't have to be the
top level directory of a CVS repository; it can point at a project
within a repository, in which case only that project will be
converted.  This path or one of its parent directories has to contain
a subdirectory called CVSROOT (though the CVSROOT directory can be
empty).
.P
It is not possible directly to convert a CVS repository to which you
only have remote access, but the FAQ describes tools that may be used
to create a local copy of a remote CVS repository.
"""

files = """\
A directory called \\fIcvs2svn-tmp\\fR (or the directory specified by
\\fB--tmpdir\\fR) is used as scratch space for temporary data files.
"""

see_also = [
  ('cvs', '1'),
  ('bzr', '1'),
  ]


class BzrRunOptions(GitRunOptions):

  def get_description(self):
    return description

  def _get_output_options_group(self):
    group = RunOptions._get_output_options_group(self)

    group.add_option(IncompatibleOption(
        '--dumpfile', type='string',
        action='store',
        help='path to which the data should be written',
        man_help=(
            'Write the blobs and revision data to \\fIpath\\fR.'
            ),
        metavar='PATH',
        ))
    group.add_option(ContextOption(
        '--dry-run',
        action='store_true',
        help=(
            'do not create any output; just print what would happen.'
            ),
        man_help=(
            'Do not create any output; just print what would happen.'
            ),
        ))

    return group

  def callback_manpage(self, option, opt_str, value, parser):
    f = codecs.getwriter('utf_8')(sys.stdout)
    ManWriter(
        parser,
        section='1',
        date=datetime.date.today(),
        source='Version %s' % (VERSION,),
        manual='User Commands',
        short_desc=short_desc,
        synopsis=synopsis,
        long_desc=long_desc,
        files=files,
        authors=authors,
        see_also=see_also,
        ).write_manpage(f)
    sys.exit(0)

  def process_io_options(self):
    """Process input/output options.

    Process options related to extracting data from the CVS repository
    and writing to a Bazaar-friendly fast-import file."""

    ctx = Ctx()
    options = self.options

    not_both(options.use_rcs, '--use-rcs',
             options.use_cvs, '--use-cvs')

    if options.use_rcs:
      revision_reader = RCSRevisionReader(
          co_executable=options.co_executable
          )
    else:
      # --use-cvs is the default:
      revision_reader = CVSRevisionReader(
          cvs_executable=options.cvs_executable
          )

    if not ctx.dry_run and not options.dumpfile:
      raise FatalError("must pass '--dry-run' or '--dumpfile' option.")

    ctx.revision_recorder = NullRevisionRecorder()
    ctx.revision_excluder = NullRevisionExcluder()
    ctx.revision_reader = None

    ctx.output_option = GitOutputOption(
        options.dumpfile,
        GitRevisionInlineWriter(revision_reader),
        max_merges=None,
        # Optional map from CVS author names to bzr author names:
        author_transforms={}, # FIXME
        )


