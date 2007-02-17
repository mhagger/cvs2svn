# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006 CollabNet.  All rights reserved.
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

"""This module contains classes to store changesets."""


from __future__ import generators

import struct

from cvs2svn_lib.boolean import *
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.changeset import Changeset
from cvs2svn_lib.changeset import RevisionChangeset
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import SymbolChangeset
from cvs2svn_lib.record_table import UnsignedIntegerPacker
from cvs2svn_lib.record_table import RecordTable
from cvs2svn_lib.database import PrimedPDatabase


def CVSItemToChangesetTable(filename, mode):
  return RecordTable(filename, mode, UnsignedIntegerPacker())


class ChangesetDatabase:
  def __init__(self, filename, mode):
    self.db = PrimedPDatabase(
        filename, mode,
        (Changeset, RevisionChangeset, OrderedChangeset, SymbolChangeset,))

  def store(self, changeset):
    self.db['%x' % changeset.id] = changeset

  def __getitem__(self, id):
    return self.db['%x' % id]

  def __delitem__(self, id):
    del self.db['%x' % id]

  def keys(self):
    return [int(key, 16) for key in self.db.keys()]

  def close(self):
    self.db.close()


