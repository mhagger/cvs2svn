# Hacker's Guide To cvs2svn

This project tends to use the same social and technical guidelines
(where applicable) as Subversion itself. You can view them online
[here](http://subversion.apache.org/docs/community-guide/conventions.html).

* The source code is accessible from two places:

  * The primary repository for cvs2svn during most of its life was in
    Subversion under the following URL:

      http://cvs2svn.tigris.org/svn/cvs2svn

    But tigris.org no longer exists.

  * A copy of the project is now available on GitHub:

      https://github.com/mhagger/cvs2svn

    Feel free to use the issue tracker or pull request there, but
    please be aware that cvs2svn is in maintenance mode and not
    currently under development.

* Read the files under `doc/`, especially:

  * `doc/design-notes.txt` gives a high-level description of the
    algorithm used by cvs2svn to make sense of the CVS history.

  * `doc/symbol-notes.txt` describes how CVS symbols are handled.

  * `doc/making-releases.txt` describes the (obsolete!) procedure for
    making a new release of cvs2svn.

* Read the files under `www/`, especially:

  * `www/features.html` describes abstractly many of the CVS
    peculiarities that cvs2svn attempts to deal with.

* Read the class and method docstrings.

* Adhere to the code formatting conventions of the rest of the
  project (e.g., limit line length to 79 characters).

* We no longer require the exhaustive commit messages required by the
  Subversion project. But please include commit messages that:

  * Describe the *reason* for the change.

  * Attribute changes to their original author using lines like

    Patch by: Joe Schmo <schmo@example.com>

* Please put a new test in `run-tests.py` when you fix a bug.


Happy hacking!
