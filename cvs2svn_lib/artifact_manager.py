# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
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

"""This module manages the artifacts produced by conversion passes."""


import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log


class Artifact:
  """An artifact that can be created, used across cvs2svn passes, then
  cleaned up."""

  def __init__(self, name):
    self.name = name

    # A map { which_pass : None } of passes that need this artifact.
    # This field is maintained by ArtifactManager.
    self._passes_needed = { }

  def cleanup(self):
    """This artifact is no longer needed; clean it up."""

    pass

  def __str__(self):
    return self.name


class TempFileArtifact(Artifact):
  """A temporary file that can be used across cvs2svn passes."""

  def __init__(self, basename):
    Artifact.__init__(self, basename)
    self.filename = Ctx().get_temp_filename(basename)

  def cleanup(self):
    Log().verbose("Deleting", self.filename)
    os.unlink(self.filename)


class ArtifactManager:
  """Manager artifacts that are created by one pass but needed by others.

  This class is responsible for cleaning up artifacts once they are no
  longer needed.  The trick is that cvs2svn can be run pass by pass,
  so not all passes might be executed during a specific program run.

  To use this class:

  - Call register_artifact() or register_temp_file() for all possible
    artifacts (even those that should have been created by previous
    cvs2svn runs).

  - Call register_artifact_needed() or register_temp_file_needed() for
    any artifact that are needed by any pass (even those passes that
    won't be executed during this cvs2svn run).

  Then, in pass order:

  - Call pass_skipped() for any passes that were already executed
    during a previous cvs2svn run.

  - Call pass_started() when a pass is about to start execution.

  - If a pass that has been started will be continued during the next
    program run, then call pass_continued().

  - If a pass that has been started finishes execution, call
    pass_done(), to allow any artifacts that won't be needed anymore
    to be cleaned up.

  - Call pass_deferred() for any passes that have been deferred to a
    future cvs2svn run.

  Finally:

  - Call check_clean() to verify that all artifacts have been
    accounted for."""

  def __init__(self):
    # A map { artifact_name : artifact } of known artifacts.
    self._artifacts = { }

    # A map { pass : set_of_artifacts }, where set_of_artifacts is a
    # map { artifact : None } of artifacts needed by the pass.
    self._pass_needs = { }

    # A set { pass : None } of passes that are currently being
    # executed.
    self._active_passes = { }

  def register_artifact(self, artifact, which_pass):
    """Register a new ARTIFACT for management by this class.
    WHICH_PASS is the pass that creates ARTIFACT, and is also assumed
    to need it.  It is an error to registier the same artifact more
    than once."""

    assert artifact.name not in self._artifacts
    self._artifacts[artifact.name] = artifact
    self.register_artifact_needed(artifact.name, which_pass)

  def register_temp_file(self, basename, which_pass):
    """Register a temporary file with base name BASENAME as an
    artifact.  Return the filename of the temporary file."""

    artifact = TempFileArtifact(basename)
    self.register_artifact(artifact, which_pass)
    return artifact.filename

  def get_artifact(self, artifact_name):
    """Return the artifact with the specified name.  If the artifact
    does not currently exist, raise a KeyError."""

    return self._artifacts[artifact_name]

  def get_temp_file(self, basename):
    """Return the filename of the temporary file with the specified BASENAME.

    If the temporary file is not an existing, registered
    TempFileArtifact, raise a KeyError."""

    return self.get_artifact(basename).filename

  def register_artifact_needed(self, artifact_name, which_pass):
    """Register that WHICH_PASS needs the artifact named ARTIFACT_NAME.
    An artifact with this name must already have been registered."""

    artifact = self.get_artifact(artifact_name)
    artifact._passes_needed[which_pass] = None
    self._pass_needs.setdefault(which_pass, {})[artifact] = None

  def register_temp_file_needed(self, basename, which_pass):
    """Register that the temporary file with base name BASENAME is
    needed by WHICH_PASS."""

    self.register_artifact_needed(basename, which_pass)

  def _unregister_artifacts(self, which_pass):
    """Unregister any artifacts that were needed for WHICH_PASS.

    Return a list of artifacts that are no longer needed at all."""

    try:
      artifacts = self._pass_needs[which_pass].keys()
    except KeyError:
      # No artifacts were needed for that pass:
      return []

    del self._pass_needs[which_pass]

    unneeded_artifacts = []
    for artifact in artifacts:
      del artifact._passes_needed[which_pass]
      if not artifact._passes_needed:
        del self._artifacts[artifact.name]
        unneeded_artifacts.append(artifact)

    return unneeded_artifacts

  def pass_skipped(self, which_pass):
    """WHICH_PASS was executed during a previous cvs2svn run.

    Its artifacts were created then, and any artifacts that would
    normally be cleaned up after this pass have already been cleaned
    up."""

    self._unregister_artifacts(which_pass)

  def pass_started(self, which_pass):
    """WHICH_PASS is starting."""

    self._active_passes[which_pass] = None

  def pass_continued(self, which_pass):
    """WHICH_PASS, which has already been started, will be continued
    during the next program run.  Unregister any artifacts that would
    be cleaned up at the end of WHICH_PASS without actually cleaning
    them up."""

    del self._active_passes[which_pass]
    self._unregister_artifacts(which_pass)

  def pass_done(self, which_pass):
    """WHICH_PASS is done.  Clean up all artifacts that are no longer
    needed."""

    del self._active_passes[which_pass]
    artifacts = self._unregister_artifacts(which_pass)
    if not Ctx().skip_cleanup:
      for artifact in artifacts:
        artifact.cleanup()

  def pass_deferred(self, which_pass):
    """WHICH_PASS is being deferred until a future cvs2svn run.
    Unregister any artifacts that would be cleaned up during
    WHICH_PASS."""

    self._unregister_artifacts(which_pass)

  def check_clean(self):
    """All passes have been processed.  Output a warning messages if
    all artifacts have not been accounted for.  (This is mainly a
    consistency check, that no artifacts were registered under
    nonexistent passes.)"""

    if self._artifacts:
      Log().warn(
          'INTERNAL: The following artifacts were not cleaned up:\n    %s\n'
          % ('\n    '.join([artifact.name for artifact in self._artifacts])))


# The default ArtifactManager instance:
artifact_manager = ArtifactManager()


