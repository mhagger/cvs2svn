This repository exhibits has interesting characteristic that the very
first thing that happen on a branch is that its sole file is deleted.
A bug in cvs2svn caused this to delay branch creation until the end of
the program (where we're finished off branches and tags), which
resulted in the file's deletion from the branch never really
happening.
