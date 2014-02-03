# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007-2009 CollabNet.  All rights reserved.
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

"""Write file contents to a stream of git-fast-import blobs."""

from cvs2svn_lib import config
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.revision_manager import RevisionCollector
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.artifact_manager import artifact_manager


class GitRevisionCollector(RevisionCollector):
  """Output file revisions to git-fast-import."""

  def __init__(self, revision_reader, blob_filename=None):
    self.revision_reader = revision_reader
    self.blob_filename = blob_filename

  def register_artifacts(self, which_pass):
    self.revision_reader.register_artifacts(which_pass)
    if self.blob_filename is None:
      artifact_manager.register_temp_file(
        config.GIT_BLOB_DATAFILE, which_pass,
        )

  def start(self):
    self.revision_reader.start()
    if self.blob_filename is None:
      self.dump_file = open(
          artifact_manager.get_temp_file(config.GIT_BLOB_DATAFILE), 'wb',
          )
    else:
      self.dump_file = open(self.blob_filename, 'wb')
    self._mark_generator = KeyGenerator()

  def _process_revision(self, cvs_rev):
    """Write the revision fulltext to a blob if it is not dead."""

    if isinstance(cvs_rev, CVSRevisionDelete):
      # There is no need to record a delete revision, and its token
      # will never be needed:
      return

    # FIXME: We have to decide what to do about keyword substitution
    # and eol_style here:
    fulltext = self.revision_reader.get_content(cvs_rev)

    mark = self._mark_generator.gen_id()
    self.dump_file.write('blob\n')
    self.dump_file.write('mark :%d\n' % (mark,))
    self.dump_file.write('data %d\n' % (len(fulltext),))
    self.dump_file.write(fulltext)
    self.dump_file.write('\n')
    cvs_rev.revision_reader_token = mark

  def _process_symbol(self, cvs_symbol, cvs_file_items):
    """Record the original source of CVS_SYMBOL.

    Determine the original revision source of CVS_SYMBOL, and store it
    as the symbol's revision_reader_token."""

    cvs_source = cvs_symbol.get_cvs_revision_source(cvs_file_items)
    cvs_symbol.revision_reader_token = cvs_source.revision_reader_token

  def process_file(self, cvs_file_items):
    for lod_items in cvs_file_items.iter_lods():
      for cvs_rev in lod_items.cvs_revisions:
        self._process_revision(cvs_rev)

    # Now that all CVSRevisions' revision_reader_tokens are set,
    # iterate through symbols and set their tokens to those of their
    # original source revisions:
    for lod_items in cvs_file_items.iter_lods():
      if lod_items.cvs_branch is not None:
        self._process_symbol(lod_items.cvs_branch, cvs_file_items)
      for cvs_tag in lod_items.cvs_tags:
        self._process_symbol(cvs_tag, cvs_file_items)

  def finish(self):
    self.revision_reader.finish()
    self.dump_file.close()


