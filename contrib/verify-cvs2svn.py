#!/usr/bin/env python
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
#
# The purpose of verify-cvs2svn is to verify the result of a cvs2svn
# repository conversion.  The following tests are performed:
#
# 1. Content checking of the HEAD revision of trunk, all tags and all
#    branches.  Only the tags and branches in the Subversion
#    repository are checked, i.e. there are no checks to verify that
#    all tags and branches in the CVS repository are present.
#
# This program only works if you converted a subdirectory of a CVS
# repository, and not the whole repository.  If you really did convert
# a whole repository and need to check it, you must create a CVSROOT
# directory above the current root using cvs init.
#
# ====================================================================

import os
import sys
import optparse
import subprocess
import shutil
import re
import tarfile


# CVS and Subversion command line client commands
CVS_CMD = 'cvs'
SVN_CMD = 'svn'
HG_CMD = 'hg'
GIT_CMD = 'git'


def pipe(cmd):
  """Run cmd as a pipe.  Return (output, status)."""
  child = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  output = child.stdout.read()
  status = child.wait()
  return (output, status)


def cmd_failed(cmd, output, status):
  print 'CMD FAILED:', ' '.join(cmd)
  print 'Output:'
  sys.stdout.write(output)
  raise RuntimeError('%s command failed!' % cmd[0])


def split_output(self, cmd):
  (output, status) = pipe(cmd)
  if status:
    cmd_failed(cmd, output, status)
  retval = output.split(os.linesep)[:-1]
  if retval and not retval[-1]:
    del retval[-1]
  return retval


class CvsRepos:
  def __init__(self, path):
    """Open the CVS repository at PATH."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
      raise RuntimeError('CVS path is not a directory')

    if os.path.exists(os.path.join(path, 'CVSROOT')):
      # The whole repository
      self.module = "."
      self.cvsroot = path
    else:
      self.cvsroot = os.path.dirname(path)
      self.module = os.path.basename(path)
      while not os.path.exists(os.path.join(self.cvsroot, 'CVSROOT')):
        parent = os.path.dirname(self.cvsroot)
        if parent == self.cvsroot:
          raise RuntimeError('Cannot find the CVSROOT')
        self.module = os.path.join(os.path.basename(self.cvsroot), self.module)
        self.cvsroot = parent

  def __str__(self):
    return os.path.basename(self.cvsroot)

  def export(self, dest_path, rev=None, keyword_opt=None):
    """Export revision REV to DEST_PATH where REV can be None to export
    the HEAD revision, or any valid CVS revision string to export that
    revision."""
    os.mkdir(dest_path)
    cmd = [CVS_CMD, '-Q', '-d', ':local:' + self.cvsroot, 'export']
    if rev:
      cmd.extend(['-r', rev])
    else:
      cmd.extend(['-D', 'now'])
    if keyword_opt:
      cmd.append(keyword_opt)
    cmd.extend(['-d', dest_path, self.module])
    (output, status) = pipe(cmd)
    if status or output:
      cmd_failed(cmd, output, status)


class SvnRepos:
  name = 'svn'

  def __init__(self, url):
    """Open the Subversion repository at URL."""
    # Check if the user supplied an URL or a path
    if url.find('://') == -1:
      abspath = os.path.abspath(url)
      url = 'file://' + (abspath[0] != '/' and '/' or '') + abspath
      if os.sep != '/':
        url = url.replace(os.sep, '/')

    self.url = url

    # Cache a list of all tags and branches
    list = self.list('')
    if 'tags' in list:
      self.tag_list = self.list('tags')
    else:
      self.tag_list = []
    if 'branches' in list:
      self.branch_list = self.list('branches')
    else:
      self.branch_list = []

  def __str__(self):
    return self.url.split('/')[-1]

  def export(self, path, dest_path):
    """Export PATH to DEST_PATH."""
    url = '/'.join([self.url, path])
    cmd = [SVN_CMD, 'export', '-q', url, dest_path]
    (output, status) = pipe(cmd)
    if status or output:
      cmd_failed(cmd, output, status)

  def export_trunk(self, dest_path):
    """Export trunk to DEST_PATH."""
    self.export('trunk', dest_path)

  def export_tag(self, dest_path, tag):
    """Export the tag TAG to DEST_PATH."""
    self.export('tags/' + tag, dest_path)

  def export_branch(self, dest_path, branch):
    """Export the branch BRANCH to DEST_PATH."""
    self.export('branches/' + branch, dest_path)

  def list(self, path):
    """Return a list of all files and directories in PATH."""
    cmd = [SVN_CMD, 'ls', self.url + '/' + path]
    entries = []
    for line in split_output(cmd):
      if line:
        entries.append(line.rstrip('/'))
    return entries

  def tags(self):
    """Return a list of all tags in the repository."""
    return self.tag_list

  def branches(self):
    """Return a list of all branches in the repository."""
    return self.branch_list


class HgRepos:
  name = 'hg'

  def __init__(self, path):
    self.path = path
    self.base_cmd = [HG_CMD, '-R', self.path]

    self._branches = None               # cache result of branches()
    self._have_default = None           # so export_trunk() doesn't blow up

  def __str__(self):
    return os.path.basename(self.path)

  def _export(self, dest_path, rev):
    cmd = self.base_cmd + ['archive',
                           '--type', 'files',
                           '--rev', rev,
                           '--exclude', 're:^\.hg',
                           dest_path]
    (output, status) = pipe(cmd)
    if status or output:
      cmd_failed(cmd, output, status)

    # If Mercurial has nothing to export, then it doesn't create
    # dest_path.  This breaks tree_compare(), so just check that the
    # manifest for the chosen revision really is empty, and if so create
    # the empty dir.
    if not os.path.exists(dest_path):
      cmd = self.base_cmd + ['manifest', '--rev', rev]

      manifest = [fn for fn in split_output(cmd)
                  if not fn.startswith('.hg')]
      if not manifest:
        os.mkdir(dest_path)

  def export_trunk(self, dest_path):
    self.branches()                     # ensure _have_default is set
    if self._have_default:
      self._export(dest_path, 'default')
    else:
      # same as CVS does when exporting empty trunk
      os.mkdir(dest_path)

  def export_tag(self, dest_path, tag):
    self._export(dest_path, tag)

  def export_branch(self, dest_path, branch):
    self._export(dest_path, branch)

  def tags(self):
    cmd = self.base_cmd + ['tags', '-q']
    tags = split_output(cmd)
    tags.remove('tip')
    return tags

  def branches(self):
    if self._branches is None:
      cmd = self.base_cmd + ['branches', '-q']
      self._branches = branches = split_output(cmd)
      try:
        branches.remove('default')
        self._have_default = True
      except ValueError:
        self._have_default = False

    return self._branches


class GitRepos:
  name = 'git'

  def __init__(self, path):
    self.path = path
    self.repo_cmd = [
        GIT_CMD,
        '--git-dir=' + os.path.join(self.path, '.git'),
        '--work-tree=' + self.path,
        ]

    self._branches = None               # cache result of branches()
    self._have_master = None           # so export_trunk() doesn't blow up

  def __str__(self):
    return os.path.basename(self.path)

  def _export(self, dest_path, rev):
    # clone the repository
    cmd = [GIT_CMD, 'archive', '--remote=' + self.path, '--format=tar', rev]
    git_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    if False:
      # Unfortunately for some git tags the below causes
      # git_proc.wait() to hang.  The git archive process is in a
      # <defunct> state and the verify-cvs2svn hangs for good.
      tar = tarfile.open(mode="r|", fileobj=git_proc.stdout)
      for tarinfo in tar:
        tar.extract(tarinfo, dest_path)
      tar.close()
    else:
      os.mkdir(dest_path)
      tar_proc = subprocess.Popen(
          ['tar', '-C', dest_path, '-x'],
          stdin=git_proc.stdout, stdout=subprocess.PIPE,
          )
      output = tar_proc.stdout.read()
      status = tar_proc.wait()
      if output or status:
        raise RuntimeError(
            'Git tar extraction of rev %s from repo %s to %s failed (%s)!'
            % (rev, self.path, dest_path, output)
            )

    status = git_proc.wait()
    if status:
      raise RuntimeError(
          'Git extract of rev %s from repo %s to %s failed!'
          % (rev, self.path, dest_path)
          )

    if not os.path.exists(dest_path):
      raise RuntimeError(
          'Git clone of %s to %s failed!' % (self.path, dest_path)
          )

  def export_trunk(self, dest_path):
    self.branches()                     # ensure _have_default is set
    if self._have_master:
      self._export(dest_path, 'master')
    else:
      # same as CVS does when exporting empty trunk
      os.mkdir(dest_path)

  def export_tag(self, dest_path, tag):
    self._export(dest_path, tag)

  def export_branch(self, dest_path, branch):
    self._export(dest_path, branch)

  def tags(self):
    cmd = self.repo_cmd + ['tag']
    tags = split_output(cmd)
    return tags

  def branches(self):
    if self._branches is None:
      cmd = self.repo_cmd + ['branch']
      branches = split_output(cmd)
      # Remove the two chracters at the start of the branch name
      for i in range(len(branches)):
        branches[i] = branches[i][2:]
      self._branches = branches
      try:
        branches.remove('master')
        self._have_master = True
      except ValueError:
        self._have_master = False

    return self._branches


def transform_symbol(ctx, name):
  """Transform the symbol NAME using the renaming rules specified
  with --symbol-transform.  Return the transformed symbol name."""

  for (pattern, replacement) in ctx.symbol_transforms:
    newname = pattern.sub(replacement, name)
    if newname != name:
      print "   symbol '%s' transformed to '%s'" % (name, newname)
      name = newname

  return name


class Failures(object):
  def __init__(self):
    self.count = 0                      # number of failures seen

  def __str__(self):
    return str(self.count)

  def __repr__(self):
    return "<%s at 0x%x: %s>" % (self.__class__.__name__, id(self), self.count)

  def report(self, summary, details=None):
    self.count += 1
    sys.stdout.write(' FAIL: %s\n' % summary)
    if details:
      for line in details:
        sys.stdout.write('  %s\n' % line)

  def __nonzero__(self):
    return self.count > 0


def file_compare(failures, base1, base2, run_diff, rel_path):
  """Compare the mode and contents of two files.

  The paths are specified as two base paths BASE1 and BASE2, and a
  path REL_PATH that is relative to the two base paths.  Return True
  iff the file mode and contents are identical."""

  ok = True
  path1 = os.path.join(base1, rel_path)
  path2 = os.path.join(base2, rel_path)
  mode1 = os.stat(path1).st_mode & 0700   # only look at owner bits
  mode2 = os.stat(path2).st_mode & 0700
  if mode1 != mode2:
    failures.report('File modes differ for %s' % rel_path,
                    details=['%s: %o' % (path1, mode1),
                             '%s: %o' % (path2, mode2)])
    ok = False

  file1 = open(path1, 'rb')
  file2 = open(path2, 'rb')
  while True:
    data1 = file1.read(8192)
    data2 = file2.read(8192)
    if data1 != data2:
      if run_diff:
        cmd = ['diff', '-u', path1, path2]
        (output, status) = pipe(cmd)
        diff = output.split(os.linesep)
      else:
        diff = None
      failures.report('File contents differ for %s' % rel_path,
                      details=diff)
      ok = False
      break
    if len(data1) == 0:
      # eof
      break

  return ok


def tree_compare(failures, base1, base2, run_diff, rel_path=''):
  """Compare the contents of two directory trees, including file contents.

  The paths are specified as two base paths BASE1 and BASE2, and a
  path REL_PATH that is relative to the two base paths.  Return True
  iff the trees are identical."""

  if not rel_path:
    path1 = base1
    path2 = base2
  else:
    path1 = os.path.join(base1, rel_path)
    path2 = os.path.join(base2, rel_path)
  if not os.path.exists(path1):
    failures.report('%s does not exist' % path1)
    return False
  if not os.path.exists(path2):
    failures.report('%s does not exist' % path2)
    return False
  if os.path.isfile(path1) and os.path.isfile(path2):
    return file_compare(failures, base1, base2, run_diff, rel_path)
  if not (os.path.isdir(path1) and os.path.isdir(path2)):
    failures.report('Path types differ for %r' % rel_path)
    return False
  entries1 = os.listdir(path1)
  entries1.sort()
  entries2 = os.listdir(path2)
  entries2.sort()

  ok = True

  missing = filter(lambda x: x not in entries2, entries1)
  extra = filter(lambda x: x not in entries1, entries2)
  if missing:
    failures.report('Directory /%s is missing entries: %s' %
                    (rel_path, ', '.join(missing)))
    ok = False
  if extra:
    failures.report('Directory /%s has extra entries: %s' %
                    (rel_path, ', '.join(extra)))
    ok = False

  for entry in entries1:
    new_rel_path = os.path.join(rel_path, entry)
    if not tree_compare(failures, base1, base2, run_diff, new_rel_path):
      ok = False
  return ok


def verify_contents_single(failures, cvsrepos, verifyrepos, kind, label, ctx):
  """Verify the HEAD revision of a trunk, tag, or branch.

  Verify that the contents of the HEAD revision of all directories and
  files in the conversion repository VERIFYREPOS match the ones in the
  CVS repository CVSREPOS.  KIND can be either 'trunk', 'tag' or
  'branch'.  If KIND is either 'tag' or 'branch', LABEL is used to
  specify the name of the tag or branch.  CTX has the attributes:
  CTX.tmpdir: specifying the directory for all temporary files.
  CTX.skip_cleanup: if true, the temporary files are not deleted.
  CTX.run_diff: if true, run diff on differing files."""

  itemname = kind + (kind != 'trunk' and '-' + label or '')
  cvs_export_dir = os.path.join(
    ctx.tmpdir, 'cvs-export-%s' % itemname)
  vrf_export_dir = os.path.join(
    ctx.tmpdir, '%s-export-%s' % (verifyrepos.name, itemname))

  if label:
    cvslabel = transform_symbol(ctx, label)
  else:
    cvslabel = None

  try:
    cvsrepos.export(cvs_export_dir, cvslabel, ctx.keyword_opt)
    if kind == 'trunk':
      verifyrepos.export_trunk(vrf_export_dir)
    elif kind == 'tag':
      verifyrepos.export_tag(vrf_export_dir, label)
    else:
      verifyrepos.export_branch(vrf_export_dir, label)

    if not tree_compare(
          failures, cvs_export_dir, vrf_export_dir, ctx.run_diff
          ):
      return False
  finally:
    if not ctx.skip_cleanup:
      if os.path.exists(cvs_export_dir):
        shutil.rmtree(cvs_export_dir)
      if os.path.exists(vrf_export_dir):
        shutil.rmtree(vrf_export_dir)
  return True


def verify_contents(failures, cvsrepos, verifyrepos, ctx):
  """Verify that the contents of the HEAD revision of all directories
  and files in the trunk, all tags and all branches in the conversion
  repository VERIFYREPOS matches the ones in the CVS repository CVSREPOS.
  CTX is passed through to verify_contents_single()."""

  # branches/tags that failed:
  locations = []

  # Verify contents of trunk
  print 'Verifying trunk'
  sys.stdout.flush()
  if not verify_contents_single(
        failures, cvsrepos, verifyrepos, 'trunk', None, ctx
        ):
    locations.append('trunk')

  # Verify contents of all tags
  for tag in verifyrepos.tags():
    print 'Verifying tag', tag
    sys.stdout.flush()
    if not verify_contents_single(
          failures, cvsrepos, verifyrepos, 'tag', tag, ctx
          ):
      locations.append('tag:' + tag)

  # Verify contents of all branches
  for branch in verifyrepos.branches():
    if branch[:10] == 'unlabeled-':
      print 'Skipped branch', branch
    else:
      print 'Verifying branch', branch
      if not verify_contents_single(
            failures, cvsrepos, verifyrepos, 'branch', branch, ctx
            ):
        locations.append('branch:' + branch)
    sys.stdout.flush()

  assert bool(failures) == bool(locations), \
         "failures = %r\nlocations = %r" % (failures, locations)

  # Show the results
  if failures:
    sys.stdout.write('FAIL: %s != %s: %d failure(s) in:\n'
                     % (cvsrepos, verifyrepos, failures.count))
    for location in locations:
      sys.stdout.write('  %s\n' % location)
  else:
    sys.stdout.write('PASS: %s == %s\n' % (cvsrepos, verifyrepos))
  sys.stdout.flush()


class OptionContext:
  pass


def main(argv):
  parser = optparse.OptionParser(
    usage='%prog [options] cvs-repos verify-repos')
  parser.add_option('--branch',
                    help='verify contents of the branch BRANCH only')
  parser.add_option('--diff', action='store_true', dest='run_diff',
                    help='run diff on differing files')
  parser.add_option('--tag',
                    help='verify contents of the tag TAG only')
  parser.add_option('--tmpdir',
                    metavar='PATH',
                    help='path to store temporary files')
  parser.add_option('--trunk', action='store_true',
                    help='verify contents of trunk only')
  parser.add_option('--symbol-transform', action='append',
                    metavar='P:S',
                    help='transform symbol names from P to S like cvs2svn, '
                         'except transforms SVN symbol to CVS symbol')
  parser.add_option('--svn',
                    action='store_const', dest='repos_type', const='svn',
                    help='assume verify-repos is svn [default]')
  parser.add_option('--hg',
                    action='store_const', dest='repos_type', const='hg',
                    help='assume verify-repos is hg')
  parser.add_option('--git',
                    action='store_const', dest='repos_type', const='git',
                    help='assume verify-repos is git')
  parser.add_option('--suppress-keywords',
                    action='store_const', dest='keyword_opt', const='-kk',
                    help='suppress CVS keyword expansion '
                         '(equivalent to --keyword-opt=-kk)')
  parser.add_option('--keyword-opt',
                    metavar='OPT',
                    help='control CVS keyword expansion by adding OPT to '
                         'cvs export command line')

  parser.set_defaults(run_diff=False,
                      tmpdir='',
                      skip_cleanup=False,
                      symbol_transforms=[],
                      repos_type='svn')
  (options, args) = parser.parse_args()

  symbol_transforms = []
  for value in options.symbol_transforms:
    # This is broken!
    [pattern, replacement] = value.split(":")
    try:
      symbol_transforms.append(
          RegexpSymbolTransform(pattern, replacement))
    except re.error:
      parser.error("'%s' is not a valid regexp." % (pattern,))

  def error(msg):
    """Print an error to sys.stderr."""
    sys.stderr.write('Error: ' + str(msg) + '\n')

  verify_branch = options.branch
  verify_tag = options.tag
  verify_trunk = options.trunk

  # Consistency check for options and arguments.
  if len(args) != 2:
    parser.error("wrong number of arguments")

  cvs_path = args[0]
  verify_path = args[1]
  verify_klass = {'svn': SvnRepos,
                  'hg':  HgRepos,
                  'git': GitRepos}[options.repos_type]

  failures = Failures()
  try:
    # Open the repositories
    cvsrepos = CvsRepos(cvs_path)
    verifyrepos = verify_klass(verify_path)

    # Do our thing...
    if verify_branch:
      print 'Verifying branch', verify_branch
      verify_contents_single(
          failures, cvsrepos, verifyrepos, 'branch', verify_branch, options
          )
    elif verify_tag:
      print 'Verifying tag', verify_tag
      verify_contents_single(
          failures, cvsrepos, verifyrepos, 'tag', verify_tag, options
          )
    elif verify_trunk:
      print 'Verifying trunk'
      verify_contents_single(
          failures, cvsrepos, verifyrepos, 'trunk', None, options
          )
    else:
      # Verify trunk, tags and branches
      verify_contents(failures, cvsrepos, verifyrepos, options)
  except RuntimeError, e:
    error(str(e))
  except KeyboardInterrupt:
    pass

  sys.exit(failures and 1 or 0)


if __name__ == '__main__':
  main(sys.argv)

