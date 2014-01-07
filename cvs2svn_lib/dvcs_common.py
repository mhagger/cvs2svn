# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007-2009 CollabNet.  All rights reserved.
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

"""Miscellaneous utility code common to DVCS backends (like
Git, Mercurial, or Bazaar).
"""

import os, sys

from cvs2svn_lib import config
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.run_options import RunOptions
from cvs2svn_lib.log import logger
from cvs2svn_lib.common import error_prefix
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.project import Project
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.svn_revision_range import RevisionScores
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.repository_mirror import RepositoryMirror
from cvs2svn_lib.output_option import OutputOption
from cvs2svn_lib.property_setters import FilePropertySetter


class KeywordHandlingPropertySetter(FilePropertySetter):
  """Set property _keyword_handling to a specified value.

  This keyword is used to tell the RevisionReader whether it has to
  collapse/expand RCS keywords when generating the fulltext or leave
  them alone."""

  propname = '_keyword_handling'

  def __init__(self, value):
    if value not in ['collapsed', 'expanded', 'untouched', None]:
      raise FatalError(
          'Value for %s must be "collapsed", "expanded", or "untouched"'
          % (self.propname,)
          )
    self.value = value

  def set_properties(self, cvs_file):
    self.maybe_set_property(cvs_file, self.propname, self.value)


class DVCSRunOptions(RunOptions):
  """Dumping ground for whatever is common to GitRunOptions,
  HgRunOptions, and BzrRunOptions."""

  def __init__(self, progname, cmd_args, pass_manager):
    Ctx().cross_project_commits = False
    Ctx().cross_branch_commits = False
    if Ctx().username is None:
      Ctx().username = self.DEFAULT_USERNAME
    RunOptions.__init__(self, progname, cmd_args, pass_manager)

  def set_project(
        self,
        project_cvs_repos_path,
        symbol_transforms=None,
        symbol_strategy_rules=[],
        exclude_paths=[],
        ):
    """Set the project to be converted.

    If a project had already been set, overwrite it.

    Most arguments are passed straight through to the Project
    constructor.  SYMBOL_STRATEGY_RULES is an iterable of
    SymbolStrategyRules that will be applied to symbols in this
    project."""

    symbol_strategy_rules = list(symbol_strategy_rules)

    project = Project(
        0,
        project_cvs_repos_path,
        symbol_transforms=symbol_transforms,
        exclude_paths=exclude_paths,
        )

    self.projects = [project]
    self.project_symbol_strategy_rules = [symbol_strategy_rules]

  def process_property_setter_options(self):
    RunOptions.process_property_setter_options(self)

    # Property setters for internal use:
    Ctx().file_property_setters.append(
        KeywordHandlingPropertySetter('collapsed')
        )

  def process_options(self):
    # Consistency check for options and arguments.
    if len(self.args) == 0:
      # Default to using '.' as the source repository path
      self.args.append(os.getcwd())

    if len(self.args) > 1:
      logger.error(error_prefix + ": must pass only one CVS repository.\n")
      self.usage()
      sys.exit(1)

    cvsroot = self.args[0]

    self.process_extraction_options()
    self.process_output_options()
    self.process_symbol_strategy_options()
    self.process_property_setter_options()

    # Create the project:
    self.set_project(
        cvsroot,
        symbol_transforms=self.options.symbol_transforms,
        symbol_strategy_rules=self.options.symbol_strategy_rules,
        )


class DVCSOutputOption(OutputOption):
  def __init__(self):
    self._mirror = RepositoryMirror()
    self._symbolings_reader = None

  def normalize_author_transforms(self, author_transforms):
    """Convert AUTHOR_TRANSFORMS into author strings.

    AUTHOR_TRANSFORMS is a dict { CVSAUTHOR : DVCSAUTHOR } where
    CVSAUTHOR is the CVS author and DVCSAUTHOR is either:

    * a tuple (NAME, EMAIL) where NAME and EMAIL are strings.  Such
      entries are converted into a UTF-8 string of the form 'name
      <email>'.

    * a string already in the form 'name <email>'.

    Return a similar dict { CVSAUTHOR : DVCSAUTHOR } where all keys
    and values are UTF-8-encoded strings.

    Any of the input strings may be Unicode strings (in which case
    they are encoded to UTF-8) or 8-bit strings (in which case they
    are used as-is).  Also turns None into the empty dict."""

    result = {}
    if author_transforms is not None:
      for (cvsauthor, dvcsauthor) in author_transforms.iteritems():
        cvsauthor = to_utf8(cvsauthor)
        if isinstance(dvcsauthor, basestring):
          dvcsauthor = to_utf8(dvcsauthor)
        else:
          (name, email,) = dvcsauthor
          name = to_utf8(name)
          email = to_utf8(email)
          dvcsauthor = "%s <%s>" % (name, email,)
        result[cvsauthor] = dvcsauthor
    return result

  def register_artifacts(self, which_pass):
    # These artifacts are needed for SymbolingsReader:
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OPENINGS_CLOSINGS_SORTED, which_pass
        )
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OFFSETS_DB, which_pass
        )
    self._mirror.register_artifacts(which_pass)

  def check(self):
    if Ctx().cross_project_commits:
      raise FatalError(
          '%s output is not supported with cross-project commits' % self.name
          )
    if Ctx().cross_branch_commits:
      raise FatalError(
          '%s output is not supported with cross-branch commits' % self.name
          )
    if Ctx().username is None:
      raise FatalError(
          '%s output requires a default commit username' % self.name
          )

  def setup(self, svn_rev_count):
    self._symbolings_reader = SymbolingsReader()
    self._mirror.open()

  def cleanup(self):
    self._mirror.close()
    self._symbolings_reader.close()
    del self._symbolings_reader

  def _get_source_groups(self, svn_commit):
    """Return groups of sources for SVN_COMMIT.

    SVN_COMMIT is an instance of SVNSymbolCommit.  Return a list of tuples
    (svn_revnum, source_lod, cvs_symbols) where svn_revnum is the revision
    that should serve as a source, source_lod is the CVS line of
    development, and cvs_symbols is a list of CVSSymbolItems that can be
    copied from that source.  The list is in arbitrary order."""

    # Get a map {CVSSymbol : SVNRevisionRange}:
    range_map = self._symbolings_reader.get_range_map(svn_commit)

    # range_map, split up into one map per LOD; i.e., {LOD :
    # {CVSSymbol : SVNRevisionRange}}:
    lod_range_maps = {}

    for (cvs_symbol, range) in range_map.iteritems():
      lod_range_map = lod_range_maps.get(range.source_lod)
      if lod_range_map is None:
        lod_range_map = {}
        lod_range_maps[range.source_lod] = lod_range_map
      lod_range_map[cvs_symbol] = range

    # Sort the sources so that the branch that serves most often as
    # parent is processed first:
    lod_ranges = lod_range_maps.items()
    lod_ranges.sort(
        lambda (lod1,lod_range_map1),(lod2,lod_range_map2):
        -cmp(len(lod_range_map1), len(lod_range_map2)) or cmp(lod1, lod2)
        )

    source_groups = []
    for (lod, lod_range_map) in lod_ranges:
      while lod_range_map:
        revision_scores = RevisionScores(lod_range_map.values())
        (source_lod, revnum, score) = revision_scores.get_best_revnum()
        assert source_lod == lod
        cvs_symbols = []
        for (cvs_symbol, range) in lod_range_map.items():
          if revnum in range:
            cvs_symbols.append(cvs_symbol)
            del lod_range_map[cvs_symbol]
        source_groups.append((revnum, lod, cvs_symbols))

    return source_groups

  def _is_simple_copy(self, svn_commit, source_groups):
    """Return True iff SVN_COMMIT can be created as a simple copy.

    SVN_COMMIT is an SVNTagCommit.  Return True iff it can be created
    as a simple copy from an existing revision (i.e., if the fixup
    branch can be avoided for this tag creation)."""

    # The first requirement is that there be exactly one source:
    if len(source_groups) != 1:
      return False

    (svn_revnum, source_lod, cvs_symbols) = source_groups[0]

    # The second requirement is that the destination LOD not already
    # exist:
    try:
      self._mirror.get_current_lod_directory(svn_commit.symbol)
    except KeyError:
      # The LOD doesn't already exist.  This is good.
      pass
    else:
      # The LOD already exists.  It cannot be created by a copy.
      return False

    # The third requirement is that the source LOD contains exactly
    # the same files as we need to add to the symbol:
    try:
      source_node = self._mirror.get_old_lod_directory(source_lod, svn_revnum)
    except KeyError:
      raise InternalError('Source %r does not exist' % (source_lod,))
    return (
        set([cvs_symbol.cvs_file for cvs_symbol in cvs_symbols])
        == set(self._get_all_files(source_node))
        )

  def _get_all_files(self, node):
    """Generate all of the CVSFiles under NODE."""

    for cvs_path in node:
      subnode = node[cvs_path]
      if subnode is None:
        yield cvs_path
      else:
        for sub_cvs_path in self._get_all_files(subnode):
          yield sub_cvs_path


class ExpectedDirectoryError(Exception):
  """A file was found where a directory was expected."""

  pass


class ExpectedFileError(Exception):
  """A directory was found where a file was expected."""

  pass


class MirrorUpdater(object):
  def register_artifacts(self, which_pass):
    pass

  def start(self, mirror):
    self._mirror = mirror

  def _mkdir_p(self, cvs_directory, lod):
    """Make sure that CVS_DIRECTORY exists in LOD.

    If not, create it.  Return the node for CVS_DIRECTORY."""

    try:
      node = self._mirror.get_current_lod_directory(lod)
    except KeyError:
      node = self._mirror.add_lod(lod)

    for sub_path in cvs_directory.get_ancestry()[1:]:
      try:
        node = node[sub_path]
      except KeyError:
        node = node.mkdir(sub_path)
      if node is None:
        raise ExpectedDirectoryError(
            'File found at \'%s\' where directory was expected.' % (sub_path,)
            )

    return node

  def add_file(self, cvs_rev, post_commit):
    cvs_file = cvs_rev.cvs_file
    if post_commit:
      lod = cvs_file.project.get_trunk()
    else:
      lod = cvs_rev.lod
    parent_node = self._mkdir_p(cvs_file.parent_directory, lod)
    parent_node.add_file(cvs_file)

  def modify_file(self, cvs_rev, post_commit):
    cvs_file = cvs_rev.cvs_file
    if post_commit:
      lod = cvs_file.project.get_trunk()
    else:
      lod = cvs_rev.lod
    if self._mirror.get_current_path(cvs_file, lod) is not None:
      raise ExpectedFileError(
          'Directory found at \'%s\' where file was expected.' % (cvs_file,)
          )

  def delete_file(self, cvs_rev, post_commit):
    cvs_file = cvs_rev.cvs_file
    if post_commit:
      lod = cvs_file.project.get_trunk()
    else:
      lod = cvs_rev.lod
    parent_node = self._mirror.get_current_path(
        cvs_file.parent_directory, lod
        )
    if parent_node[cvs_file] is not None:
      raise ExpectedFileError(
          'Directory found at \'%s\' where file was expected.' % (cvs_file,)
          )
    del parent_node[cvs_file]

  def process_revision(self, cvs_rev, post_commit):
    if isinstance(cvs_rev, CVSRevisionAdd):
      self.add_file(cvs_rev, post_commit)
    elif isinstance(cvs_rev, CVSRevisionChange):
      self.modify_file(cvs_rev, post_commit)
    elif isinstance(cvs_rev, CVSRevisionDelete):
      self.delete_file(cvs_rev, post_commit)
    elif isinstance(cvs_rev, CVSRevisionNoop):
      pass
    else:
      raise InternalError('Unexpected CVSRevision type: %s' % (cvs_rev,))

  def branch_file(self, cvs_symbol):
    cvs_file = cvs_symbol.cvs_file
    parent_node = self._mkdir_p(cvs_file.parent_directory, cvs_symbol.symbol)
    parent_node.add_file(cvs_file)

  def finish(self):
    del self._mirror


def to_utf8(s):
  if isinstance(s, unicode):
    return s.encode('utf8')
  else:
    return s


