#!/usr/bin/env python

import anydbm
import marshal
import sys
import os
import getopt


def usage():
  cmd = sys.argv[0]
  sys.stderr.write('Usage: %s OPTION [DIRECTORY]\n\n' % os.path.basename(cmd))
  sys.stderr.write(
      'Show the contents of the temporary database files created by cvs2svn\n'
      'in a structured human-readable way.\n'
      '\n'
      'OPTION is one of:\n'
      '  -s      SymbolicNameTracker state database\n'
      '  -R      RepositoryMirror revisions table\n'
      '  -N      RepositoryMirror nodes table\n'
      '  -y      RepositoryMirror symroots table\n'
      '  -r rev  RepositoryMirror node tree for specific revision\n'
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


def main():
  try:
    opts, args = getopt.getopt(sys.argv[1:], "sRNyr:")
  except getopt.GetoptError:
    usage()

  if len(args) > 1 or len(opts) != 1:
    usage()

  if len(args) == 1:
    os.chdir(args[0])

  db = None

  for o, a in opts:
    if o == "-s":
      db = anydbm.open("cvs2svn-sym-names.db", 'r')
      print "SymbolicNameTracker state database"
      print_node_tree(db)
    elif o == "-R":
      db = anydbm.open("cvs2svn-svn-revisions.db", 'r')
      print "RepositoryMirror revisions table"
      k = map(lambda x: int(x), db.keys())
      k.sort()
      for i in k:
        print "%6d: %s" % (i, db[str(i)])
    elif o == "-N":
      db = anydbm.open("cvs2svn-svn-nodes.db", 'r')
      print "RepositoryMirror nodes table"
      k = db.keys()
      k.sort()
      for i in k:
        print "%6s: %s" % (i, marshal.loads(db[i]))
    elif o == "-y":
      db = anydbm.open("cvs2svn-svn-revisions.db", 'r')
      print "RepositoryMirror symroots table"
      k = [int(i) for i in db.keys()]
      k.sort()
      for i in k:
        print "%s: %s" % (i, db[str(i)])
    elif o == "-r":
      try:
        revnum = int(a)
      except ValueError:
        sys.stderr.write('Option -r requires a valid revision number\n')
        sys.exit(1)
      db = anydbm.open("cvs2svn-svn-revisions.db", 'r')
      key = db[str(revnum)]
      db.close()
      db = anydbm.open("cvs2svn-svn-nodes.db", 'r')
      print_node_tree(db, key, "Revision %d" % revnum)
    else:
      usage()
      sys.exit(2)

  db.close()


if __name__ == '__main__':
  main()

