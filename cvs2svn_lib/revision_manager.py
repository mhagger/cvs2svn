# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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


class RevisionCollector(object):
  """Optionally collect revision information for CVS files."""

  def __init__(self):
    """Initialize the RevisionCollector.

    Please note that a RevisionCollector is instantiated in every
    program run, even if the data-collection pass will not be
    executed.  (This is to allow it to register the artifacts that it
    produces.)  Therefore, the __init__() method should not do much,
    and more substantial preparation for use (like actually creating
    the artifacts) should be done in start()."""

    pass

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed while collecting data.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    pass

  def start(self):
    """Data will soon start being collected.

    Any non-idempotent initialization should be done here."""

    pass

  def process_file(self, cvs_file_items):
    """Collect data for the file described by CVS_FILE_ITEMS.

    CVS_FILE_ITEMS has already been transformed into the logical
    representation of the file's history as it should be output.
    Therefore it is not necessarily identical to the history as
    recorded in the RCS file."""

    raise NotImplementedError()

  def finish(self):
    """All recording is done; clean up."""

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

    pass

  def start(self):
    """Prepare to handle branch exclusions."""

    pass

  def process_file(self, cvs_file_items):
    """Called for files whose trees were modified in FilterSymbolsPass.

    This callback is called once for each CVSFile whose topology was
    modified in FilterSymbolsPass."""

    raise NotImplementedError()

  def finish(self):
    """Called after all branch exclusions for all files are done."""

    pass


class NullRevisionExcluder(RevisionExcluder):
  """A do-nothing variety of RevisionExcluder."""

  def process_file(self, cvs_file_items):
    pass


class RevisionReader(object):
  """An object that can read the contents of CVSRevisions."""

  def register_artifacts(self, which_pass):
    """Register artifacts that will be needed during branch exclusion.

    WHICH_PASS is the pass that will call our callbacks, so it should
    be used to do the registering (e.g., call
    WHICH_PASS.register_temp_file() and/or
    WHICH_PASS.register_temp_file_needed())."""

    pass

  def start(self):
    """Prepare for calls to get_content_stream."""

    pass

  def get_content_stream(self, cvs_rev, suppress_keyword_substitution=False):
    """Return a file-like object from which the contents of CVS_REV
    can be read.

    CVS_REV is a CVSRevision.  If SUPPRESS_KEYWORD_SUBSTITUTION is
    True, then suppress the substitution of RCS/CVS keywords in the
    output."""

    raise NotImplementedError

  def finish(self):
    """Inform the reader that all calls to get_content_stream are done.
    Start may be called again at a later point."""

    pass


