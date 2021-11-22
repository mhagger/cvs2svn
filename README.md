# cvs2svn - CVS to Subversion Repository Converter

:warning: cvs2svn is now in maintenance mode and is not actively being
developed. :warning:

cvs2svn is a tool for migrating a CVS repository to Subversion, git,
or Bazaar. The main design goals are robustness and 100% data
preservation. cvs2svn can convert just about any CVS repository we've
ever seen. For example, it has been used to convert gcc, FreeBSD, KDE,
GNOME, PostgreSQL…

cvs2svn infers what happened in the history of your CVS repository and
replicates that history as accurately as possible in the target SCM.
All revisions, branches, tags, log messages, author names, and commit
dates are converted. cvs2svn deduces what CVS modifications were made
at the same time, and outputs these modifications grouped together as
changesets in the target SCM. cvs2svn also deals with many CVS quirks
and is highly configurable. See the comprehensive [feature
list](features.md).

You can get the latest releases [from the GitHub releases
page](https://github.com/mhagger/cvs2svn/releases). Please read [the
documentation](cvs2svn.md) and [the FAQ](faq.md) carefully before
using cvs2svn.

For general use, the most recent released version of cvs2svn is
usually the best choice. However, if you want to use the newest
cvs2svn features or if you're debugging or patching cvs2svn, you might
want to use the master version (which is usually quite stable). To do
so, use Git to clone the repository, and run it straight from the
working copy.

This repository contains a `Dockerfile` that can be used to create a
docker image in which cvs2svn can be run. (It has some dependencies
that are no longer easily installable, so this is probably the easiest
way to run cvs2svn.)
