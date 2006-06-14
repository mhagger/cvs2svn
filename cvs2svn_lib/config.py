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

"""This module contains various configuration constants used by cvs2svn."""


from cvs2svn_lib.boolean import *


SVN_KEYWORDS_VALUE = 'Author Date Id Revision'

# These files are related to the cleaning and sorting of CVS revisions,
# for commit grouping.  See design-notes.txt for details.
ALL_REVS_DATAFILE = 'cvs2svn-a-revs.txt'
CLEAN_REVS_DATAFILE = 'cvs2svn-c-revs.txt'
SORTED_REVS_DATAFILE = 'cvs2svn-s-revs.txt'
RESYNC_DATAFILE = 'cvs2svn-resync.txt'

# This file contains a marshalled copy of all the statistics that we
# gather throughout the various runs of cvs2svn.  The data stored as a
# marshalled dictionary.
STATISTICS_FILE = 'cvs2svn-statistics'

# This text file contains records (1 per line) that describe svn
# filesystem paths that are the opening and closing source revisions
# for copies to tags and branches.  The format is as follows:
#
# SYMBOL_NAME SVN_REVNUM TYPE CVS_FILE_ID
#
# Where type is either OPENING or CLOSING.  The SYMBOL_NAME and
# SVN_REVNUM are the primary and secondary sorting criteria for
# creating SYMBOL_OPENINGS_CLOSINGS_SORTED.  CVS_FILE_ID is the id of
# the corresponding CVSFile (in hex).
SYMBOL_OPENINGS_CLOSINGS = 'cvs2svn-symbolic-names.txt'
# A sorted version of the above file.
SYMBOL_OPENINGS_CLOSINGS_SORTED = 'cvs2svn-symbolic-names-s.txt'

# This file is a temporary file for storing symbolic_name -> closing
# CVSRevision until the end of our pass where we can look up the
# corresponding SVNRevNum for the closing revs and write these out to
# the SYMBOL_OPENINGS_CLOSINGS.
SYMBOL_CLOSINGS_TMP = 'cvs2svn-symbolic-names-closings-tmp.txt'

# Skeleton version of an svn filesystem.
# (These supersede and will eventually replace the two above.)
# See class SVNRepositoryMirror for how these work.
SVN_MIRROR_REVISIONS_DB = 'cvs2svn-svn-revisions.db'
SVN_MIRROR_NODES_DB = 'cvs2svn-svn-nodes.db'

# Offsets pointing to the beginning of each SYMBOLIC_NAME in
# SYMBOL_OPENINGS_CLOSINGS_SORTED
SYMBOL_OFFSETS_DB = 'cvs2svn-symbolic-name-offsets.db'

# Maps CVSRevision.ids (in hex) to lists of symbolic names, where the
# CVSRevision is the last such that is a source for those symbolic
# names.  For example, if branch B's number is 1.3.0.2 in this CVS
# file, and this file's 1.3 is the latest (by date) revision among
# *all* CVS files that is a source for branch B, then the
# CVSRevision.id corresponding to this file at 1.3 would list at least
# B in its list.
SYMBOL_LAST_CVS_REVS_DB = 'cvs2svn-symbol-last-cvs-revs.db'

# Maps CVSFile.id to instance.
CVS_FILES_DB = 'cvs2svn-cvs-files.db'

# Maps CVSRevision.id (in hex) to CVSRevision.
CVS_ITEMS_DB = 'cvs2svn-cvs-items.db'

# Maps CVSRevision.id (in hex) to CVSRevision after resynchronization.
CVS_ITEMS_RESYNC_DB = 'cvs2svn-cvs-items-resync.db'

# Lists all symbolic names that are tags.  Keys are strings (symbolic
# names); values are ignorable.
SYMBOL_DB = 'cvs2svn-symbols.db'

# A list all symbols.  Each line consists of the symbol name, the
# number of files in which it was used as a tag, the number of files
# in which it was used as a branch, the number of commits to such
# branches, and a list of tags and branches that are defined on
# revisions in the branch.  The fields are separated by spaces.
SYMBOL_STATISTICS_LIST = 'cvs2svn-symbol-stats.txt'

# These two databases provide a bidirectional mapping between
# CVSRevision.ids (in hex) and Subversion revision numbers.
#
# The first maps CVSRevision.id to a number; the values are not
# unique.
#
# The second maps Subversion revision numbers (as hex strings) to
# pickled SVNCommit instances.
CVS_REVS_TO_SVN_REVNUMS = 'cvs2svn-cvs-revs-to-svn-revnums.db'
SVN_COMMITS_DB = 'cvs2svn-svn-commits.db'

# How many bytes to read at a time from a pipe.  128 kiB should be
# large enough to be efficient without wasting too much memory.
PIPE_READ_SIZE = 128 * 1024

# Records the author and log message for each changeset.
# The keys are author+log digests, the same kind used to identify
# unique revisions in the .revs, etc files.  Each value is a tuple
# of two elements: '(author logmessage)'.
METADATA_DB = "cvs2svn-metadata.db"

# If this run's output is a repository, then (in the tmpdir) we use
# a dumpfile of this name for repository loads.
#
# If this run's output is a dumpfile, then this is default name of
# that dumpfile, but in the current directory (unless the user has
# specified a dumpfile path, of course, in which case it will be
# wherever the user said).
DUMPFILE = 'cvs2svn-dump'

# flush a commit if a 5 minute gap occurs.
COMMIT_THRESHOLD = 5 * 60

