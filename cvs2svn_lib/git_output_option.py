# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007 CollabNet.  All rights reserved.
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

"""Classes for outputting the converted repository to git."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.cvs_item import CVSRevisionModification
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.output_option import OutputOption


class GitOutputOption(OutputOption):
  """An OutputOption that outputs to a git-fast-import formatted file."""

  def __init__(self, dump_filename):
    # The file to which to write the git-fast-import commands:
    self.dump_filename = dump_filename

  def register_artifacts(self, which_pass):
    # These artifacts are needed for SymbolingsReader:
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OPENINGS_CLOSINGS_SORTED, which_pass
        )
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OFFSETS_DB, which_pass
        )

  def check(self):
    Log().warn('!!!!! WARNING: Git output is highly experimental !!!!!')
    if not Ctx().trunk_only:
      raise FatalError(
          'Git output is currently only supported with --trunk-only'
          )

  def setup(self, svn_rev_count):
    self._symbolings_reader = SymbolingsReader()
    self.f = open(self.dump_filename, 'wb')

  def process_initial_project_commit(self, svn_commit):
    pass

  def process_primary_commit(self, svn_commit):
    author = svn_commit.get_author()
    try:
      author = Ctx().utf8_encoder(author)
    except UnicodeError:
      Log().warn('%s: problem encoding author:' % warning_prefix)
      Log().warn("  author: '%s'" % (author,))

    log_msg = svn_commit.get_log_msg()
    try:
      log_msg = Ctx().utf8_encoder(log_msg)
    except UnicodeError:
      Log().warn('%s: problem encoding log message:' % warning_prefix)
      Log().warn("  log:    '%s'" % log_msg.rstrip())

    # FIXME: is this correct?:
    self.f.write('commit refs/heads/master\n')
    self.f.write(
        'committer %s <%s> %d +0000\n' % (author, author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))
    for cvs_rev in svn_commit.get_cvs_items():
      if isinstance(cvs_rev, CVSRevisionNoop):
        pass

      elif isinstance(cvs_rev, CVSRevisionDelete):
        self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

      elif isinstance(cvs_rev, CVSRevisionModification):
        if cvs_rev.cvs_file.executable:
          mode = '100755'
        else:
          mode = '100644'

        self.f.write(
            'M %s :%d %s\n'
            % (mode, cvs_rev.revision_recorder_token,
               cvs_rev.cvs_file.cvs_path,)
            )

    self.f.write('\n')

  def process_post_commit(self, svn_commit):
    pass

  def process_branch_commit(self, svn_commit):
    pass

  def process_tag_commit(self, svn_commit):
    pass

  def cleanup(self):
    self.f.close()
    del self.f
    self._symbolings_reader.close()
    del self._symbolings_reader


