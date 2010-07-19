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

"""This module defines some passes that can be used for debugging cv2svn."""


from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import FatalException
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.log import logger
from cvs2svn_lib.pass_manager import Pass
from cvs2svn_lib.project import read_projects
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.cvs_path_database import CVSPathDatabase
from cvs2svn_lib.symbol_database import SymbolDatabase
from cvs2svn_lib.cvs_item_database import OldCVSItemStore
from cvs2svn_lib.cvs_item_database import IndexedCVSItemStore


class CheckDependenciesPass(Pass):
  """Check that the dependencies are self-consistent."""

  def __init__(self):
    Pass.__init__(self)

  def register_artifacts(self):
    self._register_temp_file_needed(config.PROJECTS)
    self._register_temp_file_needed(config.SYMBOL_DB)
    self._register_temp_file_needed(config.CVS_PATHS_DB)

  def iter_cvs_items(self):
    raise NotImplementedError()

  def get_cvs_item(self, item_id):
    raise NotImplementedError()

  def run(self, run_options, stats_keeper):
    Ctx()._projects = read_projects(
        artifact_manager.get_temp_file(config.PROJECTS)
        )
    Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
    self.symbol_db = SymbolDatabase()
    Ctx()._symbol_db = self.symbol_db

    logger.quiet("Checking dependency consistency...")

    fatal_errors = []
    for cvs_item in self.iter_cvs_items():
      # Check that the pred_ids and succ_ids are mutually consistent:
      for pred_id in cvs_item.get_pred_ids():
        pred = self.get_cvs_item(pred_id)
        if not cvs_item.id in pred.get_succ_ids():
          fatal_errors.append(
              '%s lists pred=%s, but not vice versa.' % (cvs_item, pred,))

      for succ_id in cvs_item.get_succ_ids():
        succ = self.get_cvs_item(succ_id)
        if not cvs_item.id in succ.get_pred_ids():
          fatal_errors.append(
              '%s lists succ=%s, but not vice versa.' % (cvs_item, succ,))

    if fatal_errors:
      raise FatalException(
          'Dependencies inconsistent:\n'
          '%s\n'
          'Exited due to fatal error(s).'
          % ('\n'.join(fatal_errors),)
          )

    self.symbol_db.close()
    self.symbol_db = None
    Ctx()._cvs_path_db.close()
    logger.quiet("Done")


class CheckItemStoreDependenciesPass(CheckDependenciesPass):
  def __init__(self, cvs_items_store_file):
    CheckDependenciesPass.__init__(self)
    self.cvs_items_store_file = cvs_items_store_file

  def register_artifacts(self):
    CheckDependenciesPass.register_artifacts(self)
    self._register_temp_file_needed(self.cvs_items_store_file)

  def iter_cvs_items(self):
    cvs_item_store = OldCVSItemStore(
        artifact_manager.get_temp_file(self.cvs_items_store_file))

    for cvs_file_items in cvs_item_store.iter_cvs_file_items():
      self.current_cvs_file_items = cvs_file_items
      for cvs_item in cvs_file_items.values():
        yield cvs_item

    del self.current_cvs_file_items

    cvs_item_store.close()

  def get_cvs_item(self, item_id):
    return self.current_cvs_file_items[item_id]


class CheckIndexedItemStoreDependenciesPass(CheckDependenciesPass):
  def __init__(self, cvs_items_store_file, cvs_items_store_index_file):
    CheckDependenciesPass.__init__(self)
    self.cvs_items_store_file = cvs_items_store_file
    self.cvs_items_store_index_file = cvs_items_store_index_file

  def register_artifacts(self):
    CheckDependenciesPass.register_artifacts(self)
    self._register_temp_file_needed(self.cvs_items_store_file)
    self._register_temp_file_needed(self.cvs_items_store_index_file)

  def iter_cvs_items(self):
    return self.cvs_item_store.itervalues()

  def get_cvs_item(self, item_id):
    return self.cvs_item_store[item_id]

  def run(self, run_options, stats_keeper):
    self.cvs_item_store = IndexedCVSItemStore(
        artifact_manager.get_temp_file(self.cvs_items_store_file),
        artifact_manager.get_temp_file(self.cvs_items_store_index_file),
        DB_OPEN_READ)

    CheckDependenciesPass.run(self, run_options, stats_keeper)

    self.cvs_item_store.close()
    self.cvs_item_store = None


