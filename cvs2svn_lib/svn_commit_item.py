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

"""This module contains class SVNCommitItem."""


from boolean import *
from context import Ctx


class SVNCommitItem:
  """A wrapper class for CVSRevision objects upon which
  Subversion-related data (such as properties) may be hung."""

  def __init__(self, c_rev, svn_props_changed):
    """Initialize instance and record the properties for this file.
    SVN_PROPS_CHANGED indicates whether the svn: properties are known
    to have changed since the last revision.

    The properties are set by the SVNPropertySetters in
    Ctx().svn_property_setters, then we read a couple of the
    properties back out for our own purposes."""

    self.c_rev = c_rev
    # Did the svn properties change for this file (i.e., do they have
    # to be written to the dumpfile?)
    self.svn_props_changed = svn_props_changed

    # The properties for this item as a map { key : value }.  If VALUE
    # is None, no property should be set.
    self.svn_props = { }

    for svn_property_setter in Ctx().svn_property_setters:
      svn_property_setter.set_properties(self)

    # Remember if we need to filter the EOLs.  We could actually use
    # self.svn_props now, since it is initialized for each revision.
    self.needs_eol_filter = \
        self.svn_props.get('svn:eol-style', None) is not None

    self.has_keywords = self.svn_props.get('svn:keywords', None) is not None


