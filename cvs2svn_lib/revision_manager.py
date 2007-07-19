# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

"""This module describes the interface to the CVS repository."""


import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.process import check_command_runs
from cvs2svn_lib.process import PipeStream
from cvs2svn_lib.process import CommandFailedException


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

  def start_file(self, cvs_file_items):
    """Prepare to receive data for the file with the specified CVS_FILE_ITEMS.

    CVS_FILE_ITEMS is an instance of CVSFileItems describing the file
    dependency topology right after the file tree was parsed out of
    the RCS file.  (I.e., it reflects the original CVS dependency
    structure.)  Please note that the CVSFileItems instance will be
    changed later."""

    raise NotImplementedError()

  def record_text(self, cvs_rev, log, text):
    """Record information about a revision and optionally return a token.

    CVS_REV is a CVSRevision instance describing a revision that has
    log message LOG and text TEXT (as retrieved from the RCS file).
    (TEXT is full text for the HEAD revision, and deltas for other
    revisions.)"""

    raise NotImplementedError()

  def finish_file(self, cvs_file_items):
    """The current file is finished; finish and clean up.

    CVS_FILE_ITEMS is a CVSFileItems instance describing the file's
    items at the end of processing of the RCS file in CollectRevsPass.
    It may be modified relative to the CVS_FILE_ITEMS instance passed
    to the corresponding start_file() call (revisions might be
    deleted, topology changed, etc)."""

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

  def start_file(self, cvs_file_items):
    pass

  def record_text(self, cvs_rev, log, text):
    return None

  def finish_file(self, cvs_file_items):
    pass

  def finish(self):
    pass


class RevisionExcluder:
  """An interface for informing a RevisionReader about excluded revisions.

  Currently, revisions can be excluded via the --exclude option and
  various fixups for CVS peculiarities.  This interface can be used to
  inform the associated RevisionReader about CVSItems that are being
  excluded.  (The recorder might use that information to free some
  temporary data or adjust its expectations about which revisions will
  later be read.)"""

  def __init__(self):
    """Initialize the RevisionExcluder.

    Please note that a RevisionExcluder is instantiated in every
    program run, even if the branch-exclusion pass will not be
    executed.  (This is to allow its register_artifacts() method to be
    called.)  Therefore, the __init__() method should not do much, and
    more substantial preparation for use (like actually creating the
    artifacts) should be done in start()."""

    pass

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed during branch exclusion.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    raise NotImplementedError()

  def start(self):
    """Prepare to handle branch exclusions."""

    raise NotImplementedError()

  def process_file(self, cvs_file_items):
    """Called for files whose trees were modified in FilterSymbolsPass.

    This callback is called once for each CVSFile whose topology was
    modified in FilterSymbolsPass."""

    raise NotImplementedError()

  def skip_file(self, cvs_file):
    """Called when a file's dependency topology didn't have to be changed."""

    raise NotImplementedError()

  def finish(self):
    """Called after all branch exclusions for all files are done."""

    raise NotImplementedError()


class NullRevisionExcluder(RevisionExcluder):
  """A do-nothing variety of RevisionExcluder."""

  def register_artifacts(self, which_pass):
    pass

  def start(self):
    pass

  def process_file(self, cvs_file_items):
    pass

  def skip_file(self, cvs_file):
    pass

  def finish(self):
    pass


class RevisionReader(object):
  """An object that can read the contents of CVSRevisions."""

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed during branch exclusion.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    raise NotImplementedError()

  def start(self):
    """Prepare for calls to get_content_stream."""

    raise NotImplementedError

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    """Return a file-like object from which the contents of CVS_REV
    can be read.

    CVS_REV is a CVSRevision.  If SUPPRESS_KEYWORD_SUBSTITUTION is
    True, then suppress the substitution of RCS/CVS keywords in the
    output."""

    raise NotImplementedError

  def skip_content(self, cvs_rev):
    """Inform the reader that CVS_REV would be fetched now, but isn't
    actually needed.

    This may be used for internal housekeeping.
    Note that this is not called for CVSRevisionDelete revisions."""

    raise NotImplementedError

  def finish(self):
    """Inform the reader that all calls to get_content_stream are done.
    Start may be called again at a later point."""

    raise NotImplementedError


