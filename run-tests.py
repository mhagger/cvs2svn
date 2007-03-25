#!/usr/bin/env python
#
#  run_tests.py:  test suite for cvs2svn
#
#  Usage: run_tests.py [-v | --verbose] [list | <num>]
#
#  Options:
#      -v, --verbose
#          enable verbose output
#
#  Arguments (at most one argument is allowed):
#      list
#          If the word "list" is passed as an argument, the list of
#          available tests is printed (but no tests are run).
#
#      <num>
#          If a number is passed as an argument, then only the test
#          with that number is run.
#
#      If no argument is specified, then all tests are run.
#
#  Subversion is a tool for revision control.
#  See http://subversion.tigris.org for more information.
#
# ====================================================================
# Copyright (c) 2000-2004 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
######################################################################

# General modules
import sys
import shutil
import stat
import re
import os
import time
import os.path
import locale

# Make sure this Python is recent enough.
if sys.hexversion < 0x02020000:
  sys.stderr.write("error: Python 2.2 or higher required, "
                   "see www.python.org.\n")
  sys.exit(1)

# This script needs to run in the correct directory.  Make sure we're there.
if not (os.path.exists('cvs2svn') and os.path.exists('test-data')):
  sys.stderr.write("error: I need to be run in the directory containing "
                   "'cvs2svn' and 'test-data'.\n")
  sys.exit(1)

# Load the Subversion test framework.
import svntest
from svntest import Failure
from svntest.testcase import TestCase
from svntest.testcase import Skip
from svntest.testcase import XFail

cvs2svn = os.path.abspath('cvs2svn')

# We use the installed svn and svnlook binaries, instead of using
# svntest.main.run_svn() and svntest.main.run_svnlook(), because the
# behavior -- or even existence -- of local builds shouldn't affect
# the cvs2svn test suite.
svn = 'svn'
svnlook = 'svnlook'

test_data_dir = 'test-data'
tmp_dir = 'tmp'


#----------------------------------------------------------------------
# Helpers.
#----------------------------------------------------------------------


# The value to expect for svn:keywords if it is set:
KEYWORDS = 'Author Date Id Revision'


class RunProgramException:
  pass

class MissingErrorException:
  pass

def run_program(program, error_re, *varargs):
  """Run PROGRAM with VARARGS, return stdout as a list of lines.
  If there is any stderr and ERROR_RE is None, raise
  RunProgramException, and print the stderr lines if
  svntest.main.verbose_mode is true.

  If ERROR_RE is not None, it is a string regular expression that must
  match some line of stderr.  If it fails to match, raise
  MissingErrorExpection."""
  out, err = svntest.main.run_command(program, 1, 0, *varargs)
  if err:
    if error_re:
      for line in err:
        if re.match(error_re, line):
          return out
      raise MissingErrorException()
    else:
      if svntest.main.verbose_mode:
        print '\n%s said:\n' % program
        for line in err:
          print '   ' + line,
        print
      raise RunProgramException()
  return out


def run_cvs2svn(error_re, *varargs):
  """Run cvs2svn with VARARGS, return stdout as a list of lines.
  If there is any stderr and ERROR_RE is None, raise
  RunProgramException, and print the stderr lines if
  svntest.main.verbose_mode is true.

  If ERROR_RE is not None, it is a string regular expression that must
  match some line of stderr.  If it fails to match, raise
  MissingErrorException."""
  # Use the same python that is running this script
  return run_program(sys.executable, error_re, cvs2svn, *varargs)
  # On Windows, for an unknown reason, the cmd.exe process invoked by
  # os.system('sort ...') in cvs2svn receives invalid stdio handles, if
  # cvs2svn is started as "cvs2svn ...".  "python cvs2svn ..." avoids
  # this.  Therefore, the redirection of the output to the .s-revs file fails.
  # We no longer use the problematic invocation on any system, but this
  # comment remains to warn about this problem.


def run_svn(*varargs):
  """Run svn with VARARGS; return stdout as a list of lines.
  If there is any stderr, raise RunProgramException, and print the
  stderr lines if svntest.main.verbose_mode is true."""
  return run_program(svn, None, *varargs)


def repos_to_url(path_to_svn_repos):
  """This does what you think it does."""
  rpath = os.path.abspath(path_to_svn_repos)
  if rpath[0] != '/':
    rpath = '/' + rpath
  return 'file://%s' % rpath.replace(os.sep, '/')

if hasattr(time, 'strptime'):
  def svn_strptime(timestr):
    return time.strptime(timestr, '%Y-%m-%d %H:%M:%S')
else:
  # This is for Python earlier than 2.3 on Windows
  _re_rev_date = re.compile(r'(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)')
  def svn_strptime(timestr):
    matches = _re_rev_date.match(timestr).groups()
    return tuple(map(int, matches)) + (0, 1, -1)

class Log:
  def __init__(self, revision, author, date, symbols):
    self.revision = revision
    self.author = author

    # Internally, we represent the date as seconds since epoch (UTC).
    # Since standard subversion log output shows dates in localtime
    #
    #   "1993-06-18 00:46:07 -0500 (Fri, 18 Jun 1993)"
    #
    # and time.mktime() converts from localtime, it all works out very
    # happily.
    self.date = time.mktime(svn_strptime(date[0:19]))

    # The following symbols are used for string interpolation when
    # checking paths:
    self.symbols = symbols

    # The changed paths will be accumulated later, as log data is read.
    # Keys here are paths such as '/trunk/foo/bar', values are letter
    # codes such as 'M', 'A', and 'D'.
    self.changed_paths = { }

    # The msg will be accumulated later, as log data is read.
    self.msg = ''

  def absorb_changed_paths(self, out):
    'Read changed paths from OUT into self, until no more.'
    while 1:
      line = out.readline()
      if len(line) == 1: return
      line = line[:-1]
      op_portion = line[3:4]
      path_portion = line[5:]
      # If we're running on Windows we get backslashes instead of
      # forward slashes.
      path_portion = path_portion.replace('\\', '/')
      # # We could parse out history information, but currently we
      # # just leave it in the path portion because that's how some
      # # tests expect it.
      #
      # m = re.match("(.*) \(from /.*:[0-9]+\)", path_portion)
      # if m:
      #   path_portion = m.group(1)
      self.changed_paths[path_portion] = op_portion

  def __cmp__(self, other):
    return cmp(self.revision, other.revision) or \
        cmp(self.author, other.author) or cmp(self.date, other.date) or \
        cmp(self.changed_paths, other.changed_paths) or \
        cmp(self.msg, other.msg)

  def get_path_op(self, path):
    """Return the operator for the change involving PATH.

    PATH is allowed to include string interpolation directives (e.g.,
    '%(trunk)s'), which are interpolated against self.symbols.  Return
    None if there is no record for PATH."""
    return self.changed_paths.get(path % self.symbols)

  def check_msg(self, msg):
    """Verify that this Log's message starts with the specified MSG."""
    if self.msg.find(msg) != 0:
      raise Failure(
          "Revision %d log message was:\n%s\n\n"
          "It should have begun with:\n%s\n\n"
          % (self.revision, self.msg, msg,)
          )

  def check_change(self, path, op):
    """Verify that this Log includes a change for PATH with operator OP.

    PATH is allowed to include string interpolation directives (e.g.,
    '%(trunk)s'), which are interpolated against self.symbols."""

    path = path % self.symbols
    found_op = self.changed_paths.get(path, None)
    if found_op is None:
      raise Failure(
          "Revision %d does not include change for path %s "
          "(it should have been %s).\n"
          % (self.revision, path, op,)
          )
    if found_op != op:
      raise Failure(
          "Revision %d path %s had op %s (it should have been %s)\n"
          % (self.revision, path, found_op, op,)
          )

  def check_changes(self, changed_paths):
    """Verify that this Log has precisely the CHANGED_PATHS specified.

    CHANGED_PATHS is a sequence of tuples (path, op), where the paths
    strings are allowed to include string interpolation directives
    (e.g., '%(trunk)s'), which are interpolated against self.symbols."""

    cp = {}
    for (path, op) in changed_paths:
      cp[path % self.symbols] = op

    if self.changed_paths != cp:
      raise Failure(
          "Revision %d changed paths list was:\n%s\n\n"
          "It should have been:\n%s\n\n"
          % (self.revision, self.changed_paths, cp,)
          )

  def check(self, msg, changed_paths):
    """Verify that this Log has the MSG and CHANGED_PATHS specified.

    Convenience function to check two things at once.  MSG is passed
    to check_msg(); CHANGED_PATHS is passed to check_changes()."""

    self.check_msg(msg)
    self.check_changes(changed_paths)


def parse_log(svn_repos, symbols):
  """Return a dictionary of Logs, keyed on revision number, for SVN_REPOS.

  Initialize the Logs' symbols with SYMBOLS."""

  class LineFeeder:
    'Make a list of lines behave like an open file handle.'
    def __init__(self, lines):
      self.lines = lines
    def readline(self):
      if len(self.lines) > 0:
        return self.lines.pop(0)
      else:
        return None

  def absorb_message_body(out, num_lines, log):
    'Read NUM_LINES of log message body from OUT into Log item LOG.'
    i = 0
    while i < num_lines:
      line = out.readline()
      log.msg += line
      i += 1

  log_start_re = re.compile('^r(?P<rev>[0-9]+) \| '
                            '(?P<author>[^\|]+) \| '
                            '(?P<date>[^\|]+) '
                            '\| (?P<lines>[0-9]+) (line|lines)$')

  log_separator = '-' * 72

  logs = { }

  out = LineFeeder(run_svn('log', '-v', repos_to_url(svn_repos)))

  while 1:
    this_log = None
    line = out.readline()
    if not line: break
    line = line[:-1]

    if line.find(log_separator) == 0:
      line = out.readline()
      if not line: break
      line = line[:-1]
      m = log_start_re.match(line)
      if m:
        this_log = Log(
            int(m.group('rev')), m.group('author'), m.group('date'), symbols)
        line = out.readline()
        if not line.find('Changed paths:') == 0:
          print 'unexpected log output (missing changed paths)'
          print "Line: '%s'" % line
          sys.exit(1)
        this_log.absorb_changed_paths(out)
        absorb_message_body(out, int(m.group('lines')), this_log)
        logs[this_log.revision] = this_log
      elif len(line) == 0:
        break   # We've reached the end of the log output.
      else:
        print 'unexpected log output (missing revision line)'
        print "Line: '%s'" % line
        sys.exit(1)
    else:
      print 'unexpected log output (missing log separator)'
      print "Line: '%s'" % line
      sys.exit(1)

  return logs


def erase(path):
  """Unconditionally remove PATH and its subtree, if any.  PATH may be
  non-existent, a file or symlink, or a directory."""
  if os.path.isdir(path):
    svntest.main.safe_rmtree(path)
  elif os.path.exists(path):
    os.remove(path)


def sym_log_msg(symbolic_name, is_tag=None):
  """Return the expected log message for a cvs2svn-synthesized revision
  creating branch or tag SYMBOLIC_NAME."""
  # This is a copy-paste of part of cvs2svn's make_revision_props
  if is_tag:
    type = 'tag'
  else:
    type = 'branch'

  # In Python 2.2.3, we could use textwrap.fill().  Oh well :-).
  if len(symbolic_name) >= 13:
    space_or_newline = '\n'
  else:
    space_or_newline = ' '

  log = "This commit was manufactured by cvs2svn to create %s%s'%s'." \
      % (type, space_or_newline, symbolic_name)

  return log


def make_conversion_id(name, args, passbypass, options_file=None):
  """Create an identifying tag for a conversion.

  The return value can also be used as part of a filesystem path.

  NAME is the name of the CVS repository.

  ARGS are the extra arguments to be passed to cvs2svn.

  PASSBYPASS is a boolean indicating whether the conversion is to be
  run one pass at a time.

  If OPTIONS_FILE is specified, it is an options file that will be
  used for the conversion.

  The 1-to-1 mapping between cvs2svn command parameters and
  conversion_ids allows us to avoid running the same conversion more
  than once, when multiple tests use exactly the same conversion."""

  conv_id = name

  _win32_fname_mapping = { '/': '_sl_', '\\': '_bs_', ':': '_co_',
                           '*': '_st_', '?': '_qm_', '"': '_qq_',
                           '<': '_lt_', '>': '_gt_', '|': '_pi_', }
  for arg in args:
    # Replace some characters that Win32 isn't happy about having in a
    # filename (which was causing the eol_mime test to fail).
    sanitized_arg = arg
    for a, b in _win32_fname_mapping.items():
      sanitized_arg = sanitized_arg.replace(a, b)
    conv_id += sanitized_arg

  if passbypass:
    conv_id += '-passbypass'

  if options_file is not None:
    conv_id += '--options=%s' % options_file

  return conv_id


class Conversion:
  """A record of a cvs2svn conversion.

  Fields:

    conv_id -- the conversion id for this Conversion.

    name -- a one-word name indicating the involved repositories.

    repos -- the path to the svn repository.

    logs -- a dictionary of Log instances, as returned by parse_log().

    symbols -- a dictionary of symbols used for string interpolation
        in path names.

    stdout -- a list of lines written by cvs2svn to stdout

    _wc -- the basename of the svn working copy (within tmp_dir).

    _wc_path -- the path to the svn working copy, if it has already
        been created; otherwise, None.  (The working copy is created
        lazily when get_wc() is called.)

    _wc_tree -- the tree built from the svn working copy, if it has
        already been created; otherwise, None.  The tree is created
        lazily when get_wc_tree() is called.)

    _svnrepos -- the basename of the svn repository (within tmp_dir)."""

  # The number of the last cvs2svn pass (determined lazily by
  # get_last_pass()).
  last_pass = None

  def get_last_pass(cls):
    """Return the number of cvs2svn's last pass."""

    if cls.last_pass is None:
      out = run_cvs2svn(None, '--help-passes')
      cls.last_pass = int(out[-1].split()[0])
    return cls.last_pass

  get_last_pass = classmethod(get_last_pass)

  def __init__(self, conv_id, name, error_re, passbypass, symbols, args,
               options_file=None):
    self.conv_id = conv_id
    self.name = name
    self.symbols = symbols
    if not os.path.isdir(tmp_dir):
      os.mkdir(tmp_dir)

    cvsrepos = os.path.join(test_data_dir, '%s-cvsrepos' % self.name)

    self.repos = os.path.join(tmp_dir, '%s-svnrepos' % self.conv_id)
    self._wc = os.path.join(tmp_dir, '%s-wc' % self.conv_id)
    self._wc_path = None
    self._wc_tree = None

    # Clean up from any previous invocations of this script.
    erase(self.repos)
    erase(self._wc)

    if options_file is None:
      self.options_file = None
      args.extend([
          '--tmpdir=%s' % tmp_dir,
          '--bdb-txn-nosync',
          '-s', self.repos,
          cvsrepos,
          ])
    else:
      self.options_file = os.path.join(cvsrepos, options_file)
      args.extend([
          '--options=%s' % self.options_file,
          ])

    try:
      if passbypass:
        for p in range(1, self.get_last_pass() + 1):
          self.stdout = run_cvs2svn(error_re, '-p', str(p), *args)
      else:
        self.stdout = run_cvs2svn(error_re, *args)
    except RunProgramException:
      raise Failure()
    except MissingErrorException:
      raise Failure("Test failed because no error matched '%s'"
                            % error_re)

    if not os.path.isdir(self.repos):
      raise Failure("Repository not created: '%s'"
                            % os.path.join(os.getcwd(), self.repos))

    self.logs = parse_log(self.repos, self.symbols)

  def find_tag_log(self, tagname):
    """Search LOGS for a log message containing 'TAGNAME' and return the
    log in which it was found."""
    for i in xrange(len(self.logs), 0, -1):
      if self.logs[i].msg.find("'"+tagname+"'") != -1:
        return self.logs[i]
    raise ValueError("Tag %s not found in logs" % tagname)

  def get_wc(self, *args):
    """Return the path to the svn working copy, or a path within the WC.

    If a working copy has not been created yet, create it now.

    If ARGS are specified, then they should be strings that form
    fragments of a path within the WC.  They are joined using
    os.path.join() and appended to the WC path."""

    if self._wc_path is None:
      run_svn('co', repos_to_url(self.repos), self._wc)
      self._wc_path = self._wc
    return os.path.join(self._wc_path, *args)

  def get_wc_tree(self):
    if self._wc_tree is None:
      self._wc_tree = svntest.tree.build_tree_from_wc(self.get_wc(), 1)
    return self._wc_tree

  def path_exists(self, *args):
    """Return True if the specified path exists within the repository.

    (The strings in ARGS are first joined into a path using
    os.path.join().)"""

    return os.path.exists(self.get_wc(*args))

  def check_props(self, keys, checks):
    """Helper function for checking lots of properties.  For a list of
    files in the conversion, check that the values of the properties
    listed in KEYS agree with those listed in CHECKS.  CHECKS is a
    list of tuples: [ (filename, [value, value, ...]), ...], where the
    values are listed in the same order as the key names are listed in
    KEYS."""

    for (file, values) in checks:
      assert len(values) == len(keys)
      props = props_for_path(self.get_wc_tree(), file)
      for i in range(len(keys)):
        if props.get(keys[i]) != values[i]:
          raise Failure(
              "File %s has property %s set to \"%s\" "
              "(it should have been \"%s\").\n"
              % (file, keys[i], props.get(keys[i]), values[i],)
              )


# Cache of conversions that have already been done.  Keys are conv_id;
# values are Conversion instances.
already_converted = { }

def ensure_conversion(name, error_re=None, passbypass=None,
                      trunk=None, branches=None, tags=None,
                      args=None, options_file=None):
  """Convert CVS repository NAME to Subversion, but only if it has not
  been converted before by this invocation of this script.  If it has
  been converted before, return the Conversion object from the
  previous invocation.

  If no error, return a Conversion instance.

  If ERROR_RE is a string, it is a regular expression expected to
  match some line of stderr printed by the conversion.  If there is an
  error and ERROR_RE is not set, then raise Failure.

  If PASSBYPASS is set, then cvs2svn is run multiple times, each time
  with a -p option starting at 1 and increasing to a (hardcoded) maximum.

  NAME is just one word.  For example, 'main' would mean to convert
  './test-data/main-cvsrepos', and after the conversion, the resulting
  Subversion repository would be in './tmp/main-svnrepos', and a
  checked out head working copy in './tmp/main-wc'.

  Any other options to pass to cvs2svn should be in ARGS, each element
  being one option, e.g., '--trunk-only'.  If the option takes an
  argument, include it directly, e.g., '--mime-types=PATH'.  Arguments
  are passed to cvs2svn in the order that they appear in ARGS.

  If OPTIONS_FILE is specified, then it should be the name of a file
  within the main directory of the cvs repository associated with this
  test.  It is passed to cvs2svn using the --options option (which
  suppresses some other options that are incompatible with --options)."""

  if args is None:
    args = []
  else:
    args = list(args)

  if trunk is None:
    trunk = 'trunk'
  else:
    args.append('--trunk=%s' % (trunk,))

  if branches is None:
    branches = 'branches'
  else:
    args.append('--branches=%s' % (branches,))

  if tags is None:
    tags = 'tags'
  else:
    args.append('--tags=%s' % (tags,))

  conv_id = make_conversion_id(name, args, passbypass, options_file)

  if conv_id not in already_converted:
    try:
      # Run the conversion and store the result for the rest of this
      # session:
      already_converted[conv_id] = Conversion(
          conv_id, name, error_re, passbypass,
          {'trunk' : trunk, 'branches' : branches, 'tags' : tags},
          args, options_file)
    except Failure:
      # Remember the failure so that a future attempt to run this conversion
      # does not bother to retry, but fails immediately.
      already_converted[conv_id] = None
      raise

  conv = already_converted[conv_id]
  if conv is None:
    raise Failure()
  return conv


class Cvs2SvnTestCase(TestCase):
  def __init__(self, name, description=None, variant=None,
               error_re=None, passbypass=None,
               trunk=None, branches=None, tags=None,
               args=None, options_file=None):
    TestCase.__init__(self)
    self.name = name

    if description is not None:
      self._description = description
    else:
      # By default, use the first line of the class docstring as the
      # description:
      self._description = self.__doc__.splitlines()[0]

    # Check that the original description is OK before we tinker with
    # it:
    self.check_description()

    if variant is not None:
      # Modify description to show the variant.  Trim description
      # first if necessary to stay within the 50-character limit.
      suffix = '...variant %s' % (variant,)
      self._description = self._description[:50 - len(suffix)] + suffix
      # Check that the description is still OK:
      self.check_description()

    self.error_re = error_re
    self.passbypass = passbypass
    self.trunk = trunk
    self.branches = branches
    self.tags = tags
    self.args = args
    self.options_file = options_file

  def get_description(self):
    return self._description

  def ensure_conversion(self):
    return ensure_conversion(
        self.name,
        error_re=self.error_re, passbypass=self.passbypass,
        trunk=self.trunk, branches=self.branches, tags=self.tags,
        args=self.args, options_file=self.options_file)


class Cvs2SvnPropertiesTestCase(Cvs2SvnTestCase):
  """Test properties resulting from a conversion."""

  def __init__(self, name, props_to_test, expected_props, **kw):
    """Initialize an instance of Cvs2SvnPropertiesTestCase.

    NAME is the name of the test, passed to Cvs2SvnTestCase.
    PROPS_TO_TEST is a list of the names of svn properties that should
    be tested.  EXPECTED_PROPS is a list of tuples [(filename,
    [value,...])], where the second item in each tuple is a list of
    values expected for the properties listed in PROPS_TO_TEST for the
    specified filename.  If a property must *not* be set, then its
    value should be listed as None."""

    Cvs2SvnTestCase.__init__(self, name, **kw)
    self.props_to_test = props_to_test
    self.expected_props = expected_props

  def run(self):
    conv = self.ensure_conversion()
    conv.check_props(self.props_to_test, self.expected_props)


#----------------------------------------------------------------------
# Tests.
#----------------------------------------------------------------------


def show_usage():
  "cvs2svn with no arguments shows usage"
  out = run_cvs2svn(None)
  if (len(out) > 2 and out[0].find('ERROR:') == 0
      and out[1].find('DBM module')):
    print 'cvs2svn cannot execute due to lack of proper DBM module.'
    print 'Exiting without running any further tests.'
    sys.exit(1)
  if out[0].find('USAGE') < 0:
    raise Failure('Basic cvs2svn invocation failed.')


def show_help_passes():
  "cvs2svn --help-passes shows pass information"
  out = run_cvs2svn(None, '--help-passes')
  if out[0].find('PASSES') < 0:
    raise Failure('cvs2svn --help-passes failed.')


def attr_exec():
  "detection of the executable flag"
  if sys.platform == 'win32':
    raise svntest.Skip()
  conv = ensure_conversion('main')
  st = os.stat(conv.get_wc('trunk', 'single-files', 'attr-exec'))
  if not st[0] & stat.S_IXUSR:
    raise Failure()


def space_fname():
  "conversion of filename with a space"
  conv = ensure_conversion('main')
  if not conv.path_exists('trunk', 'single-files', 'space fname'):
    raise Failure()


def two_quick():
  "two commits in quick succession"
  conv = ensure_conversion('main')
  logs = parse_log(
      os.path.join(conv.repos, 'trunk', 'single-files', 'twoquick'), {})
  if len(logs) != 2:
    raise Failure()


class PruneWithCare(Cvs2SvnTestCase):
  "prune, but never too much"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'main', **kw)

  def run(self):
    # Robert Pluim encountered this lovely one while converting the
    # directory src/gnu/usr.bin/cvs/contrib/pcl-cvs/ in FreeBSD's CVS
    # repository (see issue #1302).  Step 4 is the doozy:
    #
    #   revision 1:  adds trunk/blah/, adds trunk/blah/cookie
    #   revision 2:  adds trunk/blah/NEWS
    #   revision 3:  deletes trunk/blah/cookie
    #   revision 4:  deletes blah [re-deleting trunk/blah/cookie pruned blah!]
    #   revision 5:  does nothing
    #
    # After fixing cvs2svn, the sequence (correctly) looks like this:
    #
    #   revision 1:  adds trunk/blah/, adds trunk/blah/cookie
    #   revision 2:  adds trunk/blah/NEWS
    #   revision 3:  deletes trunk/blah/cookie
    #   revision 4:  does nothing [because trunk/blah/cookie already deleted]
    #   revision 5:  deletes blah
    #
    # The difference is in 4 and 5.  In revision 4, it's not correct to
    # prune blah/, because NEWS is still in there, so revision 4 does
    # nothing now.  But when we delete NEWS in 5, that should bubble up
    # and prune blah/ instead.
    #
    # ### Note that empty revisions like 4 are probably going to become
    # ### at least optional, if not banished entirely from cvs2svn's
    # ### output.  Hmmm, or they may stick around, with an extra
    # ### revision property explaining what happened.  Need to think
    # ### about that.  In some sense, it's a bug in Subversion itself,
    # ### that such revisions don't show up in 'svn log' output.
    #
    # In the test below, 'trunk/full-prune/first' represents
    # cookie, and 'trunk/full-prune/second' represents NEWS.

    conv = self.ensure_conversion()

    # Confirm that revision 4 removes '/trunk/full-prune/first',
    # and that revision 6 removes '/trunk/full-prune'.
    #
    # Also confirm similar things about '/full-prune-reappear/...',
    # which is similar, except that later on it reappears, restored
    # from pruneland, because a file gets added to it.
    #
    # And finally, a similar thing for '/partial-prune/...', except that
    # in its case, a permanent file on the top level prevents the
    # pruning from going farther than the subdirectory containing first
    # and second.

    rev = 11
    for path in ('/%(trunk)s/full-prune/first',
                 '/%(trunk)s/full-prune-reappear/sub/first',
                 '/%(trunk)s/partial-prune/sub/first'):
      conv.logs[rev].check_change(path, 'D')

    rev = 13
    for path in ('/%(trunk)s/full-prune',
                 '/%(trunk)s/full-prune-reappear',
                 '/%(trunk)s/partial-prune/sub'):
      conv.logs[rev].check_change(path, 'D')

    rev = 47
    for path in ('/%(trunk)s/full-prune-reappear',
                 '/%(trunk)s/full-prune-reappear/appears-later'):
      conv.logs[rev].check_change(path, 'A')


def interleaved_commits():
  "two interleaved trunk commits, different log msgs"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  # The initial import.
  rev = 38
  conv.logs[rev].check('Initial revision', (
    ('/%(trunk)s/interleaved', 'A'),
    ('/%(trunk)s/interleaved/1', 'A'),
    ('/%(trunk)s/interleaved/2', 'A'),
    ('/%(trunk)s/interleaved/3', 'A'),
    ('/%(trunk)s/interleaved/4', 'A'),
    ('/%(trunk)s/interleaved/5', 'A'),
    ('/%(trunk)s/interleaved/a', 'A'),
    ('/%(trunk)s/interleaved/b', 'A'),
    ('/%(trunk)s/interleaved/c', 'A'),
    ('/%(trunk)s/interleaved/d', 'A'),
    ('/%(trunk)s/interleaved/e', 'A'),
    ))

  # This PEP explains why we pass the 'log' parameter to these two
  # nested functions, instead of just inheriting it from the enclosing
  # scope: http://www.python.org/peps/pep-0227.html

  def check_letters(log):
    """Check if REV is the rev where only letters were committed."""
    log.check('Committing letters only.', (
      ('/%(trunk)s/interleaved/a', 'M'),
      ('/%(trunk)s/interleaved/b', 'M'),
      ('/%(trunk)s/interleaved/c', 'M'),
      ('/%(trunk)s/interleaved/d', 'M'),
      ('/%(trunk)s/interleaved/e', 'M'),
      ))

  def check_numbers(log):
    """Check if REV is the rev where only numbers were committed."""
    log.check('Committing numbers only.', (
      ('/%(trunk)s/interleaved/1', 'M'),
      ('/%(trunk)s/interleaved/2', 'M'),
      ('/%(trunk)s/interleaved/3', 'M'),
      ('/%(trunk)s/interleaved/4', 'M'),
      ('/%(trunk)s/interleaved/5', 'M'),
      ))

  # One of the commits was letters only, the other was numbers only.
  # But they happened "simultaneously", so we don't assume anything
  # about which commit appeared first, so we just try both ways.
  rev = rev + 3
  try:
    check_letters(conv.logs[rev])
    check_numbers(conv.logs[rev + 1])
  except Failure:
    check_numbers(conv.logs[rev])
    check_letters(conv.logs[rev + 1])


def simple_commits():
  "simple trunk commits"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  # The initial import.
  rev = 23
  conv.logs[rev].check('Initial revision', (
    ('/%(trunk)s/proj', 'A'),
    ('/%(trunk)s/proj/default', 'A'),
    ('/%(trunk)s/proj/sub1', 'A'),
    ('/%(trunk)s/proj/sub1/default', 'A'),
    ('/%(trunk)s/proj/sub1/subsubA', 'A'),
    ('/%(trunk)s/proj/sub1/subsubA/default', 'A'),
    ('/%(trunk)s/proj/sub1/subsubB', 'A'),
    ('/%(trunk)s/proj/sub1/subsubB/default', 'A'),
    ('/%(trunk)s/proj/sub2', 'A'),
    ('/%(trunk)s/proj/sub2/default', 'A'),
    ('/%(trunk)s/proj/sub2/subsubA', 'A'),
    ('/%(trunk)s/proj/sub2/subsubA/default', 'A'),
    ('/%(trunk)s/proj/sub3', 'A'),
    ('/%(trunk)s/proj/sub3/default', 'A'),
    ))

  # The first commit.
  rev = 30
  conv.logs[rev].check('First commit to proj, affecting two files.', (
    ('/%(trunk)s/proj/sub1/subsubA/default', 'M'),
    ('/%(trunk)s/proj/sub3/default', 'M'),
    ))

  # The second commit.
  rev = 31
  conv.logs[rev].check('Second commit to proj, affecting all 7 files.', (
    ('/%(trunk)s/proj/default', 'M'),
    ('/%(trunk)s/proj/sub1/default', 'M'),
    ('/%(trunk)s/proj/sub1/subsubA/default', 'M'),
    ('/%(trunk)s/proj/sub1/subsubB/default', 'M'),
    ('/%(trunk)s/proj/sub2/default', 'M'),
    ('/%(trunk)s/proj/sub2/subsubA/default', 'M'),
    ('/%(trunk)s/proj/sub3/default', 'M')
    ))


class SimpleTags(Cvs2SvnTestCase):
  "simple tags and branches, no commits"

  def __init__(self, **kw):
    # See test-data/main-cvsrepos/proj/README.
    Cvs2SvnTestCase.__init__(self, 'main', **kw)

  def run(self):
    conv = self.ensure_conversion()

    # Verify the copy source for the tags we are about to check
    # No need to verify the copyfrom revision, as simple_commits did that
    conv.logs[24].check(sym_log_msg('vendorbranch'), (
      ('/%(branches)s/vendorbranch/proj (from /%(trunk)s/proj:23)', 'A'),
      ))

    fromstr = ' (from /%(branches)s/vendorbranch:25)'

    # Tag on rev 1.1.1.1 of all files in proj
    log = conv.find_tag_log('T_ALL_INITIAL_FILES')
    log.check(sym_log_msg('T_ALL_INITIAL_FILES',1), (
      ('/%(tags)s/T_ALL_INITIAL_FILES'+fromstr, 'A'),
      ('/%(tags)s/T_ALL_INITIAL_FILES/single-files', 'D'),
      ('/%(tags)s/T_ALL_INITIAL_FILES/partial-prune', 'D'),
      ))

    # The same, as a branch
    conv.logs[26].check(sym_log_msg('B_FROM_INITIALS'), (
      ('/%(branches)s/B_FROM_INITIALS'+fromstr, 'A'),
      ('/%(branches)s/B_FROM_INITIALS/single-files', 'D'),
      ('/%(branches)s/B_FROM_INITIALS/partial-prune', 'D'),
      ))

    # Tag on rev 1.1.1.1 of all files in proj, except one
    log = conv.find_tag_log('T_ALL_INITIAL_FILES_BUT_ONE')
    log.check(sym_log_msg('T_ALL_INITIAL_FILES_BUT_ONE',1), (
      ('/%(tags)s/T_ALL_INITIAL_FILES_BUT_ONE'+fromstr, 'A'),
      ('/%(tags)s/T_ALL_INITIAL_FILES_BUT_ONE/single-files', 'D'),
      ('/%(tags)s/T_ALL_INITIAL_FILES_BUT_ONE/partial-prune', 'D'),
      ('/%(tags)s/T_ALL_INITIAL_FILES_BUT_ONE/proj/sub1/subsubB', 'D'),
      ))

    # The same, as a branch
    conv.logs[27].check(sym_log_msg('B_FROM_INITIALS_BUT_ONE'), (
      ('/%(branches)s/B_FROM_INITIALS_BUT_ONE'+fromstr, 'A'),
      ('/%(branches)s/B_FROM_INITIALS_BUT_ONE/single-files', 'D'),
      ('/%(branches)s/B_FROM_INITIALS_BUT_ONE/partial-prune', 'D'),
      ('/%(branches)s/B_FROM_INITIALS_BUT_ONE/proj/sub1/subsubB', 'D'),
      ))


def simple_branch_commits():
  "simple branch commits"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  rev = 35
  conv.logs[rev].check('Modify three files, on branch B_MIXED.', (
    ('/%(branches)s/B_MIXED/proj/default', 'M'),
    ('/%(branches)s/B_MIXED/proj/sub1/default', 'M'),
    ('/%(branches)s/B_MIXED/proj/sub2/subsubA/default', 'M'),
    ))


def mixed_time_tag():
  "mixed-time tag"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  log = conv.find_tag_log('T_MIXED')
  expected = (
    ('/%(tags)s/T_MIXED (from /%(trunk)s:31)', 'A'),
    ('/%(tags)s/T_MIXED/partial-prune', 'D'),
    ('/%(tags)s/T_MIXED/single-files', 'D'),
    ('/%(tags)s/T_MIXED/proj/sub2/subsubA '
    '(from /%(trunk)s/proj/sub2/subsubA:23)', 'R'),
    ('/%(tags)s/T_MIXED/proj/sub3 (from /%(trunk)s/proj/sub3:30)', 'R'),
    )
  if log.revision == 16:
    expected.append(('/%(tags)s', 'A'))
  log.check_changes(expected)


def mixed_time_branch_with_added_file():
  "mixed-time branch, and a file added to the branch"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  # A branch from the same place as T_MIXED in the previous test,
  # plus a file added directly to the branch
  conv.logs[33].check(sym_log_msg('B_MIXED'), (
    ('/%(branches)s/B_MIXED (from /%(trunk)s:31)', 'A'),
    ('/%(branches)s/B_MIXED/partial-prune', 'D'),
    ('/%(branches)s/B_MIXED/single-files', 'D'),
    ('/%(branches)s/B_MIXED/proj/sub2/subsubA '
     '(from /%(trunk)s/proj/sub2/subsubA:23)', 'R'),
    ('/%(branches)s/B_MIXED/proj/sub3 (from /%(trunk)s/proj/sub3:30)', 'R'),
    ))

  conv.logs[34].check('Add a file on branch B_MIXED.', (
    ('/%(branches)s/B_MIXED/proj/sub2/branch_B_MIXED_only', 'A'),
    ))


def mixed_commit():
  "a commit affecting both trunk and a branch"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  conv.logs[36].check(
      'A single commit affecting one file on branch B_MIXED '
      'and one on trunk.', (
    ('/%(trunk)s/proj/sub2/default', 'M'),
    ('/%(branches)s/B_MIXED/proj/sub2/branch_B_MIXED_only', 'M'),
    ))


def split_time_branch():
  "branch some trunk files, and later branch the rest"
  # See test-data/main-cvsrepos/proj/README.
  conv = ensure_conversion('main')

  rev = 42
  # First change on the branch, creating it
  conv.logs[rev - 5].check(sym_log_msg('B_SPLIT'), (
    ('/%(branches)s/B_SPLIT (from /%(trunk)s:36)', 'A'),
    ('/%(branches)s/B_SPLIT/partial-prune', 'D'),
    ('/%(branches)s/B_SPLIT/single-files', 'D'),
    ('/%(branches)s/B_SPLIT/proj/sub1/subsubB', 'D'),
    ))

  conv.logs[rev + 1].check('First change on branch B_SPLIT.', (
    ('/%(branches)s/B_SPLIT/proj/default', 'M'),
    ('/%(branches)s/B_SPLIT/proj/sub1/default', 'M'),
    ('/%(branches)s/B_SPLIT/proj/sub1/subsubA/default', 'M'),
    ('/%(branches)s/B_SPLIT/proj/sub2/default', 'M'),
    ('/%(branches)s/B_SPLIT/proj/sub2/subsubA/default', 'M'),
    ))

  # A trunk commit for the file which was not branched
  conv.logs[rev + 2].check('A trunk change to sub1/subsubB/default.  '
      'This was committed about an', (
    ('/%(trunk)s/proj/sub1/subsubB/default', 'M'),
    ))

  # Add the file not already branched to the branch, with modification:w
  conv.logs[rev + 3].check(sym_log_msg('B_SPLIT'), (
    ('/%(branches)s/B_SPLIT/proj/sub1/subsubB '
    '(from /%(trunk)s/proj/sub1/subsubB:44)', 'A'),
    ))

  conv.logs[rev + 4].check('This change affects sub3/default and '
      'sub1/subsubB/default, on branch', (
    ('/%(branches)s/B_SPLIT/proj/sub1/subsubB/default', 'M'),
    ('/%(branches)s/B_SPLIT/proj/sub3/default', 'M'),
    ))


def multiple_tags():
  "multiple tags referring to same revision"
  conv = ensure_conversion('main')
  if not conv.path_exists('tags', 'T_ALL_INITIAL_FILES', 'proj', 'default'):
    raise Failure()
  if not conv.path_exists(
        'tags', 'T_ALL_INITIAL_FILES_BUT_ONE', 'proj', 'default'):
    raise Failure()

def bogus_tag():
  "conversion of invalid symbolic names"
  conv = ensure_conversion('bogus-tag')


def overlapping_branch():
  "ignore a file with a branch with two names"
  conv = ensure_conversion('overlapping-branch',
                           error_re='.*cannot also have name \'vendorB\'')
  rev = 4
  conv.logs[rev].check_change('/%(branches)s/vendorA (from /%(trunk)s:3)',
                              'A')
  # We don't know what order the first two commits would be in, since
  # they have different log messages but the same timestamps.  As only
  # one of the files would be on the vendorB branch in the regression
  # case being tested here, we allow for either order.
  if (conv.logs[rev].get_path_op(
          '/%(branches)s/vendorB (from /%(trunk)s:2)') == 'A'
      or conv.logs[rev].get_path_op(
             '/%(branches)s/vendorB (from /%(trunk)s:3)') == 'A'):
    raise Failure()
  conv.logs[rev + 1].check_changes(())
  if len(conv.logs) != rev + 1:
    raise Failure()


class PhoenixBranch(Cvs2SvnTestCase):
  "convert a branch file rooted in a 'dead' revision"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'phoenix', **kw)

  def run(self):
    conv = self.ensure_conversion()
    conv.logs[8].check(sym_log_msg('volsung_20010721'), (
      ('/%(branches)s/volsung_20010721 (from /%(trunk)s:7)', 'A'),
      ('/%(branches)s/volsung_20010721/file.txt', 'D'),
      ))
    conv.logs[9].check('This file was supplied by Jack Moffitt', (
      ('/%(branches)s/volsung_20010721/phoenix', 'A'),
      ))


###TODO: We check for 4 changed paths here to accomodate creating tags
###and branches in rev 1, but that will change, so this will
###eventually change back.
def ctrl_char_in_log():
  "handle a control char in a log message"
  # This was issue #1106.
  rev = 2
  conv = ensure_conversion('ctrl-char-in-log')
  conv.logs[rev].check_changes((
    ('/%(trunk)s/ctrl-char-in-log', 'A'),
    ))
  if conv.logs[rev].msg.find('\x04') < 0:
    raise Failure(
        "Log message of 'ctrl-char-in-log,v' (rev 2) is wrong.")


def overdead():
  "handle tags rooted in a redeleted revision"
  conv = ensure_conversion('overdead')


class NoTrunkPrune(Cvs2SvnTestCase):
  "ensure that trunk doesn't get pruned"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'overdead', **kw)

  def run(self):
    conv = self.ensure_conversion()
    for rev in conv.logs.keys():
      rev_logs = conv.logs[rev]
      if rev_logs.get_path_op('/%(trunk)s') == 'D':
        raise Failure()


def double_delete():
  "file deleted twice, in the root of the repository"
  # This really tests several things: how we handle a file that's
  # removed (state 'dead') in two successive revisions; how we
  # handle a file in the root of the repository (there were some
  # bugs in cvs2svn's svn path construction for top-level files); and
  # the --no-prune option.
  conv = ensure_conversion(
    'double-delete', args=['--trunk-only', '--no-prune'])

  path = '/%(trunk)s/twice-removed'
  rev = 2
  conv.logs[rev].check_change(path, 'A')
  conv.logs[rev].check_msg('Initial revision')

  conv.logs[rev + 1].check_change(path, 'D')
  conv.logs[rev + 1].check_msg('Remove this file for the first time.')

  if conv.logs[rev + 1].get_path_op('/%(trunk)s') is not None:
    raise Failure()


def split_branch():
  "branch created from both trunk and another branch"
  # See test-data/split-branch-cvsrepos/README.
  #
  # The conversion will fail if the bug is present, and
  # ensure_conversion will raise Failure.
  conv = ensure_conversion('split-branch')


def resync_misgroups():
  "resyncing should not misorder commit groups"
  # See test-data/resync-misgroups-cvsrepos/README.
  #
  # The conversion will fail if the bug is present, and
  # ensure_conversion will raise Failure.
  conv = ensure_conversion('resync-misgroups')


class TaggedBranchAndTrunk(Cvs2SvnTestCase):
  "allow tags with mixed trunk and branch sources"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'tagged-branch-n-trunk', **kw)

  def run(self):
    conv = self.ensure_conversion()

    tags = conv.symbols.get('tags', 'tags')

    a_path = conv.get_wc(tags, 'some-tag', 'a.txt')
    b_path = conv.get_wc(tags, 'some-tag', 'b.txt')
    if not (os.path.exists(a_path) and os.path.exists(b_path)):
      raise Failure()
    if (open(a_path, 'r').read().find('1.24') == -1) \
       or (open(b_path, 'r').read().find('1.5') == -1):
      raise Failure()


def enroot_race():
  "never use the rev-in-progress as a copy source"
  # See issue #1427 and r8544.
  conv = ensure_conversion('enroot-race')
  rev = 8
  conv.logs[rev].check_changes((
    ('/%(branches)s/mybranch (from /%(trunk)s:7)', 'A'),
    ('/%(branches)s/mybranch/proj/a.txt', 'D'),
    ('/%(branches)s/mybranch/proj/b.txt', 'D'),
    ))
  conv.logs[rev + 1].check_changes((
    ('/%(branches)s/mybranch/proj/c.txt', 'M'),
    ('/%(trunk)s/proj/a.txt', 'M'),
    ('/%(trunk)s/proj/b.txt', 'M'),
    ))


def enroot_race_obo():
  "do use the last completed rev as a copy source"
  conv = ensure_conversion('enroot-race-obo')
  conv.logs[3].check_change('/%(branches)s/BRANCH (from /%(trunk)s:2)', 'A')
  if not len(conv.logs) == 3:
    raise Failure()


class BranchDeleteFirst(Cvs2SvnTestCase):
  "correctly handle deletion as initial branch action"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'branch-delete-first', **kw)

  def run(self):
    # See test-data/branch-delete-first-cvsrepos/README.
    #
    # The conversion will fail if the bug is present, and
    # ensure_conversion would raise Failure.
    conv = self.ensure_conversion()

    branches = conv.symbols.get('branches', 'branches')

    # 'file' was deleted from branch-1 and branch-2, but not branch-3
    if conv.path_exists(branches, 'branch-1', 'file'):
      raise Failure()
    if conv.path_exists(branches, 'branch-2', 'file'):
      raise Failure()
    if not conv.path_exists(branches, 'branch-3', 'file'):
      raise Failure()


def nonascii_filenames():
  "non ascii files converted incorrectly"
  # see issue #1255

  # on a en_US.iso-8859-1 machine this test fails with
  # svn: Can't recode ...
  #
  # as described in the issue

  # on a en_US.UTF-8 machine this test fails with
  # svn: Malformed XML ...
  #
  # which means at least it fails. Unfortunately it won't fail
  # with the same error...

  # mangle current locale settings so we know we're not running
  # a UTF-8 locale (which does not exhibit this problem)
  current_locale = locale.getlocale()
  new_locale = 'en_US.ISO8859-1'
  locale_changed = None

  # From http://docs.python.org/lib/module-sys.html
  #
  # getfilesystemencoding():
  #
  # Return the name of the encoding used to convert Unicode filenames
  # into system file names, or None if the system default encoding is
  # used. The result value depends on the operating system:
  #
  # - On Windows 9x, the encoding is ``mbcs''.
  # - On Mac OS X, the encoding is ``utf-8''.
  # - On Unix, the encoding is the user's preference according to the
  #   result of nl_langinfo(CODESET), or None if the
  #   nl_langinfo(CODESET) failed.
  # - On Windows NT+, file names are Unicode natively, so no conversion is
  #   performed.

  # So we're going to skip this test on Mac OS X for now.
  if sys.platform == "darwin":
    raise svntest.Skip()

  try:
    # change locale to non-UTF-8 locale to generate latin1 names
    locale.setlocale(locale.LC_ALL, # this might be too broad?
                     new_locale)
    locale_changed = 1
  except locale.Error:
    raise svntest.Skip()

  try:
    srcrepos_path = os.path.join(test_data_dir,'main-cvsrepos')
    dstrepos_path = os.path.join(test_data_dir,'non-ascii-cvsrepos')
    if not os.path.exists(dstrepos_path):
      # create repos from existing main repos
      shutil.copytree(srcrepos_path, dstrepos_path)
      base_path = os.path.join(dstrepos_path, 'single-files')
      shutil.copyfile(os.path.join(base_path, 'twoquick,v'),
                      os.path.join(base_path, 'two\366uick,v'))
      new_path = os.path.join(dstrepos_path, 'single\366files')
      os.rename(base_path, new_path)

    # if ensure_conversion can generate a
    conv = ensure_conversion('non-ascii', args=['--encoding=latin1'])
  finally:
    if locale_changed:
      locale.setlocale(locale.LC_ALL, current_locale)
    svntest.main.safe_rmtree(dstrepos_path)


class UnicodeLog(Cvs2SvnTestCase):
  "log message contains unicode"

  def __init__(self, warning_re=None, **kw):
    Cvs2SvnTestCase.__init__(self, 'unicode-log', **kw)
    if warning_re is None:
      self.warning_re = None
    else:
      self.warning_re = re.compile(warning_re)

  def run(self):
    try:
      # ensure the availability of the "utf_8" encoding:
      u'a'.encode('utf_8').decode('utf_8')
    except LookupError:
      raise svntest.Skip()

    conv = self.ensure_conversion()

    if self.warning_re is not None:
      for line in conv.stdout:
        if self.warning_re.match(line):
          # We found the warning that we were looking for.  Exit happily.
          return
      else:
        raise Failure()


def vendor_branch_sameness():
  "avoid spurious changes for initial revs"
  conv = ensure_conversion('vendor-branch-sameness')

  # There are four files in the repository:
  #
  #    a.txt: Imported in the traditional way; 1.1 and 1.1.1.1 have
  #           the same contents, the file's default branch is 1.1.1,
  #           and both revisions are in state 'Exp'.
  #
  #    b.txt: Like a.txt, except that 1.1.1.1 has a real change from
  #           1.1 (the addition of a line of text).
  #
  #    c.txt: Like a.txt, except that 1.1.1.1 is in state 'dead'.
  #
  #    d.txt: This file was created by 'cvs add' instead of import, so
  #           it has only 1.1 -- no 1.1.1.1, and no default branch.
  #           The timestamp on the add is exactly the same as for the
  #           imports of the other files.
  #
  # (Log messages for the same revisions are the same in all files.)
  #
  # What we expect to see is everyone added in r1, then trunk/proj
  # copied in r2.  In the copy, only a.txt should be left untouched;
  # b.txt should be 'M'odified, and (for different reasons) c.txt and
  # d.txt should be 'D'eleted.

  rev = 2
  conv.logs[rev].check('Initial revision', (
    ('/%(trunk)s/proj', 'A'),
    ('/%(trunk)s/proj/a.txt', 'A'),
    ('/%(trunk)s/proj/b.txt', 'A'),
    ('/%(trunk)s/proj/c.txt', 'A'),
    ('/%(trunk)s/proj/d.txt', 'A'),
    ))

  conv.logs[rev + 1].check(sym_log_msg('vbranchA'), (
    ('/%(branches)s/vbranchA (from /%(trunk)s:2)', 'A'),
    ('/%(branches)s/vbranchA/proj/d.txt', 'D'),
    ))

  conv.logs[rev + 2].check('First vendor branch revision.', (
    ('/%(branches)s/vbranchA/proj/b.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/c.txt', 'D'),
    ))


def default_branches():
  "handle default branches correctly"
  conv = ensure_conversion('default-branches')

  # There are seven files in the repository:
  #
  #    a.txt:
  #       Imported in the traditional way, so 1.1 and 1.1.1.1 are the
  #       same.  Then 1.1.1.2 and 1.1.1.3 were imported, then 1.2
  #       committed (thus losing the default branch "1.1.1"), then
  #       1.1.1.4 was imported.  All vendor import release tags are
  #       still present.
  #
  #    b.txt:
  #       Like a.txt, but without rev 1.2.
  #
  #    c.txt:
  #       Exactly like b.txt, just s/b.txt/c.txt/ in content.
  #
  #    d.txt:
  #       Same as the previous two, but 1.1.1 branch is unlabeled.
  #
  #    e.txt:
  #       Same, but missing 1.1.1 label and all tags but 1.1.1.3.
  #
  #    deleted-on-vendor-branch.txt,v:
  #       Like b.txt and c.txt, except that 1.1.1.3 is state 'dead'.
  #
  #    added-then-imported.txt,v:
  #       Added with 'cvs add' to create 1.1, then imported with
  #       completely different contents to create 1.1.1.1, therefore
  #       never had a default branch.
  #

  conv.logs[18].check(sym_log_msg('vtag-4',1), (
    ('/%(tags)s/vtag-4 (from /%(branches)s/vbranchA:16)', 'A'),
    ('/%(tags)s/vtag-4/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:16)', 'A'),
    ))

  conv.logs[6].check(sym_log_msg('vtag-1',1), (
    ('/%(tags)s/vtag-1 (from /%(branches)s/vbranchA:5)', 'A'),
    ('/%(tags)s/vtag-1/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:5)', 'A'),
    ))

  conv.logs[9].check(sym_log_msg('vtag-2',1), (
    ('/%(tags)s/vtag-2 (from /%(branches)s/vbranchA:7)', 'A'),
    ('/%(tags)s/vtag-2/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:7)', 'A'),
    ))

  conv.logs[12].check(sym_log_msg('vtag-3',1), (
    ('/%(tags)s/vtag-3 (from /%(branches)s/vbranchA:10)', 'A'),
    ('/%(tags)s/vtag-3/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:10)', 'A'),
    ('/%(tags)s/vtag-3/proj/e.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/e.txt:10)', 'A'),
    ))

  conv.logs[17].check("This commit was generated by cvs2svn "
                      "to compensate for changes in r16,", (
    ('/%(trunk)s/proj/b.txt '
     '(from /%(branches)s/vbranchA/proj/b.txt:16)', 'R'),
    ('/%(trunk)s/proj/c.txt '
     '(from /%(branches)s/vbranchA/proj/c.txt:16)', 'R'),
    ('/%(trunk)s/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:16)', 'R'),
    ('/%(trunk)s/proj/deleted-on-vendor-branch.txt '
     '(from /%(branches)s/vbranchA/proj/deleted-on-vendor-branch.txt:16)',
     'A'),
    ('/%(trunk)s/proj/e.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/e.txt:16)', 'R'),
    ))

  conv.logs[16].check("Import (vbranchA, vtag-4).", (
    ('/%(branches)s/unlabeled-1.1.1/proj/d.txt', 'M'),
    ('/%(branches)s/unlabeled-1.1.1/proj/e.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/a.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/added-then-imported.txt', 'M'), # CHECK!!!
    ('/%(branches)s/vbranchA/proj/b.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/c.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/deleted-on-vendor-branch.txt', 'A'),
    ))

  conv.logs[15].check(sym_log_msg('vbranchA'), (
    ('/%(branches)s/vbranchA/proj/added-then-imported.txt '
    '(from /%(trunk)s/proj/added-then-imported.txt:14)', 'A'),
    ))

  conv.logs[14].check("Add a file to the working copy.", (
    ('/%(trunk)s/proj/added-then-imported.txt', 'A'),
    ))

  conv.logs[13].check("First regular commit, to a.txt, on vtag-3.", (
    ('/%(trunk)s/proj/a.txt', 'M'),
    ))

  conv.logs[11].check("This commit was generated by cvs2svn "
                      "to compensate for changes in r10,", (
    ('/%(trunk)s/proj/a.txt '
     '(from /%(branches)s/vbranchA/proj/a.txt:10)', 'R'),
    ('/%(trunk)s/proj/b.txt '
     '(from /%(branches)s/vbranchA/proj/b.txt:10)', 'R'),
    ('/%(trunk)s/proj/c.txt '
     '(from /%(branches)s/vbranchA/proj/c.txt:10)', 'R'),
    ('/%(trunk)s/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:10)', 'R'),
    ('/%(trunk)s/proj/deleted-on-vendor-branch.txt', 'D'),
    ('/%(trunk)s/proj/e.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/e.txt:10)', 'R'),
    ))

  conv.logs[10].check("Import (vbranchA, vtag-3).", (
    ('/%(branches)s/unlabeled-1.1.1/proj/d.txt', 'M'),
    ('/%(branches)s/unlabeled-1.1.1/proj/e.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/a.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/b.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/c.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/deleted-on-vendor-branch.txt', 'D'),
    ))

  conv.logs[8].check("This commit was generated by cvs2svn "
                      "to compensate for changes in r7,", (
    ('/%(trunk)s/proj/a.txt '
     '(from /%(branches)s/vbranchA/proj/a.txt:7)', 'R'),
    ('/%(trunk)s/proj/b.txt '
     '(from /%(branches)s/vbranchA/proj/b.txt:7)', 'R'),
    ('/%(trunk)s/proj/c.txt '
     '(from /%(branches)s/vbranchA/proj/c.txt:7)', 'R'),
    ('/%(trunk)s/proj/d.txt '
     '(from /%(branches)s/unlabeled-1.1.1/proj/d.txt:7)', 'R'),
    ('/%(trunk)s/proj/deleted-on-vendor-branch.txt '
     '(from /%(branches)s/vbranchA/proj/deleted-on-vendor-branch.txt:7)',
     'R'),
    ('/%(trunk)s/proj/e.txt '
    '(from /%(branches)s/unlabeled-1.1.1/proj/e.txt:7)', 'R'),
    ))

  conv.logs[7].check("Import (vbranchA, vtag-2).", (
    ('/%(branches)s/unlabeled-1.1.1/proj/d.txt', 'M'),
    ('/%(branches)s/unlabeled-1.1.1/proj/e.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/a.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/b.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/c.txt', 'M'),
    ('/%(branches)s/vbranchA/proj/deleted-on-vendor-branch.txt', 'M'),
    ))

  conv.logs[5].check("Import (vbranchA, vtag-1).", ())

  conv.logs[4].check(sym_log_msg('vbranchA'), (
    ('/%(branches)s/vbranchA (from /%(trunk)s:2)', 'A'),
    ('/%(branches)s/vbranchA/proj/d.txt', 'D'),
    ('/%(branches)s/vbranchA/proj/e.txt', 'D'),
    ))

  conv.logs[3].check(sym_log_msg('unlabeled-1.1.1'), (
    ('/%(branches)s/unlabeled-1.1.1 (from /%(trunk)s:2)', 'A'),
    ('/%(branches)s/unlabeled-1.1.1/proj/a.txt', 'D'),
    ('/%(branches)s/unlabeled-1.1.1/proj/b.txt', 'D'),
    ('/%(branches)s/unlabeled-1.1.1/proj/c.txt', 'D'),
    ('/%(branches)s/unlabeled-1.1.1/proj/deleted-on-vendor-branch.txt', 'D'),
    ))

  conv.logs[2].check("Initial revision", (
    ('/%(trunk)s/proj', 'A'),
    ('/%(trunk)s/proj/a.txt', 'A'),
    ('/%(trunk)s/proj/b.txt', 'A'),
    ('/%(trunk)s/proj/c.txt', 'A'),
    ('/%(trunk)s/proj/d.txt', 'A'),
    ('/%(trunk)s/proj/deleted-on-vendor-branch.txt', 'A'),
    ('/%(trunk)s/proj/e.txt', 'A'),
    ))


def compose_tag_three_sources():
  "compose a tag from three sources"
  conv = ensure_conversion('compose-tag-three-sources')

  conv.logs[2].check("Add on trunk", (
    ('/%(trunk)s/tagged-on-trunk-1.2-a', 'A'),
    ('/%(trunk)s/tagged-on-trunk-1.2-b', 'A'),
    ('/%(trunk)s/tagged-on-trunk-1.1', 'A'),
    ('/%(trunk)s/tagged-on-b1', 'A'),
    ('/%(trunk)s/tagged-on-b2', 'A'),
    ))

  conv.logs[3].check(sym_log_msg('b1'), (
    ('/%(branches)s/b1 (from /%(trunk)s:2)', 'A'),
    ))

  conv.logs[4].check(sym_log_msg('b2'), (
    ('/%(branches)s/b2 (from /%(trunk)s:2)', 'A'),
    ))

  conv.logs[5].check("Commit on branch b1", (
    ('/%(branches)s/b1/tagged-on-trunk-1.2-a', 'M'),
    ('/%(branches)s/b1/tagged-on-trunk-1.2-b', 'M'),
    ('/%(branches)s/b1/tagged-on-trunk-1.1', 'M'),
    ('/%(branches)s/b1/tagged-on-b1', 'M'),
    ('/%(branches)s/b1/tagged-on-b2', 'M'),
    ))

  conv.logs[6].check("Commit on branch b2", (
    ('/%(branches)s/b2/tagged-on-trunk-1.2-a', 'M'),
    ('/%(branches)s/b2/tagged-on-trunk-1.2-b', 'M'),
    ('/%(branches)s/b2/tagged-on-trunk-1.1', 'M'),
    ('/%(branches)s/b2/tagged-on-b1', 'M'),
    ('/%(branches)s/b2/tagged-on-b2', 'M'),
    ))

  conv.logs[7].check("Commit again on trunk", (
    ('/%(trunk)s/tagged-on-trunk-1.2-a', 'M'),
    ('/%(trunk)s/tagged-on-trunk-1.2-b', 'M'),
    ('/%(trunk)s/tagged-on-trunk-1.1', 'M'),
    ('/%(trunk)s/tagged-on-b1', 'M'),
    ('/%(trunk)s/tagged-on-b2', 'M'),
    ))

  conv.logs[8].check(sym_log_msg('T',1), (
    ('/%(tags)s/T (from /%(trunk)s:7)', 'A'),
    ('/%(tags)s/T/tagged-on-b2 (from /%(branches)s/b2/tagged-on-b2:7)', 'R'),
    ('/%(tags)s/T/tagged-on-trunk-1.1 '
     '(from /%(trunk)s/tagged-on-trunk-1.1:2)', 'R'),
    ('/%(tags)s/T/tagged-on-b1 (from /%(branches)s/b1/tagged-on-b1:7)', 'R'),
    ))


def pass5_when_to_fill():
  "reserve a svn revnum for a fill only when required"
  # The conversion will fail if the bug is present, and
  # ensure_conversion would raise Failure.
  conv = ensure_conversion('pass5-when-to-fill')


class EmptyTrunk(Cvs2SvnTestCase):
  "don't break when the trunk is empty"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'empty-trunk', **kw)

  def run(self):
    # The conversion will fail if the bug is present, and
    # ensure_conversion would raise Failure.
    conv = self.ensure_conversion()


def no_spurious_svn_commits():
  "ensure that we don't create any spurious commits"
  conv = ensure_conversion('phoenix')

  # Check spurious commit that could be created in
  # SVNCommitCreator._pre_commit()
  #
  #   (When you add a file on a branch, CVS creates a trunk revision
  #   in state 'dead'.  If the log message of that commit is equal to
  #   the one that CVS generates, we do not ever create a 'fill'
  #   SVNCommit for it.)
  #
  # and spurious commit that could be created in
  # SVNCommitCreator._commit()
  #
  #   (When you add a file on a branch, CVS creates a trunk revision
  #   in state 'dead'.  If the log message of that commit is equal to
  #   the one that CVS generates, we do not create a primary SVNCommit
  #   for it.)
  conv.logs[18].check('File added on branch xiphophorus', (
    ('/%(branches)s/xiphophorus/added-on-branch.txt', 'A'),
    ))

  # Check to make sure that a commit *is* generated:
  #   (When you add a file on a branch, CVS creates a trunk revision
  #   in state 'dead'.  If the log message of that commit is NOT equal
  #   to the one that CVS generates, we create a primary SVNCommit to
  #   serve as a home for the log message in question.
  conv.logs[19].check('file added-on-branch2.txt was initially added on '
            + 'branch xiphophorus,\nand this log message was tweaked', ())

  # Check spurious commit that could be created in
  # SVNCommitCreator._commit_symbols().  (We shouldn't consider a
  # CVSRevision whose op is OP_DEAD as a candidate for the
  # LastSymbolicNameDatabase.)
  conv.logs[20].check('This file was also added on branch xiphophorus,', (
    ('/%(branches)s/xiphophorus/added-on-branch2.txt', 'A'),
    ))


class PeerPathPruning(Cvs2SvnTestCase):
  "make sure that filling prunes paths correctly"

  def __init__(self, **kw):
    Cvs2SvnTestCase.__init__(self, 'peer-path-pruning', **kw)

  def run(self):
    conv = self.ensure_conversion()
    conv.logs[8].check(sym_log_msg('BRANCH'), (
      ('/%(branches)s/BRANCH (from /%(trunk)s:6)', 'A'),
      ('/%(branches)s/BRANCH/bar', 'D'),
      ('/%(branches)s/BRANCH/foo (from /%(trunk)s/foo:7)', 'R'),
      ))


def invalid_closings_on_trunk():
  "verify correct revs are copied to default branches"
  # The conversion will fail if the bug is present, and
  # ensure_conversion would raise Failure.
  conv = ensure_conversion('invalid-closings-on-trunk')


def individual_passes():
  "run each pass individually"
  conv = ensure_conversion('main')
  conv2 = ensure_conversion('main', passbypass=1)

  if conv.logs != conv2.logs:
    raise Failure()


def resync_bug():
  "reveal a big bug in our resync algorithm"
  # This will fail if the bug is present
  conv = ensure_conversion('resync-bug')


def branch_from_default_branch():
  "reveal a bug in our default branch detection code"
  conv = ensure_conversion('branch-from-default-branch')

  # This revision will be a default branch synchronization only
  # if cvs2svn is correctly determining default branch revisions.
  #
  # The bug was that cvs2svn was treating revisions on branches off of
  # default branches as default branch revisions, resulting in
  # incorrectly regarding the branch off of the default branch as a
  # non-trunk default branch.  Crystal clear?  I thought so.  See
  # issue #42 for more incoherent blathering.
  conv.logs[6].check("This commit was generated by cvs2svn", (
    ('/%(trunk)s/proj/file.txt '
     '(from /%(branches)s/upstream/proj/file.txt:5)', 'R'),
    ))


def file_in_attic_too():
  "die if a file exists in and out of the attic"
  try:
    ensure_conversion(
        'file-in-attic-too',
        error_re=(
            r'A CVS repository cannot contain both '
            r'(.*)' + re.escape(os.sep) + r'(.*) '
            + r'and '
            r'\1' + re.escape(os.sep) + r'Attic' + re.escape(os.sep) + r'\2'))
    raise MissingErrorException()
  except Failure:
    pass


def retain_file_in_attic_too():
  "test --retain-conflicting-attic-files option"
  conv = ensure_conversion(
      'file-in-attic-too', args=['--retain-conflicting-attic-files'])
  if not conv.path_exists('trunk', 'file.txt'):
    raise Failure()
  if not conv.path_exists('trunk', 'Attic', 'file.txt'):
    raise Failure()


def symbolic_name_filling_guide():
  "reveal a big bug in our SymbolFillingGuide"
  # This will fail if the bug is present
  conv = ensure_conversion('symbolic-name-overfill')


# Helpers for tests involving file contents and properties.

class NodeTreeWalkException:
  "Exception class for node tree traversals."
  pass

def node_for_path(node, path):
  "In the tree rooted under SVNTree NODE, return the node at PATH."
  if node.name != '__SVN_ROOT_NODE':
    raise NodeTreeWalkException()
  path = path.strip('/')
  components = path.split('/')
  for component in components:
    node = svntest.tree.get_child(node, component)
  return node

# Helper for tests involving properties.
def props_for_path(node, path):
  "In the tree rooted under SVNTree NODE, return the prop dict for PATH."
  return node_for_path(node, path).props


class EOLMime(Cvs2SvnPropertiesTestCase):
  """eol settings and mime types together

  The files are as follows:

      trunk/foo.txt: no -kb, mime file says nothing.
      trunk/foo.xml: no -kb, mime file says text.
      trunk/foo.zip: no -kb, mime file says non-text.
      trunk/foo.bin: has -kb, mime file says nothing.
      trunk/foo.csv: has -kb, mime file says text.
      trunk/foo.dbf: has -kb, mime file says non-text.
  """

  def __init__(self, args, **kw):
    # TODO: It's a bit klugey to construct this path here.  But so far
    # there's only one test with a mime.types file.  If we have more,
    # we should abstract this into some helper, which would be located
    # near ensure_conversion().  Note that it is a convention of this
    # test suite for a mime.types file to be located in the top level
    # of the CVS repository to which it applies.
    self.mime_path = os.path.join(
        test_data_dir, 'eol-mime-cvsrepos', 'mime.types')

    Cvs2SvnPropertiesTestCase.__init__(
        self, 'eol-mime',
        props_to_test=['svn:eol-style', 'svn:mime-type', 'svn:keywords'],
        args=['--mime-types=%s' % self.mime_path] + args,
        **kw)


# We do four conversions.  Each time, we pass --mime-types=FILE with
# the same FILE, but vary --no-default-eol and --eol-from-mime-type.
# Thus there's one conversion with neither flag, one with just the
# former, one with just the latter, and one with both.


# Neither --no-default-eol nor --eol-from-mime-type:
eol_mime1 = EOLMime(
    variant=1,
    args=[],
    expected_props=[
        ('trunk/foo.txt', ['native', None, KEYWORDS]),
        ('trunk/foo.xml', ['native', 'text/xml', KEYWORDS]),
        ('trunk/foo.zip', ['native', 'application/zip', KEYWORDS]),
        ('trunk/foo.bin', [None, 'application/octet-stream', None]),
        ('trunk/foo.csv', [None, 'text/csv', None]),
        ('trunk/foo.dbf', [None, 'application/what-is-dbf', None]),
        ])


# Just --no-default-eol, not --eol-from-mime-type:
eol_mime2 = EOLMime(
    variant=2,
    args=['--no-default-eol'],
    expected_props=[
        ('trunk/foo.txt', [None, None, None]),
        ('trunk/foo.xml', [None, 'text/xml', None]),
        ('trunk/foo.zip', [None, 'application/zip', None]),
        ('trunk/foo.bin', [None, 'application/octet-stream', None]),
        ('trunk/foo.csv', [None, 'text/csv', None]),
        ('trunk/foo.dbf', [None, 'application/what-is-dbf', None]),
        ])


# Just --eol-from-mime-type, not --no-default-eol:
eol_mime3 = EOLMime(
    variant=3,
    args=['--eol-from-mime-type'],
    expected_props=[
        ('trunk/foo.txt', ['native', None, KEYWORDS]),
        ('trunk/foo.xml', ['native', 'text/xml', KEYWORDS]),
        ('trunk/foo.zip', [None, 'application/zip', None]),
        ('trunk/foo.bin', [None, 'application/octet-stream', None]),
        ('trunk/foo.csv', [None, 'text/csv', None]),
        ('trunk/foo.dbf', [None, 'application/what-is-dbf', None]),
        ])


# Both --no-default-eol and --eol-from-mime-type:
eol_mime4 = EOLMime(
    variant=4,
    args=['--eol-from-mime-type', '--no-default-eol'],
    expected_props=[
        ('trunk/foo.txt', [None, None, None]),
        ('trunk/foo.xml', ['native', 'text/xml', KEYWORDS]),
        ('trunk/foo.zip', [None, 'application/zip', None]),
        ('trunk/foo.bin', [None, 'application/octet-stream', None]),
        ('trunk/foo.csv', [None, 'text/csv', None]),
        ('trunk/foo.dbf', [None, 'application/what-is-dbf', None]),
        ])


cvs_revnums_off = Cvs2SvnPropertiesTestCase(
    'eol-mime',
    description='test non-setting of cvs2svn:cvs-rev property',
    args=[],
    props_to_test=['cvs2svn:cvs-rev'],
    expected_props=[
        ('trunk/foo.txt', [None]),
        ('trunk/foo.xml', [None]),
        ('trunk/foo.zip', [None]),
        ('trunk/foo.bin', [None]),
        ('trunk/foo.csv', [None]),
        ('trunk/foo.dbf', [None]),
        ])


cvs_revnums_on = Cvs2SvnPropertiesTestCase(
    'eol-mime',
    description='test setting of cvs2svn:cvs-rev property',
    args=['--cvs-revnums'],
    props_to_test=['cvs2svn:cvs-rev'],
    expected_props=[
        ('trunk/foo.txt', ['1.2']),
        ('trunk/foo.xml', ['1.2']),
        ('trunk/foo.zip', ['1.2']),
        ('trunk/foo.bin', ['1.2']),
        ('trunk/foo.csv', ['1.2']),
        ('trunk/foo.dbf', ['1.2']),
        ])


keywords = Cvs2SvnPropertiesTestCase(
    'keywords',
    description='test setting of svn:keywords property among others',
    props_to_test=['svn:keywords', 'svn:eol-style', 'svn:mime-type'],
    expected_props=[
        ('trunk/foo.default', [KEYWORDS, 'native', None]),
        ('trunk/foo.kkvl', [KEYWORDS, 'native', None]),
        ('trunk/foo.kkv', [KEYWORDS, 'native', None]),
        ('trunk/foo.kb', [None, None, 'application/octet-stream']),
        ('trunk/foo.kk', [None, 'native', None]),
        ('trunk/foo.ko', [None, 'native', None]),
        ('trunk/foo.kv', [None, 'native', None]),
        ])


def ignore():
  "test setting of svn:ignore property"
  conv = ensure_conversion('cvsignore')
  wc_tree = conv.get_wc_tree()
  topdir_props = props_for_path(wc_tree, 'trunk/proj')
  subdir_props = props_for_path(wc_tree, '/trunk/proj/subdir')

  if topdir_props['svn:ignore'] != \
     '*.idx\n*.aux\n*.dvi\n*.log\nfoo\nbar\nbaz\nqux\n\n':
    raise Failure()

  if subdir_props['svn:ignore'] != \
     '*.idx\n*.aux\n*.dvi\n*.log\nfoo\nbar\nbaz\nqux\n\n':
    raise Failure()


def requires_cvs():
  "test that CVS can still do what RCS can't"
  # See issues 4, 11, 29 for the bugs whose regression we're testing for.
  conv = ensure_conversion('requires-cvs', args=["--use-cvs"])

  atsign_contents = file(conv.get_wc("trunk", "atsign-add")).read()
  cl_contents = file(conv.get_wc("trunk", "client_lock.idl")).read()

  if atsign_contents[-1:] == "@":
    raise Failure()
  if cl_contents.find("gregh\n//\n//Integration for locks") < 0:
    raise Failure()

  if not (conv.logs[21].author == "William Lyon Phelps III" and
          conv.logs[20].author == "j random"):
    raise Failure()


def questionable_branch_names():
  "test that we can handle weird branch names"
  conv = ensure_conversion('questionable-symbols')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual branch paths, too, but the main thing is to know that the
  # conversion doesn't fail.


def questionable_tag_names():
  "test that we can handle weird tag names"
  conv = ensure_conversion('questionable-symbols')
  for tag_name in ['Tag_A', 'TagWith--Backslash_E', 'TagWith++Slash_Z']:
    conv.find_tag_log(tag_name).check(sym_log_msg(tag_name,1), (
      ('/%(tags)s/' + tag_name + ' (from /trunk:8)', 'A'),
      ))


def revision_reorder_bug():
  "reveal a bug that reorders file revisions"
  conv = ensure_conversion('revision-reorder-bug')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def exclude():
  "test that exclude really excludes everything"
  conv = ensure_conversion('main', args=['--exclude=.*'])
  for log in conv.logs.values():
    for item in log.changed_paths.keys():
      if item.startswith('/branches/') or item.startswith('/tags/'):
        raise Failure()


def vendor_branch_delete_add():
  "add trunk file that was deleted on vendor branch"
  # This will error if the bug is present
  conv = ensure_conversion('vendor-branch-delete-add')


def resync_pass2_pull_forward():
  "ensure pass2 doesn't pull rev too far forward"
  conv = ensure_conversion('resync-pass2-pull-forward')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def native_eol():
  "only LFs for svn:eol-style=native files"
  conv = ensure_conversion('native-eol')
  lines = run_program(svntest.main.svnadmin_binary, None, 'dump', '-q',
                      conv.repos)
  # Verify that all files in the dump have LF EOLs.  We're actually
  # testing the whole dump file, but the dump file itself only uses
  # LF EOLs, so we're safe.
  for line in lines:
    if line[-1] != '\n' or line[:-1].find('\r') != -1:
      raise Failure()


def double_fill():
  "reveal a bug that created a branch twice"
  conv = ensure_conversion('double-fill')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def resync_pass2_push_backward():
  "ensure pass2 doesn't push rev too far backward"
  conv = ensure_conversion('resync-pass2-push-backward')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def double_add():
  "reveal a bug that added a branch file twice"
  conv = ensure_conversion('double-add')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def bogus_branch_copy():
  "reveal a bug that copies a branch file wrongly"
  conv = ensure_conversion('bogus-branch-copy')
  # If the conversion succeeds, then we're okay.  We could check the
  # actual revisions, too, but the main thing is to know that the
  # conversion doesn't fail.


def nested_ttb_directories():
  "require error if ttb directories are not disjoint"
  opts_list = [
    {'trunk' : 'a', 'branches' : 'a',},
    {'trunk' : 'a', 'tags' : 'a',},
    {'branches' : 'a', 'tags' : 'a',},
    # This option conflicts with the default trunk path:
    {'branches' : 'trunk',},
    # Try some nested directories:
    {'trunk' : 'a', 'branches' : 'a/b',},
    {'trunk' : 'a/b', 'tags' : 'a/b/c/d',},
    {'branches' : 'a', 'tags' : 'a/b',},
    ]

  for opts in opts_list:
    try:
      ensure_conversion(
          'main', error_re=r'.*paths .* and .* are not disjoint\.', **opts
          )
      raise MissingErrorException()
    except Failure:
      pass


class AutoProps(Cvs2SvnPropertiesTestCase):
  """Test auto-props.

  The files are as follows:

      trunk/foo.txt: no -kb, mime auto-prop says nothing.
      trunk/foo.xml: no -kb, mime auto-prop says text and eol-style=CRLF.
      trunk/foo.zip: no -kb, mime auto-prop says non-text.
      trunk/foo.bin: has -kb, mime auto-prop says nothing.
      trunk/foo.csv: has -kb, mime auto-prop says text and eol-style=CRLF.
      trunk/foo.dbf: has -kb, mime auto-prop says non-text.
      trunk/foo.UPCASE1: no -kb, no mime type.
      trunk/foo.UPCASE2: no -kb, no mime type.
  """

  def __init__(self, args, **kw):
    ### TODO: It's a bit klugey to construct this path here.  See also
    ### the comment in eol_mime().
    auto_props_path = os.path.join(
        test_data_dir, 'eol-mime-cvsrepos', 'auto-props')

    Cvs2SvnPropertiesTestCase.__init__(
        self, 'eol-mime',
        props_to_test=[
            'myprop', 'svn:eol-style', 'svn:mime-type', 'svn:keywords'],
        args=[
            '--auto-props=%s' % auto_props_path,
            '--eol-from-mime-type'
            ] + args,
        **kw)


auto_props_ignore_case = AutoProps(
    description="test auto-props (case-insensitive)",
    args=['--auto-props-ignore-case'],
    expected_props=[
        ('trunk/foo.txt', ['txt', 'native', None, KEYWORDS]),
        ('trunk/foo.xml', ['xml', 'CRLF', 'text/xml', KEYWORDS]),
        ('trunk/foo.zip', ['zip', None, 'application/zip', None]),
        ('trunk/foo.bin', ['bin', None, 'application/octet-stream', None]),
        ('trunk/foo.csv', ['csv', 'CRLF', 'text/csv', None]),
        ('trunk/foo.dbf', ['dbf', None, 'application/what-is-dbf', None]),
        ('trunk/foo.UPCASE1', ['UPCASE1', 'native', None, KEYWORDS]),
        ('trunk/foo.UPCASE2', ['UPCASE2', 'native', None, KEYWORDS]),
        ])


auto_props = AutoProps(
    description="test auto-props (case-sensitive)",
    args=[],
    expected_props=[
        ('trunk/foo.txt', ['txt', 'native', None, KEYWORDS]),
        ('trunk/foo.xml', ['xml', 'CRLF', 'text/xml', KEYWORDS]),
        ('trunk/foo.zip', ['zip', None, 'application/zip', None]),
        ('trunk/foo.bin', ['bin', None, 'application/octet-stream', None]),
        ('trunk/foo.csv', ['csv', 'CRLF', 'text/csv', None]),
        ('trunk/foo.dbf', ['dbf', None, 'application/what-is-dbf', None]),
        ('trunk/foo.UPCASE1', ['UPCASE1', 'native', None, KEYWORDS]),
        ('trunk/foo.UPCASE2', [None, 'native', None, KEYWORDS]),
        ])


def ctrl_char_in_filename():
  "do not allow control characters in filenames"

  try:
    srcrepos_path = os.path.join(test_data_dir,'main-cvsrepos')
    dstrepos_path = os.path.join(test_data_dir,'ctrl-char-filename-cvsrepos')
    if os.path.exists(dstrepos_path):
      svntest.main.safe_rmtree(dstrepos_path)

    # create repos from existing main repos
    shutil.copytree(srcrepos_path, dstrepos_path)
    base_path = os.path.join(dstrepos_path, 'single-files')
    try:
      shutil.copyfile(os.path.join(base_path, 'twoquick,v'),
                      os.path.join(base_path, 'two\rquick,v'))
    except:
      # Operating systems that don't allow control characters in
      # filenames will hopefully have thrown an exception; in that
      # case, just skip this test.
      raise svntest.Skip()

    try:
      conv = ensure_conversion(
          'ctrl-char-filename',
          error_re=(r'.*Character .* in filename .* '
                    r'is not supported by subversion\.'),
          )
      raise MissingErrorException()
    except Failure:
      pass
  finally:
    svntest.main.safe_rmtree(dstrepos_path)


def commit_dependencies():
  "interleaved and multi-branch commits to same files"
  conv = ensure_conversion("commit-dependencies")
  conv.logs[2].check('adding', (
    ('/%(trunk)s/interleaved', 'A'),
    ('/%(trunk)s/interleaved/file1', 'A'),
    ('/%(trunk)s/interleaved/file2', 'A'),
    ))
  conv.logs[3].check('big commit', (
    ('/%(trunk)s/interleaved/file1', 'M'),
    ('/%(trunk)s/interleaved/file2', 'M'),
    ))
  conv.logs[4].check('dependant small commit', (
    ('/%(trunk)s/interleaved/file1', 'M'),
    ))
  conv.logs[5].check('adding', (
    ('/%(trunk)s/multi-branch', 'A'),
    ('/%(trunk)s/multi-branch/file1', 'A'),
    ('/%(trunk)s/multi-branch/file2', 'A'),
    ))
  conv.logs[6].check(sym_log_msg("branch"), (
    ('/%(branches)s/branch (from /%(trunk)s:5)', 'A'),
    ('/%(branches)s/branch/interleaved', 'D'),
    ))
  conv.logs[7].check('multi-branch-commit', (
    ('/%(trunk)s/multi-branch/file1', 'M'),
    ('/%(trunk)s/multi-branch/file2', 'M'),
    ('/%(branches)s/branch/multi-branch/file1', 'M'),
    ('/%(branches)s/branch/multi-branch/file2', 'M'),
    ))


def double_branch_delete():
  "fill branches before modifying files on them"
  conv = ensure_conversion('double-branch-delete')

  # Test for issue #102.  The file IMarshalledValue.java is branched,
  # deleted, readded on the branch, and then deleted again.  If the
  # fill for the file on the branch is postponed until after the
  # modification, the file will end up live on the branch instead of
  # dead!  Make sure it happens at the right time.

  conv.logs[6].check(sym_log_msg('Branch_4_0'), (
    ('/%(branches)s/Branch_4_0/IMarshalledValue.java '
     '(from /%(trunk)s/IMarshalledValue.java:5)', 'A'),
    ));

  conv.logs[7].check('file IMarshalledValue.java was added on branch', (
    ('/%(branches)s/Branch_4_0/IMarshalledValue.java', 'D'),
    ));

  conv.logs[8].check('JBAS-2436 - Adding LGPL Header2', (
    ('/%(branches)s/Branch_4_0/IMarshalledValue.java', 'A'),
    ));


def symbol_mismatches():
  "error for conflicting tag/branch"

  try:
    ensure_conversion('symbol-mess')
    raise MissingErrorException()
  except Failure:
    pass


def force_symbols():
  "force symbols to be tags/branches"

  conv = ensure_conversion(
      'symbol-mess',
      args=['--force-branch=MOSTLY_BRANCH', '--force-tag=MOSTLY_TAG'])
  if conv.path_exists('tags', 'BRANCH') \
     or not conv.path_exists('branches', 'BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'TAG') \
     or conv.path_exists('branches', 'TAG'):
     raise Failure()
  if conv.path_exists('tags', 'MOSTLY_BRANCH') \
     or not conv.path_exists('branches', 'MOSTLY_BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'MOSTLY_TAG') \
     or conv.path_exists('branches', 'MOSTLY_TAG'):
     raise Failure()


def commit_blocks_tags():
  "commit prevents forced tag"

  basic_args = ['--force-branch=MOSTLY_BRANCH', '--force-tag=MOSTLY_TAG']
  try:
    ensure_conversion(
        'symbol-mess',
        args=(basic_args + ['--force-tag=BRANCH_WITH_COMMIT']))
    raise MissingErrorException()
  except Failure:
    pass


def blocked_excludes():
  "error for blocked excludes"

  basic_args = ['--force-branch=MOSTLY_BRANCH', '--force-tag=MOSTLY_TAG']
  for blocker in ['BRANCH', 'COMMIT', 'UNNAMED']:
    try:
      ensure_conversion(
          'symbol-mess',
          args=(basic_args + ['--exclude=BLOCKED_BY_%s' % blocker]))
      raise MissingErrorException()
    except Failure:
      pass


def unblock_blocked_excludes():
  "excluding blocker removes blockage"

  basic_args = ['--force-branch=MOSTLY_BRANCH', '--force-tag=MOSTLY_TAG']
  for blocker in ['BRANCH', 'COMMIT']:
    ensure_conversion(
        'symbol-mess',
        args=(basic_args + ['--exclude=BLOCKED_BY_%s' % blocker,
                            '--exclude=BLOCKING_%s' % blocker]))


def regexp_force_symbols():
  "force symbols via regular expressions"

  conv = ensure_conversion(
      'symbol-mess',
      args=['--force-branch=MOST.*_BRANCH', '--force-tag=MOST.*_TAG'])
  if conv.path_exists('tags', 'MOSTLY_BRANCH') \
     or not conv.path_exists('branches', 'MOSTLY_BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'MOSTLY_TAG') \
     or conv.path_exists('branches', 'MOSTLY_TAG'):
     raise Failure()


def heuristic_symbol_default():
  "test 'heuristic' symbol default"

  conv = ensure_conversion(
      'symbol-mess', args=['--symbol-default=heuristic'])
  if conv.path_exists('tags', 'MOSTLY_BRANCH') \
     or not conv.path_exists('branches', 'MOSTLY_BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'MOSTLY_TAG') \
     or conv.path_exists('branches', 'MOSTLY_TAG'):
     raise Failure()


def branch_symbol_default():
  "test 'branch' symbol default"

  conv = ensure_conversion(
      'symbol-mess', args=['--symbol-default=branch'])
  if conv.path_exists('tags', 'MOSTLY_BRANCH') \
     or not conv.path_exists('branches', 'MOSTLY_BRANCH'):
     raise Failure()
  if conv.path_exists('tags', 'MOSTLY_TAG') \
     or not conv.path_exists('branches', 'MOSTLY_TAG'):
     raise Failure()


def tag_symbol_default():
  "test 'tag' symbol default"

  conv = ensure_conversion(
      'symbol-mess', args=['--symbol-default=tag'])
  if not conv.path_exists('tags', 'MOSTLY_BRANCH') \
     or conv.path_exists('branches', 'MOSTLY_BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'MOSTLY_TAG') \
     or conv.path_exists('branches', 'MOSTLY_TAG'):
     raise Failure()


def symbol_transform():
  "test --symbol-transform"

  conv = ensure_conversion(
      'symbol-mess',
      args=[
          '--symbol-default=heuristic',
          '--symbol-transform=^BRANCH:branch',
          '--symbol-transform=^TAG:tag',
          '--symbol-transform=^MOSTLY_(BRANCH|TAG):MOSTLY.\\1',
          ])
  if not conv.path_exists('branches', 'branch'):
     raise Failure()
  if not conv.path_exists('tags', 'tag'):
     raise Failure()
  if not conv.path_exists('branches', 'MOSTLY.BRANCH'):
     raise Failure()
  if not conv.path_exists('tags', 'MOSTLY.TAG'):
     raise Failure()


def issue_99():
  "test problem from issue 99"

  conv = ensure_conversion('issue-99')


def issue_100():
  "test problem from issue 100"

  conv = ensure_conversion('issue-100')
  file1 = conv.get_wc('trunk', 'file1.txt')
  if file(file1).read() != 'file1.txt<1.2>\n':
    raise Failure()


def issue_106():
  "test problem from issue 106"

  conv = ensure_conversion('issue-106')


def options_option():
  "use of the --options option"

  conv = ensure_conversion('main', options_file='cvs2svn.options')


def tag_with_no_revision():
  "tag defined but revision is deleted"

  conv = ensure_conversion('tag-with-no-revision')


def delete_cvsignore():
  "svn:ignore should vanish when .cvsignore does"

  # This is issue #81.

  conv = ensure_conversion('delete-cvsignore')

  wc_tree = conv.get_wc_tree()
  props = props_for_path(wc_tree, 'trunk/proj')

  if props.has_key('svn:ignore'):
    raise Failure()


def repeated_deltatext():
  "ignore repeated deltatext blocks with warning"

  conv = ensure_conversion(
      'repeated-deltatext',
      error_re=(r'.*Deltatext block for revision 1.1 appeared twice'),
      )


def nasty_graphs():
  "process some nasty dependency graphs"

  # It's not how well the bear can dance, but that the bear can dance
  # at all:
  conv = ensure_conversion('nasty-graphs')


def tagging_after_delete():
  "optimal tag after deleting files"

  conv = ensure_conversion('tagging-after-delete')

  # tag should be 'clean', no deletes
  log = conv.find_tag_log('tag1')
  expected = (
    ('/%(tags)s/tag1 (from /%(trunk)s:3)', 'A'),
    )
  log.check_changes(expected)


def crossed_branches():
  "branches created in inconsistent orders"

  conv = ensure_conversion('crossed-branches')


########################################################################
# Run the tests

# list all tests here, starting with None:
test_list = [
    None,
# 1:
    show_usage,
    attr_exec,
    space_fname,
    two_quick,
    PruneWithCare(),
    PruneWithCare(variant=1, trunk='a', branches='b', tags='c'),
    PruneWithCare(variant=2, trunk='a/1', branches='b/1', tags='c/1'),
    PruneWithCare(variant=3, trunk='a/1', branches='a/2', tags='a/3'),
    interleaved_commits,
# 10:
    simple_commits,
    SimpleTags(),
    SimpleTags(variant=1, trunk='a', branches='b', tags='c'),
    SimpleTags(variant=2, trunk='a/1', branches='b/1', tags='c/1'),
    SimpleTags(variant=3, trunk='a/1', branches='a/2', tags='a/3'),
    simple_branch_commits,
    mixed_time_tag,
    mixed_time_branch_with_added_file,
    mixed_commit,
    split_time_branch,
# 20:
    bogus_tag,
    overlapping_branch,
    PhoenixBranch(),
    PhoenixBranch(variant=1, trunk='a/1', branches='b/1', tags='c/1'),
    ctrl_char_in_log,
    overdead,
    NoTrunkPrune(),
    NoTrunkPrune(variant=1, trunk='a', branches='b', tags='c'),
    NoTrunkPrune(variant=2, trunk='a/1', branches='b/1', tags='c/1'),
    NoTrunkPrune(variant=3, trunk='a/1', branches='a/2', tags='a/3'),
# 30:
    double_delete,
    split_branch,
    resync_misgroups,
    TaggedBranchAndTrunk(),
    TaggedBranchAndTrunk(variant=1, trunk='a/1', branches='a/2', tags='a/3'),
    enroot_race,
    enroot_race_obo,
    BranchDeleteFirst(),
    BranchDeleteFirst(variant=1, trunk='a/1', branches='a/2', tags='a/3'),
    nonascii_filenames,
# 40:
    UnicodeLog(
        warning_re=r'WARNING\: problem encoding author or log message'),
    UnicodeLog(
        variant='encoding', args=['--encoding=utf_8']),
    UnicodeLog(
        variant='fallback-encoding', args=['--fallback-encoding=utf_8']),
    vendor_branch_sameness,
    default_branches,
    compose_tag_three_sources,
    pass5_when_to_fill,
    PeerPathPruning(),
    PeerPathPruning(variant=1, trunk='a/1', branches='a/2', tags='a/3'),
    EmptyTrunk(),
# 50:
    EmptyTrunk(variant=1, trunk='a', branches='b', tags='c'),
    EmptyTrunk(variant=2, trunk='a/1', branches='a/2', tags='a/3'),
    XFail(no_spurious_svn_commits),
    invalid_closings_on_trunk,
    individual_passes,
    resync_bug,
    XFail(branch_from_default_branch),
    file_in_attic_too,
    retain_file_in_attic_too,
    symbolic_name_filling_guide,
# 60:
    eol_mime1,
    eol_mime2,
    eol_mime3,
    eol_mime4,
    cvs_revnums_off,
    cvs_revnums_on,
    keywords,
    ignore,
    requires_cvs,
    questionable_branch_names,
# 70:
    questionable_tag_names,
    revision_reorder_bug,
    exclude,
    vendor_branch_delete_add,
    resync_pass2_pull_forward,
    native_eol,
    double_fill,
    resync_pass2_push_backward,
    double_add,
    bogus_branch_copy,
# 80:
    nested_ttb_directories,
    auto_props_ignore_case,
    auto_props,
    ctrl_char_in_filename,
    commit_dependencies,
    show_help_passes,
    multiple_tags,
    double_branch_delete,
    symbol_mismatches,
    force_symbols,
# 90:
    commit_blocks_tags,
    blocked_excludes,
    unblock_blocked_excludes,
    regexp_force_symbols,
    heuristic_symbol_default,
    branch_symbol_default,
    tag_symbol_default,
    symbol_transform,
    issue_99,
    issue_100,
# 100:
    issue_106,
    options_option,
    tag_with_no_revision,
    XFail(delete_cvsignore),
    repeated_deltatext,
    nasty_graphs,
    XFail(tagging_after_delete),
    crossed_branches,
    ]

if __name__ == '__main__':

  # The Subversion test suite code assumes it's being invoked from
  # within a working copy of the Subversion sources, and tries to use
  # the binaries in that tree.  Since the cvs2svn tree never contains
  # a Subversion build, we just use the system's installed binaries.
  svntest.main.svn_binary         = 'svn'
  svntest.main.svnlook_binary     = 'svnlook'
  svntest.main.svnadmin_binary    = 'svnadmin'
  svntest.main.svnversion_binary  = 'svnversion'

  svntest.main.run_tests(test_list)
  # NOTREACHED


### End of file.
