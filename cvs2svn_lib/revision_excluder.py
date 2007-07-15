# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2007 CollabNet.  All rights reserved.
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


