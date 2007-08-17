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

"""An abstract class that contructs file contents during CollectRevsPass.

It calls its record_fulltext() method with the full text of every
revision.  This method should be overwritten to do something with the
fulltext and possibly return a revision_recorder_token."""


from __future__ import generators

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.cvs_item import CVSRevision
from cvs2svn_lib.cvs_item import CVSRevisionAbsent
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
    """Return the first CVSRevision with the content of CVS_REV.

    'First' here refers to deltatext order; i.e., the very first
    revision is HEAD on trunk, then backwards to the root of a branch,
    then out to the tip of a branch.

    If there is no other CVSRevision that have the same content,
    return CVS_REV itself."""

    while True:
      if cvs_rev.deltatext_exists:
        return cvs_rev
      if isinstance(cvs_rev.lod, Trunk):
        if cvs_rev.next_id is None:
          # The HEAD revision on trunk is always its own source, even
          # if its deltatext (i.e., its fulltext) is empty:
          return cvs_rev
        else:
          cvs_rev = self._cvs_file_items[cvs_rev.next_id]
      else:
        cvs_rev = self._cvs_file_items[cvs_rev.prev_id]

  def record_fulltext(self, cvs_rev, log, fulltext):
    """Write the fulltext to a blob if it is original.

    To find the 'original' revision, we follow the CVS
    delta-dependency chain backwards until we find a file that has a
    deltatext.  The reason we go to this trouble is to avoid writing
    the same file contents multiple times for a string of revisions
    that don't have deltatexts (as, for example, happens with dead
    revisions and imported revisions)."""

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
        cvs_source = cvs_file_items[cvs_item.source_id]
        while not isinstance(cvs_source, CVSRevision):
          cvs_source = cvs_file_items[cvs_source.source_id]
        cvs_item.revision_recorder_token = cvs_source.revision_recorder_token

    del self._cvs_file_items

  def finish(self):
    self.dump_file.close()


