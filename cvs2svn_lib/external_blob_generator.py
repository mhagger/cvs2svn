# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2009-2010 CollabNet.  All rights reserved.
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

"""Use the generate_blobs.py script to generate git blobs.

Use a separate program, generate_blobs.py, to generate a git blob file
directly from the RCS files, setting blob marks that we choose.  This
method is very much faster then generating the blobs from within the
main program for several reasons:

* The revision fulltexts are generated using internal code (rather
  than spawning rcs or cvs once per revision).  This gain is analogous
  to the benefit of using --use-internal-co rather than --use-cvs or
  --use-rcs for cvs2svn.

* Intermediate revisions' fulltext can usually be held in RAM rather
  than being written to temporary storage, and output as they are
  generated (git-fast-import doesn't care about their order).

* The generate_blobs.py script runs in parallel to the main cvs2git
  script, allowing benefits to be had from multiple CPUs.

"""

import sys
import os
import subprocess
import cPickle as pickle

from cvs2svn_lib.common import FatalError
from cvs2svn_lib.log import logger
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.revision_manager import RevisionCollector
from cvs2svn_lib.key_generator import KeyGenerator


class ExternalBlobGenerator(RevisionCollector):
  """Have generate_blobs.py output file revisions to a blob file."""

  def __init__(self, blob_filename):
    self.blob_filename = blob_filename

  def start(self):
    self._mark_generator = KeyGenerator()
    logger.normal('Starting generate_blobs.py...')
    self._popen = subprocess.Popen(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), 'generate_blobs.py'),
            self.blob_filename,
            ],
        stdin=subprocess.PIPE,
        )

  def _process_symbol(self, cvs_symbol, cvs_file_items):
    """Record the original source of CVS_SYMBOL.

    Determine the original revision source of CVS_SYMBOL, and store it
    as the symbol's revision_reader_token."""

    cvs_source = cvs_symbol.get_cvs_revision_source(cvs_file_items)
    cvs_symbol.revision_reader_token = cvs_source.revision_reader_token

  def process_file(self, cvs_file_items):
    marks = {}
    for lod_items in cvs_file_items.iter_lods():
      for cvs_rev in lod_items.cvs_revisions:
        if not isinstance(cvs_rev, CVSRevisionDelete):
          mark = self._mark_generator.gen_id()
          cvs_rev.revision_reader_token = mark
          marks[cvs_rev.rev] = mark

    # A separate pickler is used for each dump(), so that its memo
    # doesn't grow very large.  The default ASCII protocol is used so
    # that this works without changes on systems that distinguish
    # between text and binary files.
    pickle.dump((cvs_file_items.cvs_file.rcs_path, marks), self._popen.stdin)
    self._popen.stdin.flush()

    # Now that all CVSRevisions' revision_reader_tokens are set,
    # iterate through symbols and set their tokens to those of their
    # original source revisions:
    for lod_items in cvs_file_items.iter_lods():
      if lod_items.cvs_branch is not None:
        self._process_symbol(lod_items.cvs_branch, cvs_file_items)
      for cvs_tag in lod_items.cvs_tags:
        self._process_symbol(cvs_tag, cvs_file_items)

  def finish(self):
    self._popen.stdin.close()
    logger.normal('Waiting for generate_blobs.py to finish...')
    returncode = self._popen.wait()
    if returncode:
      raise FatalError(
          'generate_blobs.py failed with return code %s.' % (returncode,)
          )
    else:
      logger.normal('generate_blobs.py is done.')


