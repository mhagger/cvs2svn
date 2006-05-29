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

"""This module contains a class to store information about a CVS file."""

import os

from cvs2svn_lib.boolean import *
from cvs2svn_lib.key_generator import KeyGenerator


class CVSFile(object):
  """Represent a CVS file."""

  key_generator = KeyGenerator(1)

  def __init__(self, id, filename, cvs_path,
               in_attic, executable, file_size, mode):
    """Initialize a new CVSFile object.

    Arguments:

      ID                 --> (int or None) unique id for this file.  If None,
                             a new id is generated.
      FILENAME           --> (string) the filesystem path to the CVS file
      CVS_PATH           --> (string) the canonical path within the CVS
                             project (no 'Attic', no ',v', forward slashes)
      IN_ATTIC           --> (bool) True iff RCS file is in Attic
      EXECUTABLE         --> (bool) True iff RCS file has executable bit set
      FILE_SIZE          --> (long) size of the RCS file in bytes
      MODE               --> (string or None) 'kkv', 'kb', etc."""

    if id is None:
      self.id = self.key_generator.gen_id()
    else:
      self.id = id

    self.filename = filename
    self.cvs_path = cvs_path
    self.in_attic = in_attic
    self.executable = executable
    self.file_size = file_size
    self.mode = mode

    # The default RCS branch, if any, for this CVS file.
    #
    # The value is None or a vendor branch revision, such as
    # '1.1.1.1', or '1.1.1.2', or '1.1.1.96'.  The vendor branch
    # revision represents the highest vendor branch revision thought
    # to have ever been head of the default branch.
    #
    # The reason we record a specific vendor revision, rather than a
    # default branch number, is that there are two cases to handle:
    #
    # One case is simple.  The RCS file lists a default branch
    # explicitly in its header, such as '1.1.1'.  In this case, we
    # know that every revision on the vendor branch is to be treated
    # as head of trunk at that point in time.
    #
    # But there's also a degenerate case.  The RCS file does not
    # currently have a default branch, yet we can deduce that for some
    # period in the past it probably *did* have one.  For example, the
    # file has vendor revisions 1.1.1.1 -> 1.1.1.96, all of which are
    # dated before 1.2, and then it has 1.1.1.97 -> 1.1.1.100 dated
    # after 1.2.  In this case, we should record 1.1.1.96 as the last
    # vendor revision to have been the head of the default branch.
    #
    # This information is determined by _FileDataCollector and stored
    # here.
    self.default_branch = None

  def get_basename(self):
    """Return the last path component of self.filename, minus the ',v'."""

    return os.path.basename(self.filename)[:-2]

  basename = property(get_basename)


