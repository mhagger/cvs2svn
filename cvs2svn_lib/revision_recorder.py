# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006 CollabNet.  All rights reserved.
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

"""This module provides objects that can record CVS revision contents."""


class RevisionRecorder:
  """An object that can record text and deltas from CVS files."""

  def start_file(self, cvs_file):
    """Prepare to receive data for the specified file.

    CVS_FILE is an instance of CVSFile."""

    raise NotImplementedError()

  def record_text(self, revision_data, log, text):
    """Record information about a revision and optionally return a token.

    REVISION_DATA is an instance of collect_data._RevisionData.  LOG
    and TEXT are the log message and text (either full text or deltas)
    for that revision."""

    raise NotImplementedError()

  def finish_file(self):
    """The current file is finished; clean up."""

    raise NotImplementedError()

  def finish(self):
    """Finish up any cleanup related to the previous file."""

    raise NotImplementedError()


class NullRevisionRecorder(RevisionRecorder):
  """A do-nothing variety of RevisionRecorder."""

  def start_file(self, cvs_file):
    pass

  def record_text(self, revision_data, log, text):
    return None

  def finish_file(self):
    pass

  def finish(self):
    pass


class FullTextRevisionRecorder(RevisionRecorder):
  """A RevisionRecorder that reconstructs the full text internally."""

  def start_file(self, cvs_file):
    # TODO: Implement
    raise NotImplementedError()

  def record_text(self, revision_data, log, text):
    """Reconstruct the full text then call self.record_full_text()."""

    # TODO: Implement
    raise NotImplementedError()
    #return self.record_full_text(revision_data, log, full_text)

  def finish_file(self):
    # TODO: Implement
    raise NotImplementedError()

  def finish(self):
    # TODO: Implement
    raise NotImplementedError()

  def record_full_text(self, revision_data, log, full_text):
    """Record information about a revision.

    Like RevisionRecorder.record_text(), except that the file's
    FULL_TEXT (i.e., reconstructed from deltas) is provided.

    This method should be defined by derived classes."""

    raise NotImplementedError()


