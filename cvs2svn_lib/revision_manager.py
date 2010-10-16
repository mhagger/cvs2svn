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
    recorded in the RCS file.

    This method is allowed to store a pickleable object to the
    CVSItem.revision_reader_token member of CVSItems in
    CVS_FILE_ITEMS.  These data are stored with the items and
    available for the use of the RevisionReader."""

    raise NotImplementedError()

  def finish(self):
    """All recording is done; clean up."""

    pass


class NullRevisionCollector(RevisionCollector):
  """A do-nothing variety of RevisionCollector."""

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
    """Prepare for calls to get_content()."""

    pass

  def get_content(self, cvs_rev):
    """Return the contents of CVS_REV.

    CVS_REV is a CVSRevision.  The way that the contents are extracted
    is influenced by properties that are set on CVS_REV:

    * The CVS_REV property _keyword_handling specifies how RCS/CVS
      keywords should be handled:

      * 'collapsed' -- collapse RCS/CVS keywords in the output; e.g.,
        '$Author: jrandom $' -> '$Author$'.

      * 'expanded' -- expand RCS/CVS keywords in the output; e.g.,
        '$Author$' -> '$Author: jrandom $'.

      * 'untouched' -- leave RCS/CVS keywords untouched.  For a file
        that had keyword expansion enabled in CVS, this typically
        means that the keyword comes out expanded as for the
        *previous* revision, because CVS expands keywords on checkout,
        not checkin.

      * unset -- undefined behavior; depends on which revision manager
        is being used.

    * The CVS_REV property _eol_fix specifies how EOL sequences should
      be handled in the output.  If the property is unset or empty,
      then leave EOL sequences untouched.  If it is non-empty, then
      convert all end-of-line sequences to the value of that property
      (typically '\n' or '\r\n').

    See doc/properties.txt and doc/text-transformations.txt for more
    information.

    If Ctx().decode_apple_single is set, then extract the data fork
    from any content that looks like AppleSingle format."""

    raise NotImplementedError()

  def finish(self):
    """Inform the reader that all calls to get_content() are done.

    Start may be called again at a later point."""

    pass


