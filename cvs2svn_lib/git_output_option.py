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

"""Classes for outputting the converted repository to git.

For information about the format allowed by git-fast-import, see:

    http://www.kernel.org/pub/software/scm/git/docs/git-fast-import.html

"""

import bisect

from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.dvcs_common import DVCSOutputOption
from cvs2svn_lib.dvcs_common import MirrorUpdater
from cvs2svn_lib.key_generator import KeyGenerator


class ExpectedDirectoryError(Exception):
  """A file was found where a directory was expected."""

  pass


class ExpectedFileError(Exception):
  """A directory was found where a file was expected."""

  pass


class GitRevisionWriter(MirrorUpdater):

  def start(self, mirror, f):
    super(GitRevisionWriter, self).start(mirror)
    self.f = f

  def _modify_file(self, cvs_item, post_commit):
    raise NotImplementedError()

  def add_file(self, cvs_rev, post_commit):
    super(GitRevisionWriter, self).add_file(cvs_rev, post_commit)
    self._modify_file(cvs_rev, post_commit)

  def modify_file(self, cvs_rev, post_commit):
    super(GitRevisionWriter, self).modify_file(cvs_rev, post_commit)
    self._modify_file(cvs_rev, post_commit)

  def delete_file(self, cvs_rev, post_commit):
    super(GitRevisionWriter, self).delete_file(cvs_rev, post_commit)
    self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

  def branch_file(self, cvs_symbol):
    super(GitRevisionWriter, self).branch_file(cvs_symbol)
    self._modify_file(cvs_symbol, post_commit=False)

  def finish(self):
    super(GitRevisionWriter, self).finish()
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

  def start(self, mirror, f):
    GitRevisionWriter.start(self, mirror, f)
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


def get_chunks(iterable, chunk_size):
  """Generate lists containing chunks of the output of ITERABLE.

  Each list contains at most CHUNK_SIZE items.  If CHUNK_SIZE is None,
  yield the whole contents of ITERABLE in one list."""

  if chunk_size is None:
    yield list(iterable)
  else:
    it = iter(iterable)
    while True:
      # If this call to it.next() raises StopIteration, then we have
      # no more chunks to emit, so simply pass the exception through:
      chunk = [it.next()]

      # Now try filling the rest of the chunk:
      try:
        while len(chunk) < chunk_size:
          chunk.append(it.next())
      except StopIteration:
        # The iterator was exhausted while filling chunk, but chunk
        # contains at least one element.  Yield it, then we're done.
        yield chunk
        break

      # Yield the full chunk then continue with the next chunk:
      yield chunk
      del chunk


class GitOutputOption(DVCSOutputOption):
  """An OutputOption that outputs to a git-fast-import formatted file.

  Members:

    dump_filename -- (string) the name of the file to which the
        git-fast-import commands for defining revisions will be
        written.

    author_transforms -- a map {cvsauthor : (fullname, email)} from
        CVS author names to git full name and email address.  All of
        the contents are 8-bit strings encoded as UTF-8.

  """

  name = "Git"

  # The first mark number used for git-fast-import commit marks.  This
  # value needs to be large to avoid conflicts with blob marks.
  _first_commit_mark = 1000000000

  def __init__(
        self, dump_filename, revision_writer,
        max_merges=None, author_transforms=None,
        ):
    """Constructor.

    DUMP_FILENAME is the name of the file to which the git-fast-import
    commands for defining revisions should be written.  (Please note
    that depending on the style of revision writer, the actual file
    contents might not be written to this file.)

    REVISION_WRITER is a GitRevisionWriter that is used to output
    either the content of revisions or a mark that was previously used
    to label a blob.

    MAX_MERGES can be set to an integer telling the maximum number of
    parents that can be merged into a commit at once (aside from the
    natural parent).  If it is set to None, then there is no limit.

    AUTHOR_TRANSFORMS is a map {cvsauthor : (fullname, email)} from
    CVS author names to git full name and email address.  All of the
    contents should either be Unicode strings or 8-bit strings encoded
    as UTF-8.

    """
    DVCSOutputOption.__init__(self)
    self.dump_filename = dump_filename
    self.revision_writer = revision_writer
    self.max_merges = max_merges

    self.author_transforms = self.normalize_author_transforms(author_transforms)

    self._mark_generator = KeyGenerator(GitOutputOption._first_commit_mark)

  def register_artifacts(self, which_pass):
    DVCSOutputOption.register_artifacts(self, which_pass)
    self.revision_writer.register_artifacts(which_pass)

  def check_symbols(self, symbol_map):
    # FIXME: What constraints does git impose on symbols?
    pass

  def setup(self, svn_rev_count):
    DVCSOutputOption.setup(self, svn_rev_count)
    self.f = open(self.dump_filename, 'wb')

    # The youngest revnum that has been committed so far:
    self._youngest = 0

    # A map {lod : [(revnum, mark)]} giving each of the revision
    # numbers in which there was a commit to lod, and the mark active
    # at the end of the revnum.
    self._marks = {}

    self.revision_writer.start(self._mirror, self.f)

  def _create_commit_mark(self, lod, revnum):
    mark = self._mark_generator.gen_id()
    self._set_lod_mark(lod, revnum, mark)
    return mark

  def _set_lod_mark(self, lod, revnum, mark):
    """Record MARK as the status of LOD for REVNUM.

    If there is already an entry for REVNUM, overwrite it.  If not,
    append a new entry to the self._marks list for LOD."""

    assert revnum >= self._youngest
    entry = (revnum, mark)
    try:
      modifications = self._marks[lod]
    except KeyError:
      # This LOD hasn't appeared before; create a new list and add the
      # entry:
      self._marks[lod] = [entry]
    else:
      # A record exists, so it necessarily has at least one element:
      if modifications[-1][0] == revnum:
        modifications[-1] = entry
      else:
        modifications.append(entry)
    self._youngest = revnum

  def _get_author(self, svn_commit):
    """Return the author to be used for SVN_COMMIT.

    Return the author as a UTF-8 string in the form needed by git fast-import;
    that is, 'name <email>'."""

    cvs_author = svn_commit.get_author()
    return self.author_transforms.get(cvs_author, "%s <>" % (cvs_author,))

  @staticmethod
  def _get_log_msg(svn_commit):
    return svn_commit.get_log_msg()

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

  def _get_source_mark(self, source_lod, revnum):
    """Return the mark active on SOURCE_LOD at the end of REVNUM."""

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
    self.f.write('committer %s %d +0000\n' % (author, svn_commit.date,))
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
    for groups in get_chunks(source_groups, self.max_merges):
      self._process_symbol_commit(
          svn_commit, 'refs/heads/%s' % (svn_commit.symbol.name,),
          groups,
          self._create_commit_mark(svn_commit.symbol, svn_commit.revnum),
          )
    self._mirror.end_commit()

  def _set_symbol(self, symbol, mark):
    if isinstance(symbol, Branch):
      category = 'heads'
    elif isinstance(symbol, Tag):
      category = 'tags'
    else:
      raise InternalError()
    self.f.write('reset refs/%s/%s\n' % (category, symbol.name,))
    self.f.write('from :%d\n' % (mark,))

  def get_tag_fixup_branch_name(self, svn_commit):
    # The branch name to use for the "tag fixup branches".  The git-fast-import
    # documentation suggests using 'TAG_FIXUP' (outside of the refs/heads
    # namespace), but this is currently broken.
    # Use a name containing '.', which is not allowed in CVS symbols, to avoid
    # conflicts (though of course a conflict could still result if the user
    # requests symbol transformations).
    return 'refs/heads/TAG.FIXUP'

  def process_tag_commit(self, svn_commit):
    # FIXME: For now we create a fixup branch with the same name as
    # the tag, then the tag.  We never delete the fixup branch.  Also,
    # a fixup branch is created even if the tag could be created from
    # a single source.
    self._mirror.start_commit(svn_commit.revnum)

    source_groups = list(self._get_source_groups(svn_commit))
    if self._is_simple_copy(svn_commit, source_groups):
      (source_lod, source_revnum, cvs_symbols) = source_groups[0]
      Log().debug(
          '%s will be created via a simple copy from %s:r%d'
          % (svn_commit.symbol, source_lod, source_revnum,)
          )
      mark = self._get_source_mark(source_lod, source_revnum)
      self._set_symbol(svn_commit.symbol, mark)
    else:
      Log().debug(
          '%s will be created via a fixup branch' % (svn_commit.symbol,)
          )

      fixup_branch_name = self.get_tag_fixup_branch_name(svn_commit)

      # Create the fixup branch (which might involve making more than
      # one commit):
      for groups in get_chunks(source_groups, self.max_merges):
        mark = self._create_commit_mark(svn_commit.symbol, svn_commit.revnum)
        self._process_symbol_commit(
            svn_commit, fixup_branch_name, groups, mark
            )

      # Store the mark of the last commit to the fixup branch as the
      # value of the tag:
      self._set_symbol(svn_commit.symbol, mark)
      self.f.write('reset %s\n' % (fixup_branch_name,))
      self.f.write('\n')

    self._mirror.end_commit()

  def cleanup(self):
    DVCSOutputOption.cleanup(self)
    self.revision_writer.finish()
    self.f.close()
    del self.f


