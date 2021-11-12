# REPORTING BUGS

:warning: cvs2svn is now in maintenance mode and is not actively being
developed. :warning:

This document tells how and where to report bugs in cvs2svn.  It is
not a list of all outstanding bugs -- we use an online issue tracker
for that, see

   https://github.com/mhagger/cvs2svn/issues

Before reporting a bug:

1. Verify that you are running the latest version of cvs2svn.

2. Read the current [frequently-asked-questions list](www/faq.html) to
   see if your problem has a known solution, and to help determine
   if your problem is caused by corruption in your CVS repository.

3. Check to see if your bug is already filed in the [issue
   tracker](https://github.com/mhagger/cvs2svn/issues).

If your problem seems to be new, [please create an
issue](https://github.com/mhagger/cvs2svn/issues/new).

To be useful, a bug report should include the following information:

* The revision of cvs2svn you ran.  Run `cvs2svn --version` to
  determine this.

* The version of Subversion you used it with.  Run `svnadmin
  --version` to determine this.

* The exact cvs2svn command line you invoked, and the output it
  produced.

* The contents of the configuration file that you used (if you used
  the `--config` option).

* The data you ran it on.  If your CVS repository is small (only a
  few kilobytes), then just provide the repository itself.  If it's
  large, or if the data is confidential, then please try to come up
  with some smaller, releasable data set that still stimulates the
  bug.  The cvs2svn project includes a script that can often help
  you narrow down the source of the bug to just a few `*,v` files,
  and another that helps strip proprietary information out of your
  repository.  See [the FAQ](www/faq.html) for more information.

The most important thing is that we be able to reproduce the bug :-).
If we can reproduce it, we can usually fix it.  If we can't reproduce
it, we'll probably never fix it.  So describing the bug conditions
accurately is crucial.  If in addition to that, you want to add some
speculations as to the cause of the bug, or even include a patch to
fix it, that's great!
