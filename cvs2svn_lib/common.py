# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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


import time
import codecs

from cvs2svn_lib.log import logger


# Always use these constants for opening databases.
DB_OPEN_READ = 'r'
DB_OPEN_WRITE = 'w'
DB_OPEN_NEW = 'n'


SVN_INVALID_REVNUM = -1


# Warnings and errors start with these strings.  They are typically
# followed by a colon and a space, as in "%s: " ==> "WARNING: ".
warning_prefix = "WARNING"
error_prefix = "ERROR"


class FatalException(Exception):
  """Exception thrown on a non-recoverable error.

  If this exception is thrown by main(), it is caught by the global
  layer of the program, its string representation is printed (followed
  by a newline), and the program is ended with an exit code of 1."""

  pass


class InternalError(Exception):
  """Exception thrown in the case of a cvs2svn internal error (aka, bug)."""

  pass


class FatalError(FatalException):
  """A FatalException that prepends error_prefix to the message."""

  def __init__(self, msg):
    """Use (error_prefix + ': ' + MSG) as the error message."""

    FatalException.__init__(self, '%s: %s' % (error_prefix, msg,))


class CommandError(FatalError):
  """A FatalError caused by a failed command invocation.

  The error message includes the command name, exit code, and output."""

  def __init__(self, command, exit_status, error_output=''):
    self.command = command
    self.exit_status = exit_status
    self.error_output = error_output
    if error_output.rstrip():
      FatalError.__init__(
          self,
          'The command %r failed with exit status=%s\n'
          'and the following output:\n'
          '%s'
          % (self.command, self.exit_status, self.error_output.rstrip()))
    else:
      FatalError.__init__(
          self,
          'The command %r failed with exit status=%s and no output'
          % (self.command, self.exit_status))


def canonicalize_eol(text, eol):
  """Replace any end-of-line sequences in TEXT with the string EOL."""

  text = text.replace('\r\n', '\n')
  text = text.replace('\r', '\n')
  if eol != '\n':
    text = text.replace('\n', eol)
  return text


def path_join(*components):
  """Join two or more pathname COMPONENTS, inserting '/' as needed.
  Empty component are skipped."""

  return '/'.join(filter(None, components))


def path_split(path):
  """Split the svn pathname PATH into a pair, (HEAD, TAIL).

  This is similar to os.path.split(), but always uses '/' as path
  separator.  PATH is an svn path, which should not start with a '/'.
  HEAD is everything before the last slash, and TAIL is everything
  after.  If PATH ends in a slash, TAIL will be empty.  If there is no
  slash in PATH, HEAD will be empty.  If PATH is empty, both HEAD and
  TAIL are empty."""

  pos = path.rfind('/')
  if pos == -1:
    return ('', path,)
  else:
    return (path[:pos], path[pos+1:],)


class IllegalSVNPathError(FatalException):
  pass


def normalize_svn_path(path, allow_empty=False):
  """Normalize an SVN path (e.g., one supplied by a user).

  1. Strip leading, trailing, and duplicated '/'.
  2. If ALLOW_EMPTY is not set, verify that PATH is not empty.

  Return the normalized path.

  If the path is invalid, raise an IllegalSVNPathError."""

  norm_path = path_join(*path.split('/'))
  if not allow_empty and not norm_path:
    raise IllegalSVNPathError("Path is empty")
  return norm_path


class PathRepeatedException(Exception):
  def __init__(self, path, count):
    self.path = path
    self.count = count
    Exception.__init__(
        self, 'Path %s is repeated %d times' % (self.path, self.count,)
        )


class PathsNestedException(Exception):
  def __init__(self, nest, nestlings):
    self.nest = nest
    self.nestlings = nestlings
    Exception.__init__(
        self,
        'Path %s contains the following other paths: %s'
        % (self.nest, ', '.join(self.nestlings),)
        )


class PathsNotDisjointException(FatalException):
  """An exception that collects multiple other disjointness exceptions."""

  def __init__(self, problems):
    self.problems = problems
    Exception.__init__(
        self,
        'The following paths are not disjoint:\n'
        '    %s\n'
        % ('\n    '.join([str(problem) for problem in self.problems]),)
        )


def verify_paths_disjoint(*paths):
  """Verify that all of the paths in the argument list are disjoint.

  If any of the paths is nested in another one (i.e., in the sense
  that 'a/b/c/d' is nested in 'a/b'), or any two paths are identical,
  raise a PathsNotDisjointException containing exceptions detailing
  the individual problems."""

  def split(path):
    if not path:
      return []
    else:
      return path.split('/')

  def contains(split_path1, split_path2):
    """Return True iff SPLIT_PATH1 contains SPLIT_PATH2."""

    return (
        len(split_path1) < len(split_path2)
        and split_path2[:len(split_path1)] == split_path1
        )

  paths = [(split(path), path) for path in paths]
  # If all overlapping elements are equal, a shorter list is
  # considered "less than" a longer one.  Therefore if any paths are
  # nested, this sort will leave at least one such pair adjacent, in
  # the order [nest,nestling].
  paths.sort()

  problems = []

  # Create exceptions for any repeated paths, and delete the repeats
  # from the paths array:
  i = 0
  while i < len(paths):
    split_path, path = paths[i]
    j = i + 1
    while j < len(paths) and split_path == paths[j][0]:
      j += 1
    if j - i > 1:
      problems.append(PathRepeatedException(path, j - i))
      # Delete all but the first copy:
      del paths[i + 1:j]
    i += 1

  # Create exceptions for paths nested in each other:
  i = 0
  while i < len(paths):
    split_path, path = paths[i]
    j = i + 1
    while j < len(paths) and contains(split_path, paths[j][0]):
      j += 1
    if j - i > 1:
      problems.append(PathsNestedException(
          path, [path2 for (split_path2, path2) in paths[i + 1:j]]
          ))
    i += 1

  if problems:
    raise PathsNotDisjointException(problems)


def is_trunk_revision(rev):
  """Return True iff REV is a trunk revision.

  REV is a CVS revision number (e.g., '1.6' or '1.6.4.5').  Return
  True iff the revision is on trunk."""

  return rev.count('.') == 1


def is_branch_revision_number(rev):
  """Return True iff REV is a branch revision number.

  REV is a CVS revision number in canonical form (i.e., with zeros
  removed).  Return True iff it refers to a whole branch, as opposed
  to a single revision."""

  return rev.count('.') % 2 == 0


def format_date(date):
  """Return an svn-compatible date string for DATE (seconds since epoch).

  A Subversion date looks like '2002-09-29T14:44:59.000000Z'."""

  return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(date))


class CVSTextDecoder:
  """Callable that decodes CVS strings into Unicode.

  Members:

    decoders -- a list [(name, CodecInfo.decode), ...] containing the
        names and decoders that will be used in 'strict' mode to
        attempt to decode inputs.

    fallback_decoder -- a tuple (name, CodecInfo.decode) containing
        the name and decoder that will be used in 'replace' mode if
        none of the decoders in DECODERS succeeds.  If no
        fallback_decoder has been specified, this member contains
        None.

    eol_fix -- a string to which all EOL sequences will be converted,
        or None if they should be left unchanged.

  """

  def __init__(self, encodings, fallback_encoding=None, eol_fix=None):
    """Create a CVSTextDecoder instance.

    ENCODINGS is a list containing the names of encodings that are
    attempted to be used as source encodings in 'strict' mode.

    FALLBACK_ENCODING, if specified, is the name of an encoding that
    should be used as a source encoding in lossy 'replace' mode if all
    of ENCODINGS failed.

    EOL_FIX is the string to which all EOL sequences should be
    converted.  If it is set to None, then EOL sequences are left
    unchanged.

    Raise LookupError if any of the specified encodings is unknown."""

    self.decoders = []

    for encoding in encodings:
      self.add_encoding(encoding)

    self.set_fallback_encoding(fallback_encoding)
    self.eol_fix = eol_fix

  def add_encoding(self, encoding):
    """Add an encoding to be tried in 'strict' mode.

    ENCODING is the name of an encoding.  If it is unknown, raise a
    LookupError."""

    for (name, decoder) in self.decoders:
      if name == encoding:
        return
    else:
      self.decoders.append( (encoding, codecs.lookup(encoding)[1]) )

  def set_fallback_encoding(self, encoding):
    """Set the fallback encoding, to be tried in 'replace' mode.

    ENCODING is the name of an encoding.  If it is unknown, raise a
    LookupError."""

    if encoding is None:
      self.fallback_decoder = None
    else:
      self.fallback_decoder = (encoding, codecs.lookup(encoding)[1])

  def decode(self, s):
    """Try to decode string S using our configured source encodings.

    Return the string as a Unicode string.  If S is already a unicode
    string, do nothing.

    Raise UnicodeError if the string cannot be decoded using any of
    the source encodings and no fallback encoding was specified."""

    if isinstance(s, unicode):
      return s
    for (name, decoder) in self.decoders:
      try:
        return decoder(s)[0]
      except ValueError:
        logger.verbose("Encoding '%s' failed for string %r" % (name, s))

    if self.fallback_decoder is not None:
      (name, decoder) = self.fallback_decoder
      return decoder(s, 'replace')[0]
    else:
      raise UnicodeError()

  def __call__(self, s):
    s = self.decode(s)
    if self.eol_fix is not None:
      s = canonicalize_eol(s, self.eol_fix)
    return s

  def decode_path(self, path):
    """Try to decode PATH using our configured source encodings.

    Decode each path component separately (as they may each use
    different encodings)."""

    return u'/'.join([
        self.decode(piece)
        for piece in path.split('/')
        ])


class Timestamper:
  """Return monotonic timestamps derived from changeset timestamps."""

  def __init__(self):
    # The last timestamp that has been returned:
    self.timestamp = 0.0

    # The maximum timestamp that is considered reasonable:
    self.max_timestamp = time.time() + 24.0 * 60.0 * 60.0

  def get(self, timestamp, change_expected):
    """Return a reasonable timestamp derived from TIMESTAMP.

    Push TIMESTAMP into the future if necessary to ensure that it is
    at least one second later than every other timestamp that has been
    returned by previous calls to this method.

    If CHANGE_EXPECTED is not True, then log a message if the
    timestamp has to be changed."""

    if timestamp > self.max_timestamp:
      # If a timestamp is in the future, it is assumed that it is
      # bogus.  Shift it backwards in time to prevent it forcing other
      # timestamps to be pushed even further in the future.

      # Note that this is not nearly a complete solution to the bogus
      # timestamp problem.  A timestamp in the future still affects
      # the ordering of changesets, and a changeset having such a
      # timestamp will not be committed until all changesets with
      # earlier timestamps have been committed, even if other
      # changesets with even earlier timestamps depend on this one.
      self.timestamp = self.timestamp + 1.0
      if not change_expected:
        logger.warn(
            'Timestamp "%s" is in the future; changed to "%s".'
            % (time.asctime(time.gmtime(timestamp)),
               time.asctime(time.gmtime(self.timestamp)),)
            )
    elif timestamp < self.timestamp + 1.0:
      self.timestamp = self.timestamp + 1.0
      if not change_expected and logger.is_on(logger.VERBOSE):
        logger.verbose(
            'Timestamp "%s" adjusted to "%s" to ensure monotonicity.'
            % (time.asctime(time.gmtime(timestamp)),
               time.asctime(time.gmtime(self.timestamp)),)
            )
    else:
      self.timestamp = timestamp

    return self.timestamp


