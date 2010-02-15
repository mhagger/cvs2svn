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

import itertools

from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.fulltext_revision_recorder import FulltextRevisionRecorder
from cvs2svn_lib.key_generator import KeyGenerator


class GitRevisionRecorder(FulltextRevisionRecorder):
  """Output file revisions to git-fast-import."""

  def __init__(self, blob_filename):
    self.blob_filename = blob_filename

  def start(self):
    self.dump_file = open(self.blob_filename, 'wb')
    self._mark_generator = KeyGenerator()

  def record_fulltext(self, cvs_rev, log, fulltext):
    """Write the revision fulltext to a blob if it is not dead."""

    if isinstance(cvs_rev, CVSRevisionDelete):
      # There is no need to record a delete revision, and its token
      # will never be needed:
      return None

    mark = self._mark_generator.gen_id()
    self.dump_file.write('blob\n')
    self.dump_file.write('mark :%d\n' % (mark,))
    self.dump_file.write('data %d\n' % (len(fulltext),))
    self.dump_file.write(fulltext)
    self.dump_file.write('\n')
    return mark

  def finish_file(self, cvs_file_items):
    # Determine the original source of each CVSSymbol, and store it as
    # the symbol's revision_recorder_token.
    for cvs_item in cvs_file_items.values():
      if isinstance(cvs_item, CVSSymbol):
        cvs_source = cvs_item.get_cvs_revision_source(cvs_file_items)
        cvs_item.revision_recorder_token = cvs_source.revision_recorder_token

  def finish(self):
    self.dump_file.close()


