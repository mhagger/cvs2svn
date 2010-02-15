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

"""This module manages cvs2git run options."""


import sys
import datetime
import codecs

from cvs2svn_lib.version import VERSION
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.dvcs_common import DVCSRunOptions
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.run_options import ContextOption
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.run_options import not_both
from cvs2svn_lib.man_writer import ManWriter
from cvs2svn_lib.revision_manager import NullRevisionCollector
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.git_revision_recorder import GitRevisionCollector
from cvs2svn_lib.git_output_option import GitRevisionMarkWriter
from cvs2svn_lib.git_output_option import GitOutputOption


class GitRunOptions(DVCSRunOptions):

  short_desc = 'convert a cvs repository into a git repository'

  synopsis = """\
.B cvs2git
[\\fIOPTION\\fR]... \\fIOUTPUT-OPTIONS CVS-REPOS-PATH\\fR
.br
.B cvs2git
[\\fIOPTION\\fR]... \\fI--options=PATH\\fR
"""

  long_desc = """\
Create a new git repository based on the version history stored in a
CVS repository. Each CVS commit will be mirrored in the git
repository, including such information as date of commit and id of the
committer.
.P
The output of this program are a "blobfile" and a "dumpfile", which
together can be loaded into a git repository using "git fast-import".
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
    ('git', '1'),
    ('git-fast-import', '1'),
    ]


  def _get_output_options_group(self):
    group = super(GitRunOptions, self)._get_output_options_group()

    group.add_option(IncompatibleOption(
        '--blobfile', type='string',
        action='store',
        help='path to which the "blob" data should be written',
        man_help=(
            'Write the "blob" data (containing revision contents) to '
            '\\fIpath\\fR.'
            ),
        metavar='PATH',
        ))
    group.add_option(IncompatibleOption(
        '--dumpfile', type='string',
        action='store',
        help='path to which the revision data should be written',
        man_help=(
            'Write the revision data (branches and commits) to \\fIpath\\fR.'
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

  def _get_extraction_options_group(self):
    group = super(GitRunOptions, self)._get_extraction_options_group()
    self._add_use_cvs_option(group)
    self._add_use_rcs_option(group)
    return group

  # XXX not quite the same as same method in SVNRunOptions, but it
  # probably should be
  def process_extraction_options(self):
    """Process options related to extracting data from the CVS
    repository."""
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

    if ctx.dry_run:
      ctx.revision_collector = NullRevisionCollector()
    else:
      if not (options.blobfile and options.dumpfile):
        raise FatalError("must pass '--blobfile' and '--dumpfile' options.")
      ctx.revision_collector = GitRevisionCollector(
          options.blobfile, revision_reader,
          )

    ctx.revision_reader = None

  def process_output_options(self):
    """Process options related to fastimport output."""
    ctx = Ctx()
    ctx.output_option = GitOutputOption(
        self.options.dumpfile,
        GitRevisionMarkWriter(),
        # Optional map from CVS author names to git author names:
        author_transforms={}, # FIXME
        )
