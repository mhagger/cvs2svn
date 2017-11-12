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

import sys
import bisect
import time
import shutil

from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.log import logger
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.symbol import Tag
from cvs2svn_lib.cvs_item import CVSSymbol
from cvs2svn_lib.dvcs_common import DVCSOutputOption
from cvs2svn_lib.dvcs_common import MirrorUpdater
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.artifact_manager import artifact_manager

def cvs_item_is_executable(cvs_item):
  return 'svn:executable' in cvs_item.cvs_file.properties

class GitRevisionWriter(MirrorUpdater):

  def start(self, mirror, f):
    MirrorUpdater.start(self, mirror)
    self.f = f

  def _modify_file(self, cvs_item, post_commit):
    raise NotImplementedError()

  def add_file(self, cvs_rev, post_commit):
    MirrorUpdater.add_file(self, cvs_rev, post_commit)
    self._modify_file(cvs_rev, post_commit)

  def modify_file(self, cvs_rev, post_commit):
    MirrorUpdater.modify_file(self, cvs_rev, post_commit)
    self._modify_file(cvs_rev, post_commit)

  def delete_file(self, cvs_rev, post_commit):
    MirrorUpdater.delete_file(self, cvs_rev, post_commit)
    self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

  def branch_file(self, cvs_symbol):
    MirrorUpdater.branch_file(self, cvs_symbol)
    self._modify_file(cvs_symbol, post_commit=False)

  def finish(self):
    MirrorUpdater.finish(self)
    del self.f


class GitRevisionMarkWriter(GitRevisionWriter):
  def register_artifacts(self, which_pass):
    GitRevisionWriter.register_artifacts(self, which_pass)
    if Ctx().revision_collector.blob_filename is None:
      artifact_manager.register_temp_file_needed(
        config.GIT_BLOB_DATAFILE, which_pass,
        )

  def start(self, mirror, f):
    GitRevisionWriter.start(self, mirror, f)
    if Ctx().revision_collector.blob_filename is None:
      # The revision collector wrote the blobs to a temporary file;
      # copy them into f:
      logger.normal('Copying blob data to output')
      blobf = open(
          artifact_manager.get_temp_file(config.GIT_BLOB_DATAFILE), 'rb',
          )
      shutil.copyfileobj(blobf, f)
      blobf.close()

  def _modify_file(self, cvs_item, post_commit):
    if cvs_item_is_executable(cvs_item):
      mode = '100755'
    else:
      mode = '100644'

    self.f.write(
        'M %s :%d %s\n'
        % (mode, cvs_item.revision_reader_token,
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
    if cvs_item_is_executable(cvs_item):
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
    fulltext = self.revision_reader.get_content(cvs_rev)

    self.f.write('data %d\n' % (len(fulltext),))
    self.f.write(fulltext)
    self.f.write('\n')

  def finish(self):
    GitRevisionWriter.finish(self)
    self.revision_reader.finish()


class GitOutputOption(DVCSOutputOption):
  """An OutputOption that outputs to a git-fast-import formatted file.

  Members:

    dump_filename -- (string or None) the name of the file to which
        the git-fast-import commands for defining revisions will be
        written.  If None, the data will be written to stdout.

    author_transforms -- a map from CVS author names to git full name
        and email address.  See
        DVCSOutputOption.normalize_author_transforms() for information
        about the form of this parameter.

  """

  name = "Git"

  # The first mark number used for git-fast-import commit marks.  This
  # value needs to be large to avoid conflicts with blob marks.
  _first_commit_mark = 1000000000

  def __init__(
        self, revision_writer,
        dump_filename=None,
        author_transforms=None,
        tie_tag_fixup_branches=False,
        ):
    """Constructor.

    REVISION_WRITER is a GitRevisionWriter that is used to output
    either the content of revisions or a mark that was previously used
    to label a blob.

    DUMP_FILENAME is the name of the file to which the git-fast-import
    commands for defining revisions should be written.  (Please note
    that depending on the style of revision writer, the actual file
    contents might not be written to this file.)  If it is None, then
    the output is written to stdout.

    AUTHOR_TRANSFORMS is a map {cvsauthor : (fullname, email)} from
    CVS author names to git full name and email address.  All of the
    contents should either be Unicode strings or 8-bit strings encoded
    as UTF-8.

    TIE_TAG_FIXUP_BRANCHES means whether after finishing with a tag
    fixup branch, it should be psuedo-merged (ancestry linked but no
    content changes) back into its source branch, to dispose of the
    open head.

    """
    DVCSOutputOption.__init__(self)
    self.dump_filename = dump_filename
    self.revision_writer = revision_writer

    self.author_transforms = self.normalize_author_transforms(
        author_transforms
        )

    self.tie_tag_fixup_branches = tie_tag_fixup_branches

    self._mark_generator = KeyGenerator(GitOutputOption._first_commit_mark)

  def register_artifacts(self, which_pass):
    DVCSOutputOption.register_artifacts(self, which_pass)
    self.revision_writer.register_artifacts(which_pass)

  def check_symbols(self, symbol_map):
    # FIXME: What constraints does git impose on symbols?
    pass

  def setup(self, svn_rev_count):
    DVCSOutputOption.setup(self, svn_rev_count)
    if self.dump_filename is None:
      self.f = sys.stdout
    else:
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

    Return the author as a UTF-8 string in the form needed by git
    fast-import; that is, 'name <email>'."""

    cvs_author = svn_commit.get_author()
    return self._map_author(cvs_author)

  def _map_author(self, cvs_author):
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
    mark = self._create_commit_mark(lod, svn_commit.revnum)
    logger.normal(
        'Writing commit r%d on %s (mark :%d)'
        % (svn_commit.revnum, lod, mark,)
        )
    self.f.write('mark :%d\n' % (mark,))
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
    mark = self._create_commit_mark(None, svn_commit.revnum)
    logger.normal(
        'Writing post-commit r%d on Trunk (mark :%d)'
        % (svn_commit.revnum, mark,)
        )
    self.f.write('mark :%d\n' % (mark,))
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

  def describe_lod_to_user(self, lod):
    """This needs to make sense to users of the fastimported result."""
    if isinstance(lod, Trunk):
      return 'master'
    else:
      return lod.name

  def _describe_commit(self, svn_commit, lod):
      author = self._map_author(svn_commit.get_author())
      if author.endswith(" <>"):
        author = author[:-3]
      date = time.strftime(
          "%Y-%m-%d %H:%M:%S UTC", time.gmtime(svn_commit.date)
          )
      log_msg = svn_commit.get_log_msg()
      if log_msg.find('\n') != -1:
        log_msg = log_msg[:log_msg.index('\n')]
      return "%s %s %s '%s'" % (
          self.describe_lod_to_user(lod), date, author, log_msg,)

  def _process_symbol_commit(self, svn_commit, git_branch, source_groups):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    # There are two distinct cases we need to care for here:
    #  1. initial creation of a LOD
    #  2. fixup of an existing LOD to include more files, because the LOD in
    #     CVS was created piecemeal over time, with intervening commits

    # We look at _marks here, but self._mirror._get_lod_history(lod).exists()
    # might be technically more correct (though _get_lod_history is currently
    # underscore-private)
    is_initial_lod_creation = svn_commit.symbol not in self._marks

    # Create the mark, only after the check above
    mark = self._create_commit_mark(svn_commit.symbol, svn_commit.revnum)

    if is_initial_lod_creation:
      # Get the primary parent
      p_source_revnum, p_source_lod, p_cvs_symbols = source_groups[0]
      try:
        p_source_node = self._mirror.get_old_lod_directory(
            p_source_lod, p_source_revnum
            )
      except KeyError:
        raise InternalError('Source %r does not exist' % (p_source_lod,))
      cvs_files_to_delete = set(self._get_all_files(p_source_node))

      for (source_revnum, source_lod, cvs_symbols,) in source_groups:
        for cvs_symbol in cvs_symbols:
          cvs_files_to_delete.discard(cvs_symbol.cvs_file)

    self.f.write('commit %s\n' % (git_branch,))
    self.f.write('mark :%d\n' % (mark,))
    self.f.write('committer %s %d +0000\n' % (author, svn_commit.date,))
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))

    # Only record actual DVCS ancestry for the primary sprout parent,
    # all the rest are effectively cherrypicks.
    if is_initial_lod_creation:
      self.f.write(
          'from :%d\n'
          % (self._get_source_mark(p_source_lod, p_source_revnum),)
          )

    for (source_revnum, source_lod, cvs_symbols,) in source_groups:
      for cvs_symbol in cvs_symbols:
        self.revision_writer.branch_file(cvs_symbol)

    if is_initial_lod_creation:
      for cvs_file in cvs_files_to_delete:
        self.f.write('D %s\n' % (cvs_file.cvs_path,))

    self.f.write('\n')
    return mark

  def process_branch_commit(self, svn_commit):
    self._mirror.start_commit(svn_commit.revnum)

    source_groups = self._get_source_groups(svn_commit)
    if self._is_simple_copy(svn_commit, source_groups):
      (source_revnum, source_lod, cvs_symbols) = source_groups[0]
      logger.debug(
          '%s will be created via a simple copy from %s:r%d'
          % (svn_commit.symbol, source_lod, source_revnum,)
          )
      mark = self._get_source_mark(source_lod, source_revnum)
      self._set_symbol(svn_commit.symbol, mark)
      self._mirror.copy_lod(source_lod, svn_commit.symbol, source_revnum)
      self._set_lod_mark(svn_commit.symbol, svn_commit.revnum, mark)
    else:
      logger.debug(
          '%s will be created via fixup commit(s)' % (svn_commit.symbol,)
          )
      self._process_symbol_commit(
          svn_commit, 'refs/heads/%s' % (svn_commit.symbol.name,),
          source_groups,
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
    # The branch name to use for the "tag fixup branches".  The
    # git-fast-import documentation suggests using 'TAG_FIXUP'
    # (outside of the refs/heads namespace), but this is currently
    # broken.  Use a name containing '.', which is not allowed in CVS
    # symbols, to avoid conflicts (though of course a conflict could
    # still result if the user requests symbol transformations).
    return 'refs/heads/TAG.FIXUP'

  def process_tag_commit(self, svn_commit):
    # FIXME: For now we create a fixup branch with the same name as
    # the tag, then the tag.  We never delete the fixup branch.
    self._mirror.start_commit(svn_commit.revnum)

    source_groups = self._get_source_groups(svn_commit)
    if self._is_simple_copy(svn_commit, source_groups):
      (source_revnum, source_lod, cvs_symbols) = source_groups[0]
      logger.debug(
          '%s will be created via a simple copy from %s:r%d'
          % (svn_commit.symbol, source_lod, source_revnum,)
          )
      mark = self._get_source_mark(source_lod, source_revnum)
      self._set_symbol(svn_commit.symbol, mark)
      self._mirror.copy_lod(source_lod, svn_commit.symbol, source_revnum)
      self._set_lod_mark(svn_commit.symbol, svn_commit.revnum, mark)
    else:
      logger.debug(
          '%s will be created via a fixup branch' % (svn_commit.symbol,)
          )

      fixup_branch_name = self.get_tag_fixup_branch_name(svn_commit)

      # Create the fixup branch (which might involve making more than
      # one commit):
      mark = self._process_symbol_commit(
          svn_commit, fixup_branch_name, source_groups
          )

      # Store the mark of the last commit to the fixup branch as the
      # value of the tag:
      self._set_symbol(svn_commit.symbol, mark)
      self.f.write('reset %s\n' % (fixup_branch_name,))
      self.f.write('\n')

      if self.tie_tag_fixup_branches:
        source_lod = source_groups[0][1]
        source_lod_git_branch = \
            'refs/heads/%s' % (getattr(source_lod, 'name', 'master'),)

        mark2 = self._create_commit_mark(source_lod, svn_commit.revnum)
        author = self._map_author(Ctx().username)
        log_msg = self._get_log_msg_for_ancestry_tie(svn_commit)

        self.f.write('commit %s\n' % (source_lod_git_branch,))
        self.f.write('mark :%d\n' % (mark2,))
        self.f.write('committer %s %d +0000\n' % (author, svn_commit.date,))
        self.f.write('data %d\n' % (len(log_msg),))
        self.f.write('%s\n' % (log_msg,))

        self.f.write(
            'merge :%d\n'
            % (mark,)
            )

        self.f.write('\n')

    self._mirror.end_commit()

  def _get_log_msg_for_ancestry_tie(self, svn_commit):
    return Ctx().text_wrapper.fill(
        Ctx().tie_tag_ancestry_message % {
            'symbol_name' : svn_commit.symbol.name,
            }
        )

  def cleanup(self):
    DVCSOutputOption.cleanup(self)
    self.revision_writer.finish()
    if self.dump_filename is not None:
      self.f.close()
    del self.f


