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

  def __init__(self):
    """Initialize the RevisionRecorder.

    Please note that a RevisionRecorder is instantiated in every
    program run, even if the data-collection pass will not be
    executed.  (This is to allow it to register the artifacts that it
    produces.)  Therefore, the __init__() method should not do much,
    and more substantial preparation for use (like actually creating
    the artifacts) should be done in start()."""

    pass

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed during data recording.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    raise NotImplementedError()

  def start(self):
    """Data will soon start being collected.

    Any non-idempotent initialization should be done here."""

    raise NotImplementedError()

  def start_file(self, cvs_file):
    """Prepare to receive data for the specified file.

    CVS_FILE is an instance of CVSFile."""

    raise NotImplementedError()

  def record_text(self, revisions_data, revision, log, text):
    """Record information about a revision and optionally return a token.

    REVISIONS_DATA is a map { rev : _RevisionData } containing
    collect_data._RevisionData instances for all revisions in this
    file.  REVISION is the revision number of the current revision.
    LOG and TEXT are the log message and text (as retrieved from the
    RCS file) for that revision.  (TEXT is full text for the HEAD
    revision, and deltas for other revisions.)"""

    raise NotImplementedError()

  def finish_file(self, revisions_data, root_rev):
    """The current file is finished; finish and clean up.

    REVISIONS_DATA is a map { rev : _RevisionData } containing
    _RevisionData instances for all revisions in this file.  ROOT_REV
    is the revision number of the revision that is the root of the
    dependency tree (usually '1.1')."""

    raise NotImplementedError()

  def finish(self):
    """All recording is done; clean up."""

    raise NotImplementedError()


class NullRevisionRecorder(RevisionRecorder):
  """A do-nothing variety of RevisionRecorder."""

  def register_artifacts(self, which_pass):
    pass

  def start(self):
    pass

  def start_file(self, cvs_file):
    pass

  def record_text(self, revisions_data, revision, log, text):
    return None

  def finish_file(self, revisions_data, root_rev):
    pass

  def finish(self):
    pass


class FullTextRevisionRecorder(RevisionRecorder):
  """A RevisionRecorder that reconstructs the full text internally."""

  def register_artifacts(self, which_pass):
    # TODO: Implement
    raise NotImplementedError()

  def start(self):
    # TODO: Implement
    raise NotImplementedError()

  def start_file(self, cvs_file):
    # TODO: Implement
    raise NotImplementedError()

  def record_text(self, revisions_data, revision, log, text):
    """Reconstruct the full text then call self.record_full_text()."""

    # TODO: Implement
    raise NotImplementedError()
    #return self.record_full_text(revision_data, log, full_text)

  def finish_file(self, revisions_data, root_rev):
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


