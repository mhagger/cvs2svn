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

"""This module provides an interface for being informed about exclusions.

Currently, revisions can be excluded one branch at a time via the
--exclude option.  This interface can be used to inform revision
recorders about branches that are being excluded.  (The recorder might
use that information to reduce the amount of temporary data that is
collected.)"""


class RevisionExcluder:
  """An interface for being informed about excluded revisions."""

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

  def exclude_tag(self, cvs_tag):
    """CVS_TAG is being excluded from CVS_FILE.

    This callback is called once for each tag that is to be excluded
    for CVS_FILE.  This method is called before CVS_TAG has been
    extracted from the dependencies graph."""

    raise NotImplementedError()

  def exclude_branch(self, cvs_branch, cvs_revisions):
    """CVS_BRANCH is being excluded from CVS_FILE.

    This callback is called once for each branch that is to be
    excluded for CVS_FILE.  CVS_BRANCH is the CVSBranch object for the
    branch that is being excluded.  CVS_REVISIONS is a list of
    CVSRevisions on that branch, ordered by increasing revision number.
    Callbacks are always called in the following sequence:

        revision_excluder.start()
        for cvs_file in files_with_excluded_branches:
          for ...:
            revision_excluder.exclude_tag(cvs_tag)
            revision_excluder.exclude_branch(cvs_branch, cvs_revisions)
          revision_excluder.finish_file()
        revision_excluder.finish()

    Moreover, the callback is called for branches in order from leaves
    towards trunk; this guarantees that a branch has no sub-branches
    by the time it is excluded.  This method is called before
    CVS_BRANCH has been extracted from the dependencies graph."""

    raise NotImplementedError()

  def finish_file(self, cvs_file_items):
    """Called after all branches have been excluded from CVS_FILE.

    This callback is called once for each CVSFile from which branches
    had to be excluded.  It is called after all exclude_tag() and
    exclude_branch() calls for that file."""

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

  def exclude_tag(self, cvs_tag):
    pass

  def exclude_branch(self, cvs_branch, cvs_revisions):
    pass

  def finish_file(self, cvs_file_items):
    pass

  def skip_file(self, cvs_file):
    pass

  def finish(self):
    pass


