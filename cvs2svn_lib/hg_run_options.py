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

import tempfile

from cvs2svn_lib.context import Ctx
from cvs2svn_lib.run_options import IncompatibleOption
from cvs2svn_lib.dvcs_common import DVCSRunOptions
from cvs2svn_lib.hg_output_option import HgOutputOption


class HgRunOptions(DVCSRunOptions):
  description="""\
Convert a CVS repository into a Mercurial repository, including history.
"""

  short_desc = 'convert a CVS repository into a Mercurial repository'

  synopsis = """\
.B cvs2hg
[\\fIOPTION\\fR]... \\fIOUTPUT-OPTION\\fR [\\fICVS-REPOS-PATH\\fR
.br
.B cvs2hg
[\\fIOPTION\\fR]... \\fI--options=PATH\\fR
"""

  # XXX paragraph 2 copied straight from svn_run_options.py
  long_desc = """\
Create a new Mercurial repository based on the version history stored in
a CVS repository. Each CVS commit will be mirrored in the Mercurial
repository, including commit time and author (with optional remapping to
Mercurial-style long usernames).
.P
\\fICVS-REPOS-PATH\\fR is the filesystem path of the part of the CVS
repository that you want to convert.  It is not possible to convert a
CVS repository to which you only have remote access; see the FAQ for
more information.  This path doesn't have to be the top level
directory of a CVS repository; it can point at a project within a
repository, in which case only that project will be converted.  This
path or one of its parent directories has to contain a subdirectory
called CVSROOT (though the CVSROOT directory can be empty). If
omitted, the repository path defaults to the current directory.
.P
Unlike CVS or Subversion, Mercurial expects each repository to hold
one independent project.  If your CVS repository contains multiple
independent projects, you should probably convert them to multiple
independent Mercurial repositories with multiple runs of
.B cvs2hg.
"""

  # XXX copied from svn_run_options.py
  files = """\
A directory under \\fI%s\\fR (or the directory specified by
\\fB--tmpdir\\fR) is used as scratch space for temporary data files.
""" % (tempfile.gettempdir(),)

  # XXX the cvs2{svn,git,bzr,hg} man pages should probably reference
  # each other
  see_also = [
    ('cvs', '1'),
    ('hg', '1'),
    ]

  DEFAULT_USERNAME = 'cvs2hg'

  def __init__(self, *args, **kwargs):
    # Override some default values
    ctx = Ctx()
    ctx.symbol_commit_message = (
      "artificial changeset to create "
      "%(symbol_type)s '%(symbol_name)s'")
    ctx.post_commit_message = (
      "artificial changeset: compensate for changes in %(revnum)s "
      "(on non-trunk default branch in CVS)")

    DVCSRunOptions.__init__(self, *args, **kwargs)

  # This is a straight copy of SVNRunOptions._get_extraction_options_group();
  # would be nice to refactor, but it's a bit awkward because GitRunOptions
  # doesn't support --use-internal-co option.
  def _get_extraction_options_group(self):
    group = DVCSRunOptions._get_extraction_options_group(self)
    self._add_use_internal_co_option(group)
    self._add_use_cvs_option(group)
    self._add_use_rcs_option(group)
    return group

  def _get_output_options_group(self):
    group = DVCSRunOptions._get_output_options_group(self)

    # XXX what if the hg repo already exists? die, clobber, or append?
    # (currently we die at the start of OutputPass)
    group.add_option(IncompatibleOption(
      '--hgrepos', type='string',
      action='store',
      help='create Mercurial repository in PATH',
      man_help=(
          'Convert to a Mercurial repository in \\fIpath\\fR.  This creates '
          'a new Mercurial repository at \\fIpath\\fR.  \\fIpath\\fR must '
          'not already exist.'
          ),
      metavar='PATH',
      ))

    # XXX --dry-run?

    return group

  def process_extraction_options(self):
    """Process options related to extracting data from the CVS repository."""
    self.process_all_extraction_options()

  def process_output_options(self):
    Ctx().output_option = HgOutputOption(
      self.options.hgrepos,
      author_transforms={},
      )
