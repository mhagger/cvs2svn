#!/usr/bin/env python

import anydbm
import marshal
import sys
import os
import getopt
import cPickle as pickle
from cStringIO import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.artifact_manager import artifact_manager


def usage():
  cmd = sys.argv[0]
  sys.stderr.write('Usage: %s OPTION [DIRECTORY]\n\n' % os.path.basename(cmd))
  sys.stderr.write(
      'Show the contents of the temporary database files created by cvs2svn\n'
      'in a structured human-readable way.\n'
      '\n'
      'OPTION is one of:\n'
      '  -R      SVNRepositoryMirror revisions table\n'
      '  -N      SVNRepositoryMirror nodes table\n'
      '  -r rev  SVNRepositoryMirror node tree for specific revision\n'
      '  -m      MetadataDatabase\n'
      '  -f      CVSPathDatabase\n'
      '  -c      PersistenceManager SVNCommit table\n'
      '  -C      PersistenceManager cvs-revs-to-svn-revnums table\n'
      '  -i      CVSItemDatabase (normal)\n'
      '  -I      CVSItemDatabase (filtered)\n'
      '  -p file Show the given file, assuming it contains a pickle.\n'
      '\n'
      'DIRECTORY is the directory containing the temporary database files.\n'
      'If omitted, the current directory is assumed.\n')
  sys.exit(1)


def print_node_tree(db, key="0", name="<rootnode>", prefix=""):
  print "%s%s (%s)" % (prefix, name, key)
  if name[:1] != "/":
    dict = marshal.loads(db[key])
    items = dict.items()
    items.sort()
    for entry in items:
      print_node_tree(db, entry[1], entry[0], prefix + "  ")


def show_int2str_db(fname):
  db = anydbm.open(fname, 'r')
  k = map(int, db.keys())
  k.sort()
  for i in k:
    print "%6d: %s" % (i, db[str(i)])

def show_str2marshal_db(fname):
  db = anydbm.open(fname, 'r')
  k = db.keys()
  k.sort()
  for i in k:
    print "%6s: %s" % (i, marshal.loads(db[i]))

def show_str2pickle_db(fname):
  db = anydbm.open(fname, 'r')
  k = db.keys()
  k.sort()
  for i in k:
    o = pickle.loads(db[i])
    print    "%6s: %r" % (i, o)
    print "        %s" % (o,)

def show_str2ppickle_db(fname):
  db = anydbm.open(fname, 'r')
  k = db.keys()
  k.remove('_')
  k.sort(key=lambda s: int(s, 16))
  u1 = pickle.Unpickler(StringIO(db['_']))
  u1.load()
  for i in k:
    u2 = pickle.Unpickler(StringIO(db[i]))
    u2.memo = u1.memo.copy()
    o = u2.load()
    print    "%6s: %r" % (i, o)
    print "        %s" % (o,)

def show_cvsitemstore():
  for cvs_file_items in Ctx()._cvs_items_db.iter_cvs_file_items():
    items = cvs_file_items.values()
    items.sort(key=lambda i: i.id)
    for item in items:
      print    "%6x: %r" % (item.id, item,)


def show_filtered_cvs_item_store():
  from cvs2svn_lib.cvs_item_database import IndexedCVSItemStore
  db = IndexedCVSItemStore(
      artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_STORE),
      artifact_manager.get_temp_file(config.CVS_ITEMS_FILTERED_INDEX_TABLE),
      DB_OPEN_READ)

  ids = list(db.iterkeys())
  ids.sort()
  for id in ids:
    cvs_item = db[id]
    print    "%6x: %r" % (cvs_item.id, cvs_item,)



class ProjectList:
  """A mock project-list that can be assigned to Ctx()._projects."""

  def __init__(self):
    self.projects = {}

  def __getitem__(self, i):
    return self.projects.setdefault(i, 'Project%d' % i)


def prime_ctx():
  def rf(filename):
    artifact_manager.register_temp_file(filename, None)

  from cvs2svn_lib.common import DB_OPEN_READ
  from cvs2svn_lib.symbol_database import SymbolDatabase
  from cvs2svn_lib.cvs_path_database import CVSPathDatabase
  rf(config.CVS_PATHS_DB)
  rf(config.SYMBOL_DB)
  from cvs2svn_lib.cvs_item_database import OldCVSItemStore
  from cvs2svn_lib.metadata_database import MetadataDatabase
  rf(config.METADATA_DB)
  rf(config.CVS_ITEMS_STORE)
  rf(config.CVS_ITEMS_FILTERED_STORE)
  rf(config.CVS_ITEMS_FILTERED_INDEX_TABLE)
  artifact_manager.pass_started(None)

  Ctx()._projects = ProjectList()
  Ctx()._symbol_db = SymbolDatabase()
  Ctx()._cvs_path_db = CVSPathDatabase(DB_OPEN_READ)
  Ctx()._cvs_items_db = OldCVSItemStore(
      artifact_manager.get_temp_file(config.CVS_ITEMS_STORE)
      )
  Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)

def main():
  try:
    opts, args = getopt.getopt(sys.argv[1:], "RNr:mlfcCiIp:")
  except getopt.GetoptError:
    usage()

  if len(args) > 1 or len(opts) != 1:
    usage()

  if len(args) == 1:
    Ctx().tmpdir = args[0]

  for o, a in opts:
    if o == "-R":
      show_int2str_db(config.SVN_MIRROR_REVISIONS_TABLE)
    elif o == "-N":
      show_str2marshal_db(
          config.SVN_MIRROR_NODES_STORE,
          config.SVN_MIRROR_NODES_INDEX_TABLE
          )
    elif o == "-r":
      try:
        revnum = int(a)
      except ValueError:
        sys.stderr.write('Option -r requires a valid revision number\n')
        sys.exit(1)
      db = anydbm.open(config.SVN_MIRROR_REVISIONS_TABLE, 'r')
      key = db[str(revnum)]
      db.close()
      db = anydbm.open(config.SVN_MIRROR_NODES_STORE, 'r')
      print_node_tree(db, key, "Revision %d" % revnum)
    elif o == "-m":
      show_str2marshal_db(config.METADATA_DB)
    elif o == "-f":
      prime_ctx()
      cvs_files = list(Ctx()._cvs_path_db.itervalues())
      cvs_files.sort()
      for cvs_file in cvs_files:
        print '%6x: %s' % (cvs_file.id, cvs_file,)
    elif o == "-c":
      prime_ctx()
      show_str2ppickle_db(
          config.SVN_COMMITS_INDEX_TABLE, config.SVN_COMMITS_STORE
          )
    elif o == "-C":
      show_str2marshal_db(config.CVS_REVS_TO_SVN_REVNUMS)
    elif o == "-i":
      prime_ctx()
      show_cvsitemstore()
    elif o == "-I":
      prime_ctx()
      show_filtered_cvs_item_store()
    elif o == "-p":
      obj = pickle.load(open(a))
      print repr(obj)
      print obj
    else:
      usage()
      sys.exit(2)


if __name__ == '__main__':
  main()
