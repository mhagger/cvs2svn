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


SVN_KEYWORDS_VALUE = 'Author Date Id Revision'

# This file appears with different suffixes at different stages of
# processing.  CVS revisions are cleaned and sorted here, for commit
# grouping.  See design-notes.txt for details.
DATAFILE = 'cvs2svn-data'

# This file contains a marshalled copy of all the statistics that we
# gather throughout the various runs of cvs2svn.  The data stored as a
# marshalled dictionary.
STATISTICS_FILE = 'cvs2svn-statistics'

# This text file contains records (1 per line) that describe svn
# filesystem paths that are the opening and closing source revisions
# for copies to tags and branches.  The format is as follows:
#
# SYMBOL_NAME SVN_REVNUM TYPE SVN_PATH
#
# Where type is either OPENING or CLOSING.  The SYMBOL_NAME and
# SVN_REVNUM are the primary and secondary sorting criteria for
# creating SYMBOL_OPENINGS_CLOSINGS_SORTED.
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

# Maps CVSRevision.unique_key()s to lists of symbolic names, where
# the CVSRevision is the last such that is a source for those symbolic
# names.  For example, if branch B's number is 1.3.0.2 in this CVS
# file, and this file's 1.3 is the latest (by date) revision among
# *all* CVS files that is a source for branch B, then the
# CVSRevision.unique_key() corresponding to this file at 1.3 would
# list at least B in its list.
SYMBOL_LAST_CVS_REVS_DB = 'cvs2svn-symbol-last-cvs-revs.db'

# Maps CVSRevision.unique_key() to corresponding line in s-revs.
###PERF Or, we could map to an offset into s-revs, instead of dup'ing
### the s-revs data in this database.
CVS_REVS_DB = 'cvs2svn-cvs-revs.db'

# Lists all symbolic names that are tags.  Keys are strings (symbolic
# names), values are ignorable.
TAGS_DB = 'cvs2svn-tags.db'

# A list all tags.  Each line consists of the tag name and the number
# of files in which it exists, separated by a space.
TAGS_LIST = 'cvs2svn-tags.txt'

# A list of all branches.  The file is stored as a plain text file
# to make it easy to look at in an editor.  Each line contains the
# branch name, the number of files where the branch is created, the
# commit count, and a list of tags and branches that are defined on
# revisions in the branch.
BRANCHES_LIST = 'cvs2svn-branches.txt'

# These two databases provide a bidirectional mapping between
# CVSRevision.unique_key()s and Subversion revision numbers.
#
# The first maps CVSRevision.unique_key() to a number; the values are
# not unique.
#
# The second maps Subversion revision numbers to tuples (c_rev_keys,
# motivating_revnum, symbolic_name, date).
#
# c_rev_keys is a list of CVSRevision.unique_key()s.
#
# If the SVNCommit is a default branch synchronization,
# motivating_revnum is the svn_revnum of the primary SVNCommit that
# motivated it; otherwise it is None.  (NOTE: Secondary commits that
# fill branches and tags also have a motivating commit, but we do not
# record it because it is (currently) not needed for anything.)
# motivating_revnum is used when generating the log message for the
# commit that synchronizes the default branch with trunk.
#
# symbolic_name is the symbolic name associated with the commit (if it
# filled a symbolic name) or None otherwise.
#
# date is the date of the commit.
CVS_REVS_TO_SVN_REVNUMS = 'cvs2svn-cvs-revs-to-svn-revnums.db'
SVN_REVNUMS_TO_CVS_REVS = 'cvs2svn-svn-revnums-to-cvs-revs.db'

# How many bytes to read at a time from a pipe.  128 kiB should be
# large enough to be efficient without wasting too much memory.
PIPE_READ_SIZE = 128 * 1024

# Record the default RCS branches, if any, for CVS filepaths.
#
# The keys are CVS filepaths, relative to the top of the repository
# and with the ",v" stripped off, so they match the cvs paths used in
# Commit.commit().  The values are vendor branch revisions, such as
# '1.1.1.1', or '1.1.1.2', or '1.1.1.96'.  The vendor branch revision
# represents the highest vendor branch revision thought to have ever
# been head of the default branch.
#
# The reason we record a specific vendor revision, rather than a
# default branch number, is that there are two cases to handle:
#
# One case is simple.  The RCS file lists a default branch explicitly
# in its header, such as '1.1.1'.  In this case, we know that every
# revision on the vendor branch is to be treated as head of trunk at
# that point in time.
#
# But there's also a degenerate case.  The RCS file does not currently
# have a default branch, yet we can deduce that for some period in the
# past it probably *did* have one.  For example, the file has vendor
# revisions 1.1.1.1 -> 1.1.1.96, all of which are dated before 1.2,
# and then it has 1.1.1.97 -> 1.1.1.100 dated after 1.2.  In this
# case, we should record 1.1.1.96 as the last vendor revision to have
# been the head of the default branch.
DEFAULT_BRANCHES_DB = 'cvs2svn-default-branches.db'

# Records the author and log message for each changeset.
# The keys are author+log digests, the same kind used to identify
# unique revisions in the .revs, etc files.  Each value is a tuple
# of two elements: '(author logmessage)'.
METADATA_DB = "cvs2svn-metadata.db"

# A temporary on-disk hash that maps CVSRevision unique keys to a new
# timestamp for that CVSRevision.  These new timestamps are created in
# pass2, and this hash is used exclusively in pass2.
TWEAKED_TIMESTAMPS_DB = "cvs2svn-fixed-timestamps.db"

REVS_SUFFIX = '.revs'
CLEAN_REVS_SUFFIX = '.c-revs'
SORTED_REVS_SUFFIX = '.s-revs'
RESYNC_SUFFIX = '.resync'

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

