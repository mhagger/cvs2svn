# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2011 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs.
# ====================================================================

"""The interface between cvs2svn and cvs2svn_rcsparse."""

# These identifiers are imported to be exported:
from cvs2svn_rcsparse.common import Sink
from cvs2svn_rcsparse.common import RCSParseError


selected_parser = None

def select_texttools_parser():
  """Configure this module to use the texttools parser.

  The texttools parser is faster but depends on mx.TextTools, which is
  not part of the Python standard library.  If it is not installed,
  this function will raise an ImportError."""

  global selected_parser
  import cvs2svn_rcsparse.texttools
  selected_parser = cvs2svn_rcsparse.texttools.Parser


def select_python_parser():
  """Configure this module to use the Python parser.

  The Python parser is slower but works everywhere."""

  global selected_parser
  import cvs2svn_rcsparse.default
  selected_parser = cvs2svn_rcsparse.default.Parser


def select_parser():
  """Configure this module to use the best parser available."""

  try:
    select_texttools_parser()
  except ImportError:
    select_python_parser()


def parse(file, sink):
  """Parse an RCS file.

  The arguments are the same as those of
  cvs2svn_rcsparse.common._Parser.parse() (see that method's docstring
  for more details).
  """

  if selected_parser is None:
    select_parser()

  return selected_parser().parse(file, sink)


