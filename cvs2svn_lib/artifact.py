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

"""This module defines Artifact types to be used with an ArtifactManager."""


import os

from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import logger


class Artifact(object):
  """An object that is created, used across passes, then cleaned up."""

  def __init__(self):
    # The set of passes that need this artifact.  This field is
    # maintained by ArtifactManager.
    self._passes_needed = set()

  def cleanup(self):
    """This artifact is no longer needed; clean it up."""

    pass


class TempFile(Artifact):
  """A temporary file that can be used across cvs2svn passes."""

  def __init__(self, basename):
    Artifact.__init__(self)
    self.basename = basename

  def _get_filename(self):
    return Ctx().get_temp_filename(self.basename)

  filename = property(_get_filename)

  def cleanup(self):
    logger.verbose("Deleting", self.filename)
    os.unlink(self.filename)

  def __str__(self):
    return 'Temporary file %r' % (self.filename,)


