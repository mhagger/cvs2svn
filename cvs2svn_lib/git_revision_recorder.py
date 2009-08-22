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

  def start_file(self, cvs_file_items):
    self._cvs_file_items = cvs_file_items

  def _get_original_source(self, cvs_rev):
    """Return the original source of the contents of CVS_REV.

    Return the first non-delete CVSRevision with the same contents as
    CVS_REV.  'First' here refers to deltatext order; i.e., the very
    first revision is HEAD on trunk, then backwards to the root of a
    branch, then out to the tip of a branch.

    The candidates are all revisions along the CVS delta-dependency
    chain until the next one that has a deltatext (inclusive).  Of the
    candidates, CVSRevisionDeletes are disqualified because, even
    though CVS records their contents, it is impossible to extract
    their fulltext using commands like 'cvs checkout -p'.

    If there is no other CVSRevision that has the same content, return
    CVS_REV itself."""

    # Keep track of the "best" source CVSRevision found so far:
    best_source_rev = None

    for cvs_rev in itertools.chain(
          [cvs_rev], self._cvs_file_items.iter_deltatext_ancestors(cvs_rev)
          ):
      if not isinstance(cvs_rev, CVSRevisionDelete):
        best_source_rev = cvs_rev

      if cvs_rev.deltatext_exists:
        break

    return best_source_rev

  def record_fulltext(self, cvs_rev, log, fulltext):
    """Write the fulltext to a blob if it is original and not a delete.

    The reason we go to this trouble is to avoid writing the same file
    contents multiple times for a string of revisions that don't have
    deltatexts (as, for example, happens with dead revisions and
    imported revisions)."""

    if isinstance(cvs_rev, CVSRevisionDelete):
      # There is no need to record a delete revision, and its token
      # will never be needed:
      return None

    source = self._get_original_source(cvs_rev)

    if source.id == cvs_rev.id:
      # Revision is its own source; write it out:
      mark = self._mark_generator.gen_id()
      self.dump_file.write('blob\n')
      self.dump_file.write('mark :%d\n' % (mark,))
      self.dump_file.write('data %d\n' % (len(fulltext),))
      self.dump_file.write(fulltext)
      self.dump_file.write('\n')
      return mark
    else:
      # Return as revision_recorder_token the CVSRevision.id of the
      # original source revision:
      return source.revision_recorder_token

  def finish_file(self, cvs_file_items):
    # Determine the original source of each CVSSymbol, and store it as
    # the symbol's revision_recorder_token.
    for cvs_item in cvs_file_items.values():
      if isinstance(cvs_item, CVSSymbol):
        cvs_source = cvs_item.get_cvs_revision_source(cvs_file_items)
        cvs_item.revision_recorder_token = cvs_source.revision_recorder_token

    del self._cvs_file_items

  def finish(self):
    self.dump_file.close()


