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

"""This module contains common facilities used by cvs2svn."""


from boolean import *


# Warnings and errors start with these strings.  They are typically
# followed by a colon and a space, as in "%s: " ==> "WARNING: ".
warning_prefix = "WARNING"
error_prefix = "ERROR"


class FatalException(Exception):
  """Exception thrown on a non-recoverable error.

  If this exception is thrown by main(), it is caught by the global
  layer of the program, its string representation is printed, and the
  program is ended with an exit code of 1."""

  pass


class FatalError(FatalException):
  """A FatalException that prepends error_prefix to the message."""

  def __init__(self, msg):
    """Use (error_prefix + ': ' + MSG + '\n') as the error message."""

    FatalException.__init__(self, '%s: %s\n' % (error_prefix, msg,))


