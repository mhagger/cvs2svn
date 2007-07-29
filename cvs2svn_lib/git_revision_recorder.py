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
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.cvs_item import CVSRevisionAbsent
from cvs2svn_lib.fulltext_revision_recorder import FulltextRevisionRecorder


GIT_BLOB_FILE = 'git-blob.dat'


class GitRevisionRecorder(FulltextRevisionRecorder):
  """Output file revisions to git-fast-import."""

  def register_artifacts(self, which_pass):
    artifact_manager.register_temp_file(GIT_BLOB_FILE, which_pass)

  def start(self):
    self.dump_file = open(artifact_manager.get_temp_file(GIT_BLOB_FILE), 'wb')

  def start_file(self, cvs_file_items):
    self._cvs_file_items = cvs_file_items

  def _get_original_source(self, cvs_rev):
    """Return the id of the first CVSRevision with the content of CVS_REV.

    'First' here refers to deltatext order; i.e., the very first
    revision is HEAD on trunk, then backwards to the root of a branch,
    then out to the tip of a branch.

    If there is no other CVSRevision that have the same content,
    return CVS_REV.id."""

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
      self.dump_file.write('blob\n')
      self.dump_file.write('mark :%d\n' % (cvs_rev.id,))
      self.dump_file.write('data %d\n' % (len(fulltext),))
      self.dump_file.write(fulltext)
      self.dump_file.write('\n')

    # Return as revision_recorder_token the CVSRevision.id of the
    # original source revision:
    return source.id

  def finish_file(self, cvs_file_items):
    del self._cvs_file_items

  def finish(self):
    self.dump_file.close()


