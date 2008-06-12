# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007 CollabNet.  All rights reserved.
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

"""Classes for outputting the converted repository to git.

For information about the format allowed by git-fast-import, see:

    http://www.kernel.org/pub/software/scm/git/docs/git-fast-import.html

"""

from __future__ import generators

import bisect

from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.cvs_item import CVSRevisionAdd
from cvs2svn_lib.cvs_item import CVSRevisionChange
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.output_option import OutputOption
from cvs2svn_lib.svn_revision_range import RevisionScores
from cvs2svn_lib.repository_mirror import RepositoryMirror
from cvs2svn_lib.repository_mirror import PathExistsError


# The branch name to use for the "tag fixup branches".  The
# git-fast-import documentation suggests using 'TAG_FIXUP' (outside of
# the refs/heads namespace), but this is currently broken.  Use a name
# containing '.', which is not allowed in CVS symbols, to avoid
# conflicts (though of course a conflict could still result if the
# user requests symbol transformations).
FIXUP_BRANCH_NAME = 'refs/heads/TAG.FIXUP'


class ExpectedDirectoryError(Exception):
  """A file was found where a directory was expected."""

  pass


class ExpectedFileError(Exception):
  """A directory was found where a file was expected."""

  pass


class GitRevisionWriter(object):
  def register_artifacts(self, which_pass):
    pass

  def start(self, f, mirror):
    self.f = f
    self._mirror = mirror

  def _modify_file(self, cvs_item, post_commit):
    raise NotImplementedError()

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
    self._modify_file(cvs_rev, post_commit)

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
    self._modify_file(cvs_rev, post_commit)

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
    self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

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
    self._modify_file(cvs_symbol, post_commit=False)

  def finish(self):
    del self._mirror
    del self.f


class GitRevisionMarkWriter(GitRevisionWriter):
  def _modify_file(self, cvs_item, post_commit):
    if cvs_item.cvs_file.executable:
      mode = '100755'
    else:
      mode = '100644'

    self.f.write(
        'M %s :%d %s\n'
        % (mode, cvs_item.revision_recorder_token,
           cvs_item.cvs_file.cvs_path,)
        )


class GitRevisionInlineWriter(GitRevisionWriter):
  def __init__(self, revision_reader):
    self.revision_reader = revision_reader

  def register_artifacts(self, which_pass):
    GitRevisionWriter.register_artifacts(self, which_pass)
    self.revision_reader.register_artifacts(which_pass)

  def start(self, f, mirror):
    GitRevisionWriter.start(self, f, mirror)
    self.revision_reader.start()

  def _modify_file(self, cvs_item, post_commit):
    if cvs_item.cvs_file.executable:
      mode = '100755'
    else:
      mode = '100644'

    self.f.write(
        'M %s inline %s\n'
        % (mode, cvs_item.cvs_file.cvs_path,)
        )

    if isinstance(cvs_item, CVSSymbol):
      cvs_rev = cvs_item.get_cvs_revision_source(Ctx()._cvs_items_db)
    else:
      cvs_rev = cvs_item

    # FIXME: We have to decide what to do about keyword substitution
    # and eol_style here:
    fulltext = self.revision_reader.get_content_stream(
        cvs_rev, suppress_keyword_substitution=False
        ).read()

    self.f.write('data %d\n' % (len(fulltext),))
    self.f.write(fulltext)
    self.f.write('\n')

  def finish(self):
    GitRevisionWriter.finish(self)
    self.revision_reader.finish()


class GitOutputOption(OutputOption):
  """An OutputOption that outputs to a git-fast-import formatted file.

  Members:

    dump_filename -- (string) the name of the file to which the
        git-fast-import commands for defining revisions will be
        written.

    author_transforms -- a map {cvsauthor : (fullname, email)} from
        CVS author names to git full name and email address.  All of
        the contents are 8-bit strings encoded as UTF-8.

  """

  # The offset added to svn revision numbers to create a number to use
  # as a git-fast-import commit mark.  This value needs to be large to
  # avoid conflicts with blob marks.
  _mark_offset = 1000000000

  def __init__(self, dump_filename, revision_writer, author_transforms=None):
    """Constructor.

    DUMP_FILENAME is the name of the file to which the git-fast-import
    commands for defining revisions should be written.  (Please note
    that the actual file contents are not written to this file.)

    REVISION_WRITER is a GitRevisionWriter that is used to output
    either the content of revisions or a mark that was previously used
    to label a blob.

    AUTHOR_TRANSFORMS is a map {cvsauthor : (fullname, email)} from
    CVS author names to git full name and email address.  All of the
    contents should either be unicode strings or 8-bit strings encoded
    as UTF-8.

    """

    # The file to which to write the git-fast-import commands:
    self.dump_filename = dump_filename

    def to_utf8(s):
      if isinstance(s, unicode):
        return s.encode('utf8')
      else:
        return s

    self.author_transforms = {}
    if author_transforms is not None:
      for (cvsauthor, (name, email,)) in author_transforms.iteritems():
        cvsauthor = to_utf8(cvsauthor)
        name = to_utf8(name)
        email = to_utf8(email)
        self.author_transforms[cvsauthor] = (name, email,)

    self.revision_writer = revision_writer

    self._mirror = RepositoryMirror()

  def register_artifacts(self, which_pass):
    # These artifacts are needed for SymbolingsReader:
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OPENINGS_CLOSINGS_SORTED, which_pass
        )
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OFFSETS_DB, which_pass
        )
    self.revision_writer.register_artifacts(which_pass)
    self._mirror.register_artifacts(which_pass)

  def check(self):
    if Ctx().cross_project_commits:
      raise FatalError(
          'Git output is not supported with cross-project commits'
          )
    if Ctx().cross_branch_commits:
      raise FatalError(
          'Git output is not supported with cross-branch commits'
          )
    if Ctx().username is None:
      raise FatalError(
          'Git output requires a default commit username'
          )

  def check_symbols(self, symbol_map):
    # FIXME: What constraints does git impose on symbols?
    pass

  def setup(self, svn_rev_count):
    self._symbolings_reader = SymbolingsReader()
    self.f = open(self.dump_filename, 'wb')

    # The youngest revnum that has been committed so far:
    self._youngest = 0

    # A map {lod : [(revnum, mark)]} giving each of the revision
    # numbers in which there was a commit to lod, and the
    # corresponding mark.
    self._marks = {}

    self._mirror.open()
    self.revision_writer.start(self.f, self._mirror)

  def _create_commit_mark(self, lod, revnum):
    assert revnum >= self._youngest
    mark = GitOutputOption._mark_offset + revnum
    self._marks.setdefault(lod, []).append((revnum, mark))
    self._youngest = revnum
    return mark

  def _get_author(self, svn_commit):
    """Return the author to be used for SVN_COMMIT.

    Return the author in the form needed by git; that is, 'foo <bar>'."""

    author = svn_commit.get_author()
    (name, email,) = self.author_transforms.get(author, (author, author,))
    return '%s <%s>' % (name, email,)

  def _get_log_msg(svn_commit):
    return svn_commit.get_log_msg()

  _get_log_msg = staticmethod(_get_log_msg)

  def process_initial_project_commit(self, svn_commit):
    self._mirror.start_commit(svn_commit.revnum)
    self._mirror.end_commit()

  def process_primary_commit(self, svn_commit):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    lods = set()
    for cvs_rev in svn_commit.get_cvs_items():
      lods.add(cvs_rev.lod)
    if len(lods) != 1:
      raise InternalError('Commit affects %d LODs' % (len(lods),))
    lod = lods.pop()

    self._mirror.start_commit(svn_commit.revnum)
    if isinstance(lod, Trunk):
      # FIXME: is this correct?:
      self.f.write('commit refs/heads/master\n')
    else:
      self.f.write('commit refs/heads/%s\n' % (lod.name,))
    self.f.write(
        'mark :%d\n'
        % (self._create_commit_mark(lod, svn_commit.revnum),)
        )
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))
    for cvs_rev in svn_commit.get_cvs_items():
      self.revision_writer.process_revision(cvs_rev, post_commit=False)

    self.f.write('\n')
    self._mirror.end_commit()

  def process_post_commit(self, svn_commit):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    source_lods = set()
    for cvs_rev in svn_commit.cvs_revs:
      source_lods.add(cvs_rev.lod)
    if len(source_lods) != 1:
      raise InternalError('Commit is from %d LODs' % (len(source_lods),))
    source_lod = source_lods.pop()

    self._mirror.start_commit(svn_commit.revnum)
    # FIXME: is this correct?:
    self.f.write('commit refs/heads/master\n')
    self.f.write(
        'mark :%d\n'
        % (self._create_commit_mark(None, svn_commit.revnum),)
        )
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))
    self.f.write(
        'merge :%d\n'
        % (self._get_source_mark(source_lod, svn_commit.revnum),)
        )
    for cvs_rev in svn_commit.cvs_revs:
      self.revision_writer.process_revision(cvs_rev, post_commit=True)

    self.f.write('\n')
    self._mirror.end_commit()

  def _get_source_groups(self, svn_commit):
    """Return groups of sources for SVN_COMMIT.

    SVN_COMMIT is an instance of SVNSymbolCommit.  Yield tuples
    (source_lod, svn_revnum, cvs_symbols) where source_lod is the line
    of development and svn_revnum is the revision that should serve as
    a source, and cvs_symbols is a list of CVSSymbolItems that can be
    copied from that source.  The groups are returned in arbitrary
    order."""

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
        yield (lod, revnum, cvs_symbols)

  def _get_all_files(self, node):
    """Generate all of the CVSFiles under NODE."""

    for cvs_path in node:
      subnode = node[cvs_path]
      if subnode is None:
        yield cvs_path
      else:
        for sub_cvs_path in self._get_all_files(subnode):
          yield sub_cvs_path

  def _is_simple_copy(self, svn_commit, source_groups):
    """Return True iff SVN_COMMIT can be created as a simple copy.

    SVN_COMMIT is an SVNTagCommit.  Return True iff it can be created
    as a simple copy from an existing revision (i.e., if the fixup
    branch can be avoided for this tag creation)."""

    # The first requirement is that there be exactly one source:
    if len(source_groups) != 1:
      return False

    (source_lod, svn_revnum, cvs_symbols) = source_groups[0]

    # The second requirement is that the destionation LOD not already
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
      source_node = self._mirror.get_current_lod_directory(source_lod)
    except KeyError:
      raise InternalError('Source %r does not exist' % (source_lod,))
    cvs_file_set = set([cvs_symbol.cvs_file for cvs_symbol in cvs_symbols])
    for cvs_file in self._get_all_files(source_node):
      try:
        cvs_file_set.remove(cvs_file)
      except KeyError:
        return False
    return not cvs_file_set

  def _get_source_mark(self, source_lod, revnum):
    """Return the mark active at REVNUM on SOURCE_LOD."""

    modifications = self._marks[source_lod]
    i = bisect.bisect_left(modifications, (revnum + 1,)) - 1
    (revnum, mark) = modifications[i]
    return mark

  def _process_symbol_commit(
        self, svn_commit, git_branch, source_groups, mark
        ):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    self.f.write('commit %s\n' % (git_branch,))
    self.f.write('mark :%d\n' % (mark,))
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))

    for (source_lod, source_revnum, cvs_symbols,) in source_groups:
      self.f.write(
          'merge :%d\n'
          % (self._get_source_mark(source_lod, source_revnum),)
          )

    for (source_lod, source_revnum, cvs_symbols,) in source_groups:
      for cvs_symbol in cvs_symbols:
        self.revision_writer.branch_file(cvs_symbol)

    self.f.write('\n')

  def process_branch_commit(self, svn_commit):
    self._mirror.start_commit(svn_commit.revnum)
    source_groups = list(self._get_source_groups(svn_commit))
    self._process_symbol_commit(
        svn_commit, 'refs/heads/%s' % (svn_commit.symbol.name,),
        source_groups,
        self._create_commit_mark(svn_commit.symbol, svn_commit.revnum),
        )
    self._mirror.end_commit()

  def _set_tag(self, svn_commit, mark, author, log_msg):
    self.f.write('tag %s\n' % (svn_commit.symbol.name,))
    self.f.write('from :%d\n' % (mark,))
    self.f.write(
        'tagger %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))

  def process_tag_commit(self, svn_commit):
    # FIXME: For now we create a fixup branch with the same name as
    # the tag, then the tag.  We never delete the fixup branch.  Also,
    # a fixup branch is created even if the tag could be created from
    # a single source.
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    self._mirror.start_commit(svn_commit.revnum)

    source_groups = list(self._get_source_groups(svn_commit))
    if self._is_simple_copy(svn_commit, source_groups):
      (source_lod, source_revnum, cvs_symbols) = source_groups[0]
      Log().debug(
          '%s will be created via a simple copy from %s:r%d'
          % (svn_commit.symbol, source_lod, source_revnum,)
          )
      mark = self._get_source_mark(source_lod, source_revnum)
      self._set_tag(svn_commit, mark, author, log_msg)
    else:
      Log().debug(
          '%s will be created via a fixup branch' % (svn_commit.symbol,)
          )
      mark = self._create_commit_mark(svn_commit.symbol, svn_commit.revnum)
      self._process_symbol_commit(
          svn_commit, FIXUP_BRANCH_NAME, source_groups, mark
          )
      self._set_tag(svn_commit, mark, author, log_msg)
      self.f.write('reset %s\n' % (FIXUP_BRANCH_NAME,))
      self.f.write('\n')

    self._mirror.end_commit()

  def cleanup(self):
    self.revision_writer.finish()
    self._mirror.close()
    self.f.close()
    del self.f
    self._symbolings_reader.close()
    del self._symbolings_reader


