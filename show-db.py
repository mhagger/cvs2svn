#!/usr/bin/env python

import anydbm
import marshal
import sys
import os
import getopt
import cPickle as pickle
from cStringIO import StringIO

from cvs2svn_lib import config
from cvs2svn_lib.context import Ctx


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
      '  -f      CVSFileDatabase\n'
      '  -c      PersistenceManager SVNCommit table\n'
      '  -C      PersistenceManager cvs-revs-to-svn-revnums table\n'
      '  -i      CVSItemDatabase (normal)\n'
      '  -I      CVSItemDatabase (resync)\n'
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


def show_resynccvsitemstore(fname):
  f = open(fname, 'rb')

  u = pickle.Unpickler(f)
  (pickler_memo, unpickler_memo,) = u.load()

  while True:
    u = pickle.Unpickler(f)
    u.memo = unpickler_memo.copy()
    try:
      item = u.load()
    except EOFError:
      break
    print    "%6s: %s" % (item.id, item,)



class ProjectList:
  """A mock project-list that can be assigned to Ctx().projects."""

  def __init__(self):
    self.projects = {}

  def __getitem__(self, i):
    return self.projects.setdefault(i, 'Project%d' % i)


def prime_ctx():
  from cvs2svn_lib.common import DB_OPEN_READ
  from cvs2svn_lib.symbol_database import SymbolDatabase
  from cvs2svn_lib.cvs_file_database import CVSFileDatabase
  from cvs2svn_lib.artifact_manager import artifact_manager
  artifact_manager.register_temp_file("cvs-files.pck", None)
  artifact_manager.register_temp_file("symbols.pck", None)
  artifact_manager.register_temp_file("cvs-files.db", None)
  from cvs2svn_lib.cvs_item_database import OldCVSItemStore
  from cvs2svn_lib.metadata_database import MetadataDatabase
  artifact_manager.register_temp_file("metadata.db", None)
  artifact_manager.pass_started(None)

  Ctx().projects = ProjectList()
  Ctx()._symbol_db = SymbolDatabase()
  Ctx()._cvs_file_db = CVSFileDatabase(DB_OPEN_READ)
  Ctx()._cvs_items_db = OldCVSItemStore(config.CVS_ITEMS_STORE)
  Ctx()._metadata_db = MetadataDatabase(DB_OPEN_READ)

def main():
  try:
    opts, args = getopt.getopt(sys.argv[1:], "RNr:mlfcCiIp:")
  except getopt.GetoptError:
    usage()

  if len(args) > 1 or len(opts) != 1:
    usage()

  if len(args) == 1:
    os.chdir(args[0])

  for o, a in opts:
    if o == "-R":
      show_int2str_db("svn-revisions.db")
    elif o == "-N":
      show_str2marshal_db("svn-nodes.db")
    elif o == "-r":
      try:
        revnum = int(a)
      except ValueError:
        sys.stderr.write('Option -r requires a valid revision number\n')
        sys.exit(1)
      db = anydbm.open("svn-revisions.db", 'r')
      key = db[str(revnum)]
      db.close()
      db = anydbm.open("svn-nodes.db", 'r')
      print_node_tree(db, key, "Revision %d" % revnum)
    elif o == "-m":
      show_str2marshal_db("metadata.db")
    elif o == "-f":
      show_str2pickle_db("cvs-files.db")
    elif o == "-c":
      prime_ctx()
      show_str2ppickle_db("svn-commits.db")
    elif o == "-C":
      show_str2marshal_db("cvs-revs-to-svn-revnums.db")
    elif o == "-i":
      prime_ctx()
      show_cvsitemstore()
    elif o == "-I":
      prime_ctx()
      show_resynccvsitemstore("cvs-items-resync.pck")
    elif o == "-p":
      obj = pickle.load(open(a))
      print repr(obj)
      print obj
    else:
      usage()
      sys.exit(2)


if __name__ == '__main__':
  main()
