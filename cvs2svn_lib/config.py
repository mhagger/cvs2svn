# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
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

# The default names for the trunk/branches/tags directory for each
# project:
DEFAULT_TRUNK_BASE = 'trunk'
DEFAULT_BRANCHES_BASE = 'branches'
DEFAULT_TAGS_BASE = 'tags'

SVNADMIN_EXECUTABLE = 'svnadmin'
CO_EXECUTABLE = 'co'
CVS_EXECUTABLE = 'cvs'

# A pickled list of the projects defined for this conversion.
PROJECTS = 'projects.pck'

# A file holding the Serializer to be used for CVS_REVS_*_DATAFILE and
# CVS_SYMBOLS_*_DATAFILE:
ITEM_SERIALIZER = 'item-serializer.pck'

# The first file contains the CVSRevisions in a form that can be
# sorted to deduce preliminary Changesets.  The second file is the
# sorted version of the first.
CVS_REVS_DATAFILE = 'revs.dat'
CVS_REVS_SORTED_DATAFILE = 'revs-s.dat'

# The first file contains the CVSSymbols in a form that can be sorted
# to deduce preliminary Changesets.  The second file is the sorted
# version of the first.
CVS_SYMBOLS_DATAFILE = 'symbols.dat'
CVS_SYMBOLS_SORTED_DATAFILE = 'symbols-s.dat'

# A mapping from CVSItem id to Changeset id.
CVS_ITEM_TO_CHANGESET = 'cvs-item-to-changeset.dat'

# A mapping from CVSItem id to Changeset id, after the
# RevisionChangeset loops have been broken.
CVS_ITEM_TO_CHANGESET_REVBROKEN = 'cvs-item-to-changeset-revbroken.dat'

# A mapping from CVSItem id to Changeset id, after the SymbolChangeset
# loops have been broken.
CVS_ITEM_TO_CHANGESET_SYMBROKEN = 'cvs-item-to-changeset-symbroken.dat'

# A mapping from CVSItem id to Changeset id, after all Changeset
# loops have been broken.
CVS_ITEM_TO_CHANGESET_ALLBROKEN = 'cvs-item-to-changeset-allbroken.dat'

# A mapping from id to Changeset.
CHANGESETS_INDEX = 'changesets-index.dat'
CHANGESETS_STORE = 'changesets.pck'

# A mapping from id to Changeset, after the RevisionChangeset loops
# have been broken.
CHANGESETS_REVBROKEN_INDEX = 'changesets-revbroken-index.dat'
CHANGESETS_REVBROKEN_STORE = 'changesets-revbroken.pck'

# A mapping from id to Changeset, after the RevisionChangesets have
# been sorted and converted into OrderedChangesets.
CHANGESETS_REVSORTED_INDEX = 'changesets-revsorted-index.dat'
CHANGESETS_REVSORTED_STORE = 'changesets-revsorted.pck'

# A mapping from id to Changeset, after the SymbolChangeset loops have
# been broken.
CHANGESETS_SYMBROKEN_INDEX = 'changesets-symbroken-index.dat'
CHANGESETS_SYMBROKEN_STORE = 'changesets-symbroken.pck'

# A mapping from id to Changeset, after all Changeset loops have been
# broken.
CHANGESETS_ALLBROKEN_INDEX = 'changesets-allbroken-index.dat'
CHANGESETS_ALLBROKEN_STORE = 'changesets-allbroken.pck'

# The RevisionChangesets in commit order.  Each line contains the
# changeset id and timestamp of one changeset, in hexadecimal, in the
# order that the changesets should be committed to svn.
CHANGESETS_SORTED_DATAFILE = 'changesets-s.txt'

# A file containing a marshalled copy of all the statistics that have
# been gathered so far is written at the end of each pass as a
# marshalled dictionary.  This is the pattern used to generate the
# filenames.
STATISTICS_FILE = 'statistics-%02d.pck'

# This text file contains records (1 per line) that describe openings
# and closings for copies to tags and branches.  The format is as
# follows:
#
#     SYMBOL_ID SVN_REVNUM TYPE CVS_SYMBOL_ID
#
# where type is either OPENING or CLOSING.  CVS_SYMBOL_ID is the id of
# the CVSSymbol whose opening or closing is being described (in hex).
SYMBOL_OPENINGS_CLOSINGS = 'symbolic-names.txt'
# A sorted version of the above file.  SYMBOL_ID and SVN_REVNUM are
# the primary and secondary sorting criteria.  It is important that
# SYMBOL_IDs be located together to make it quick to read them at
# once.  The order of SVN_REVNUM is only important because it is
# assumed by some internal consistency checks.
SYMBOL_OPENINGS_CLOSINGS_SORTED = 'symbolic-names-s.txt'

# Skeleton version of the repository filesystem.  See class
# RepositoryMirror for how these work.
MIRROR_NODES_INDEX_TABLE = 'mirror-nodes-index.dat'
MIRROR_NODES_STORE = 'mirror-nodes.pck'

# Offsets pointing to the beginning of each symbol's records in
# SYMBOL_OPENINGS_CLOSINGS_SORTED.  This file contains a pickled map
# from symbol_id to file offset.
SYMBOL_OFFSETS_DB = 'symbol-offsets.pck'

# Pickled map of CVSPath.id to instance.
CVS_PATHS_DB = 'cvs-paths.pck'

# A series of records.  The first is a pickled serializer.  Each
# subsequent record is a serialized list of all CVSItems applying to a
# CVSFile.
CVS_ITEMS_STORE = 'cvs-items.pck'

# The same as above, but with the CVSItems ordered in groups based on
# their initial changesets.  CVSItems will usually be accessed one
# changeset at a time, so this ordering helps disk locality (even
# though some of the changesets will later be broken up).
CVS_ITEMS_SORTED_INDEX_TABLE = 'cvs-items-sorted-index.dat'
CVS_ITEMS_SORTED_STORE = 'cvs-items-sorted.pck'

# A record of all symbolic names that will be processed in the
# conversion.  This file contains a pickled list of TypedSymbol
# objects.
SYMBOL_DB = 'symbols.pck'

# A pickled list of the statistics for all symbols.  Each entry in the
# list is an instance of cvs2svn_lib.symbol_statistics._Stats.
SYMBOL_STATISTICS = 'symbol-statistics.pck'

# These two databases provide a bidirectional mapping between
# CVSRevision.ids (in hex) and Subversion revision numbers.
#
# The first maps CVSRevision.id to the SVN revision number of which it
# is a part (more than one CVSRevision can map to the same SVN
# revision number).
#
# The second maps Subversion revision numbers (as hex strings) to
# pickled SVNCommit instances.
CVS_REVS_TO_SVN_REVNUMS = 'cvs-revs-to-svn-revnums.dat'

# This database maps Subversion revision numbers to pickled SVNCommit
# instances.
SVN_COMMITS_INDEX_TABLE = 'svn-commits-index.dat'
SVN_COMMITS_STORE = 'svn-commits.pck'

# How many bytes to read at a time from a pipe.  128 kiB should be
# large enough to be efficient without wasting too much memory.
PIPE_READ_SIZE = 128 * 1024

# Records the author and log message for each changeset.  The database
# contains a map metadata_id -> (author, logmessage).  Each
# CVSRevision that is eligible to be combined into the same SVN commit
# is assigned the same id.  Note that the (author, logmessage) pairs
# are not necessarily all distinct; other data are taken into account
# when constructing ids.
METADATA_INDEX_TABLE = 'metadata-index.dat'
METADATA_STORE = 'metadata.pck'

# The same, after it has been cleaned up for the chosen output option:
METADATA_CLEAN_INDEX_TABLE = 'metadata-clean-index.dat'
METADATA_CLEAN_STORE = 'metadata-clean.pck'

# The following four databases are used in conjunction with --use-internal-co.

# Records the RCS deltas for all CVS revisions.  The deltas are to be
# applied forward, i.e. those from trunk are reversed wrt RCS.
RCS_DELTAS_INDEX_TABLE = 'rcs-deltas-index.dat'
RCS_DELTAS_STORE = 'rcs-deltas.pck'

# Records the revision tree of each RCS file.  The format is a list of
# list of integers.  The outer list holds lines of development, the inner list
# revisions within the LODs, revisions are CVSItem ids.  Branches "closer
# to the trunk" appear later.  Revisions are sorted by reverse chronological
# order.  The last revision of each branch is the revision it sprouts from.
# Revisions that represent deletions at the end of a branch are omitted.
RCS_TREES_INDEX_TABLE = 'rcs-trees-index.dat'
RCS_TREES_STORE = 'rcs-trees.pck'

# At any given time during OutputPass, holds the full text of each CVS
# revision that was checked out already and still has descendants that will
# be checked out.
CVS_CHECKOUT_DB = 'cvs-checkout.db'

# End of DBs related to --use-internal-co.

# Hold the generated blob content for the git back end.
GIT_BLOB_DATAFILE = "git-blobs.dat"

# flush a commit if a 5 minute gap occurs.
COMMIT_THRESHOLD = 5 * 60

