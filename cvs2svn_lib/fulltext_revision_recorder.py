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

"""An abstract class that contructs file contents during CollectRevsPass.

It calls its record_fulltext() method with the full text of every
revision.  This method should be overridden to do something with the
fulltext and possibly return a revision_recorder_token."""


from cvs2svn_lib.revision_manager import RevisionRecorder


class FulltextRevisionRecorder:
  """Similar to a RevisionRecorder, but it requires the fulltext."""

  def register_artifacts(self, which_pass):
    pass

  def start(self):
    pass

  def start_file(self, cvs_file_items):
    pass

  def record_fulltext(self, cvs_rev, log, fulltext):
    """Record the fulltext for CVS_REV.

    CVS_REV has the log message LOG and the fulltext FULLTEXT.  This
    method should be overridden to do something sensible with them."""

    raise NotImplementedError()

  def finish_file(self, cvs_file_items):
    pass

  def finish(self):
    pass


class FulltextRevisionRecorderAdapter(RevisionRecorder):
  """Reconstruct the fulltext and pass it to a FulltextRevisionRecorder.

  This class implements RevisionRecorder (so it can be passed directly
  to CollectRevsPass).  But it doesn't actually record anything.
  Instead, it reconstructs the fulltext of each revision, and passes
  the fulltext to a fulltext_revision_recorder."""

  def __init__(self, fulltext_revision_recorder):
    RevisionRecorder.__init__(self)
    self.fulltext_revision_recorder = fulltext_revision_recorder

  def register_artifacts(self, which_pass):
    self.fulltext_revision_recorder.register_artifacts(which_pass)

  def start(self):
    self.fulltext_revision_recorder.start()

  def start_file(self, cvs_file_items):
    self.fulltext_revision_recorder.start_file(cvs_file_items)

  def record_text(self, cvs_rev, log, text):
    """This method should be overwridden.

    It should determine the fulltext of CVS_REV, then pass it to
    self.fulltext_revision_recorder.record_fulltext() and return the
    result."""

    raise NotImplementedError()

  def finish_file(self, cvs_file_items):
    self.fulltext_revision_recorder.finish_file(cvs_file_items)

  def finish(self):
    self.fulltext_revision_recorder.finish()


class SimpleFulltextRevisionRecorderAdapter(FulltextRevisionRecorderAdapter):
  """Reconstruct the fulltext using a RevisionReader.

  To create the fulltext, this class simply uses a RevisionReader (for
  example, RCSRevisionReader or CVSRevisionReader).  This is not quite
  as wasteful as using one of these RevisionReaders in OutputPass,
  because the same RCS file will be read over and over (and so
  presumably stay in the disk cache).  But it is still pretty silly,
  considering that we have all the RCS deltas available to us."""

  def __init__(self, revision_reader, fulltext_revision_recorder):
    FulltextRevisionRecorderAdapter.__init__(self, fulltext_revision_recorder)
    self.revision_reader = revision_reader

  def register_artifacts(self, which_pass):
    FulltextRevisionRecorderAdapter.register_artifacts(self, which_pass)
    self.revision_reader.register_artifacts(which_pass)

  def start(self):
    FulltextRevisionRecorderAdapter.start(self)
    self.revision_reader.start()

  def record_text(self, cvs_rev, log, text):
    # FIXME: We have to decide what to do about keyword substitution
    # and eol_style here:
    fulltext = self.revision_reader.get_content_stream(
        cvs_rev, suppress_keyword_substitution=False
        ).read()
    return self.fulltext_revision_recorder.record_fulltext(
        cvs_rev, log, fulltext
        )

  def finish(self):
    FulltextRevisionRecorderAdapter.finish(self)
    self.revision_reader.finish()


