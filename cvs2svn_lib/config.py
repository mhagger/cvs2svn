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

# The default names for the trunk/branches/tags directory for each
# project:
DEFAULT_TRUNK_BASE = 'trunk'
DEFAULT_BRANCHES_BASE = 'branches'
DEFAULT_TAGS_BASE = 'tags'

SVNADMIN_EXECUTABLE = 'svnadmin'
CO_EXECUTABLE = 'co'
CVS_EXECUTABLE = 'cvs'
SORT_EXECUTABLE = 'sort'

# The first file contains enough information about each CVSRevision to
# deduce preliminary Changesets.  The second file is a sorted version
# of the first.
CVS_REVS_SUMMARY_DATAFILE = 'cvs2svn-revs-summary.txt'
CVS_REVS_SUMMARY_SORTED_DATAFILE = 'cvs2svn-revs-summary-s.txt'

# The first file contains enough information about each CVSSymbol to
# deduce preliminary Changesets.  The second file is a sorted version
# of the first.
CVS_SYMBOLS_SUMMARY_DATAFILE = 'cvs2svn-symbols-summary.txt'
CVS_SYMBOLS_SUMMARY_SORTED_DATAFILE = 'cvs2svn-symbols-summary-s.txt'

# A mapping from CVSItem id to Changeset id.
CVS_ITEM_TO_CHANGESET = 'cvs2svn-cvs-item-to-changeset.dat'

# A mapping from CVSItem id to Changeset id, after the
# RevisionChangeset loops have been broken.
CVS_ITEM_TO_CHANGESET_REVBROKEN = \
    'cvs2svn-cvs-item-to-changeset-revbroken.dat'

# A mapping from CVSItem id to Changeset id, after all Changeset
# loops have been broken.
CVS_ITEM_TO_CHANGESET_ALLBROKEN = \
    'cvs2svn-cvs-item-to-changeset-allbroken.dat'

# A mapping from id to Changeset.
CHANGESETS_DB = 'cvs2svn-changesets.db'

# A mapping from id to Changeset, after the RevisionChangeset loops
# have been broken.
CHANGESETS_REVBROKEN_DB = 'cvs2svn-changesets-revbroken.db'

# A mapping from id to Changeset, after the RevisionChangesets have
# been sorted and converted into OrderedChangesets.
CHANGESETS_REVSORTED_DB = 'cvs2svn-changesets-revsorted.db'

# A mapping from id to Changeset, after all Changeset loops have been
# broken.
CHANGESETS_ALLBROKEN_DB = 'cvs2svn-changesets-allbroken.db'

# The RevisionChangesets in commit order.  Each line contains the
# changeset id and timestamp of one changeset, in hexadecimal, in the
# order that the changesets should be committed to svn.
CHANGESETS_SORTED_DATAFILE = 'cvs2svn-changesets-s.txt'

# This file contains a marshalled copy of all the statistics that we
# gather throughout the various runs of cvs2svn.  The data stored as a
# marshalled dictionary.
STATISTICS_FILE = 'cvs2svn-statistics.pck'

# This text file contains records (1 per line) that describe svn
# filesystem paths that are the opening and closing source revisions
# for copies to tags and branches.  The format is as follows:
#
#     SYMBOL_ID SVN_REVNUM TYPE BRANCH_ID CVS_FILE_ID
#
# Where type is either OPENING or CLOSING.  The SYMBOL_ID and
# SVN_REVNUM are the primary and secondary sorting criteria for
# creating SYMBOL_OPENINGS_CLOSINGS_SORTED.  BRANCH_ID is the symbol
# id of the branch where this opening or closing happened (in hex), or
# '*' for the default branch.  CVS_FILE_ID is the id of the
# corresponding CVSFile (in hex).
SYMBOL_OPENINGS_CLOSINGS = 'cvs2svn-symbolic-names.txt'
# A sorted version of the above file.
SYMBOL_OPENINGS_CLOSINGS_SORTED = 'cvs2svn-symbolic-names-s.txt'

# Skeleton version of an svn filesystem.  See class
# SVNRepositoryMirror for how these work.
SVN_MIRROR_REVISIONS_TABLE = 'cvs2svn-svn-revisions.dat'
SVN_MIRROR_NODES_INDEX_TABLE = 'cvs2svn-svn-nodes-index.dat'
SVN_MIRROR_NODES_STORE = 'cvs2svn-svn-nodes.pck'

# Offsets pointing to the beginning of each symbol's records in
# SYMBOL_OPENINGS_CLOSINGS_SORTED.  This file contains a pickled map
# from symbol_id to file offset.
SYMBOL_OFFSETS_DB = 'cvs2svn-symbol-offsets.pck'

# Maps changeset_ids (in hex) to lists of symbol ids for which the
# changeset is the last changeset that is a source for that symbol.
# In other words, after the changeset is committed, all of the symbols
# in the list can be filled.  For example, if branch B's number is
# 1.3.0.2 in this CVS file, and this file's 1.3 is the latest (by
# date) revision among *all* CVS files that is a source for branch B,
# then the changeset.id for the changeset holding this file at 1.3
# would list the symbol id for branch B in its list.
SYMBOL_LAST_CHANGESETS_DB = 'cvs2svn-symbol-last-changesets.db'

# Pickled map of CVSFile.id to instance.
CVS_FILES_DB = 'cvs2svn-cvs-files.pck'

# A series of records.  The first is a pickled serializer.  Each
# subsequent record is a serialized list of all CVSItems applying to a
# CVSFile.
CVS_ITEMS_STORE = 'cvs2svn-cvs-items.pck'

# A database of filtered CVSItems.  Excluded symbols have been
# discarded (and the dependencies of the remaining CVSItems fixed up).
# These two files are used within an IndexedCVSItemStore; the first is
# a map id-> offset, and the second contains the pickled CVSItems at
# the specified offsets.
CVS_ITEMS_FILTERED_INDEX_TABLE = 'cvs2svn-cvs-items-filtered-index.pck'
CVS_ITEMS_FILTERED_STORE = 'cvs2svn-cvs-items-filtered.pck'

# A record of all symbolic names that will be processed in the
# conversion.  This file contains a pickled list of TypedSymbol
# objects.
SYMBOL_DB = 'cvs2svn-symbols.pck'

# A pickled list of the statistics for all symbols.  Each entry in the
# list is an instance of cvs2svn_lib.symbol_statistics._Stats.
SYMBOL_STATISTICS = 'cvs2svn-symbol-statistics.pck'

# These two databases provide a bidirectional mapping between
# CVSRevision.ids (in hex) and Subversion revision numbers.
#
# The first maps CVSRevision.id to the SVN revision number of which it
# is a part (more than one CVSRevision can map to the same SVN
# revision number).
#
# The second maps Subversion revision numbers (as hex strings) to
# pickled SVNCommit instances.
CVS_REVS_TO_SVN_REVNUMS = 'cvs2svn-cvs-revs-to-svn-revnums.dat'
SVN_COMMITS_DB = 'cvs2svn-svn-commits.db'

# How many bytes to read at a time from a pipe.  128 kiB should be
# large enough to be efficient without wasting too much memory.
PIPE_READ_SIZE = 128 * 1024

# Records the author and log message for each changeset.  The database
# contains a map metadata_id -> (author, logmessage).  Each
# CVSRevision that is eligible to be combined into the same SVN commit
# is assigned the same id.  Note that the (author, logmessage) pairs
# are not necessarily all distinct; other data are taken into account
# when constructing ids.
METADATA_DB = "cvs2svn-metadata.db"

# The following four databases are used in conjunction with --use-internal-co.

# Records the RCS deltas for all CVS revisions.  The deltas are to be
# applied forward, i.e. those from trunk are reversed wrt RCS.
RCS_DELTAS_INDEX_TABLE = "cvs2svn-rcs-deltas-index.dat"
RCS_DELTAS_STORE = "cvs2svn-rcs-deltas.pck"

# Records the revision tree of each RCS file.  The format is a list of
# list of integers.  The outer list holds lines of development, the inner list
# revisions within the LODs, revisions are CVSItem ids.  Branches "closer
# to the trunk" appear later.  Revisions are sorted by reverse chronological
# order.  The last revision of each branch is the revision it sprouts from.
# Revisions that represent deletions at the end of a branch are omitted.
RCS_TREES_INDEX_TABLE = "cvs2svn-rcs-trees-index.dat"
RCS_TREES_STORE = "cvs2svn-rcs-trees.pck"

# Records the revision tree of each RCS file after removing revisions
# belonging to excluded branches.  Note that the branch ordering is arbitrary
# in this file.
RCS_TREES_FILTERED_INDEX_TABLE = "cvs2svn-rcs-trees-filtered-index.dat"
RCS_TREES_FILTERED_STORE = "cvs2svn-rcs-trees-filtered.pck"

# At any given time during OutputPass, holds the full text of each CVS
# revision that was checked out already and still has descendants that will
# be checked out.
CVS_CHECKOUT_DB = "cvs2svn-cvs-checkout.db"

# End of DBs related to --use-internal-co.

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

