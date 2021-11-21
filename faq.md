# cvs2svn FAQ

:warning: cvs2svn is now in maintenance mode and is not actively being
developed. :warning:

## General

### Does cvs2svn support incremental repository conversion?

No.

Explanation: During the transition from CVS to Subversion, it would
sometimes be useful to have the new Subversion repository track
activity in the CVS repository for a period of time until the final
switchover. This would require each conversion to determine what had
changed in CVS since the last conversion, and add those commits on top
of the Subversion repository.

Unfortunately, cvs2svn/cvs2git does _not_ support incremental
conversions. With some work it would be possible to add this feature,
but it would be difficult to make it robust. The trickiest problem is
that CVS allows changes to the repository that have retroactive
effects (e.g., affecting parts of the history that have already been
converted).

Some conversion tools claim to support incremental conversions from
CVS, but as far as is known none of them are reliable.


## Compatibility

### Does cvs2svn run under Psyco?

No.

Explanation: [Psyco](http://psyco.sourceforge.net/) is a python
extension that can speed up the execution of Python code by compiling
parts of it into i386 machine code. Unfortunately, Psyco is known
_not_ to run cvs2svn correctly (this was last tested with the Psyco
pre-2.0 development branch). When cvs2svn is run under Psyco it
crashes in `OutputPass` with an error message that looks something
like this:

```
cvs2svn_lib.common.InternalError: ID changed from 2 -> 3 for Trunk, r2
```

The Psyco team has been informed about the problem.


## How-to

### How can I convert a CVS repository to which I only have remote
access?

cvs2svn requires direct, filesystem access to a copy of the CVS
repository that you want to convert. The reason for this requirement
is that cvs2svn directly parses the `*,v` files that make up the CVS
repository.

Many remote hosting sites provide access to backups of your CVS
repository, which could be used for a cvs2svn conversion. For example:

* [SourceForge](http://sourceforge.net) allows CVS content to be
  accessed via [rsync](http://sourceforge.net/docs/E04/en/#rsync). In
  fact, they provide [complete
  instructions](http://sourceforge.net/apps/trac/sourceforge/wiki/SVN%20adminrepo#Usingcvs2svntocreateaSVNdumpfilefromCVScontent)
  for migrating a SourceForge project from CVS to SVN.

* ..._(other examples welcome)_

If your provider does not provide any way to download your CVS
repository, there are two known tools that claim to be able to clone a
CVS repository via the CVS protocol:

* [cvsclone](http://samba.org/ftp/tridge/rtc/cvsclone.l)

* [CVSsuck](http://cvs.m17n.org/~akr/cvssuck/)


It should be possible to use one of these tools to fetch a copy of
your CVS repository from your provider, then to use cvs2svn to convert
the copy. However, the developers of cvs2svn do not have any
experience with these tools, so you are on your own here. If you try
one of them, please tell us about your experience.


### How can I convert part of a CVS repository?

This is easy: simply run cvs2svn normally, passing it the path of the
project subdirectory within the CVS repository. Since cvs2svn ignores
any files outside of the path it is given, other projects within the
CVS repository will be excluded from the conversion.

Example: You have a CVS repository at path `/path/cvsrepo` with
projects in subdirectories `/path/cvsrepo/foo` and
`/path/cvsrepo/bar`, and you want to create a new Subversion
repository at `/path/foo-svn` that includes only the `foo` project:


```
    $ cvs2svn -s /path/foo-svn /path/cvsrepo/foo
```


### How can I convert separate projects in my CVS repository into a
single Subversion repository?

This question assumes that you will convert all of your projects at
the same time. If you must convert your projects at different times,
please see "What if I don't want to convert all of my projects at
once?"

cvs2svn supports multiproject conversions, but you have to use the
options file method to start the conversion. In your options file, you
simply call `run_options.add_project()` once for each sub-project in
your repository. For example, if your CVS repository has the layout:

    /project-a
    /project-b

and you want your Subversion repository to be laid out like this:

    project-a/
       trunk/
          ...
       branches/
          ...
       tags/
          ...
    project-b/
       trunk/
          ...
       branches/
          ...
       tags/
          ...

then you need to have a section like this in your options file:

```
run_options.add_project(
    'my/cvsrepo/project-a',
    trunk_path='project-a/trunk',
    branches_path='project-a/branches',
    tags_path='project-a/tags',
    symbol_transforms=[
        #...whatever...
        ],
    symbol_strategy_rules=[
        #...whatever...
        ],
    )
run_options.add_project(
    'my/cvsrepo/project-b',
    trunk_path='project-b/trunk',
    branches_path='project-b/branches',
    tags_path='project-b/tags',
    symbol_transforms=[
        #...whatever...
        ],
    symbol_strategy_rules=[
        #...whatever...
        ],
    )
```


### I have hundreds of subprojects to convert and my options file is getting huge

The options file is Python code, executed by the Python interpreter.
This makes it easy to automate parts of the configuration process. For
example, to add many subprojects, you can write a Python loop:

```
projects = ['A', 'B', 'C', ...etc...]

cvs_repo_main_dir = r'test-data/main-cvsrepos'
for project in projects:
    run_options.add_project(
        cvs_repo_main_dir + '/' + project,
        trunk_path=(project + '/trunk'),
        branches_path=(project + '/branches'),
        tags_path=(project + '/tags'),
        # ...
        )
```

or you could even read the subprojects directly from the CVS
repository:

```
import os
cvs_repo_main_dir = r'test-data/main-cvsrepos'
projects = os.listdir(cvs_repo_main_dir)

# Probably you don't want to convert CVSROOT:
projects.remove('CVSROOT')

for project in projects:
    # ...as above...
```


### How can I define my own class and use it in my options file?

It is possible to customize your conversion using arbitrary Python
code. Sometimes this requires you to define your own Python class. For
technical reasons, such classes should not be defined within the
options file but rather in a separate file that is imported into the
options file.

[Technical explanation: The problem is that class instances used in
`run_options` are pickled in pass1 then unpickled in later passes.
(Pickling is a Python mechanism for storing objects to a file.) But
class instances can only be unpickled if the class can be imported at
the time of unpickling. This, in turns, requires the class to be
defined at the top level of a Python module. The options file is _not_
a valid Python module; among other things, it is loaded using
execfile(), not by being imported.]

So create a separate file with a `*.py` filename, like
`myoptionsclasses.py`. In that file, do any imports needed by your
code, then define your class:

```
from cvs2svn_lib.symbol_transform import SymbolTransform

class MySymbolTransform(SymbolTransform):
    def transform(self, cvs_file, symbol_name, revision):
        [...]
```

Then, in your main options file, import the class and use it:

```
from myoptionsclasses import MySymbolTransform

run_options.add_project(
    [...]
    symbol_transforms=[
        MySymbolTransform(),
        ...
        ])
```


### How can I convert project `foo` so that `trunk/tags/branches` are
inside of `foo`?

If `foo` is the only project that you want to convert, then either run
cvs2svn like this:

    $ cvs2svn --trunk=foo/trunk --branches=foo/branches --tags=foo/tags CVSREPO/foo

or use an options file that defines a project like this:

```
run_options.add_project(
    'my/cvsrepo/foo',
    trunk_path='foo/trunk',
    branches_path='foo/branches',
    tags_path='foo/tags',
    symbol_transforms=[
        #...whatever...
        ],
    symbol_strategy_rules=[
        #...whatever...
        ],
    )
```

If `foo` is not the only project that you want to convert, then you
need to do a multiproject conversion; see "How can I convert separate
projects in my CVS repository into a single Subversion repository?"
for more information.


### What if I don't want to convert all of my projects at once?

Suppose you need to convert some CVS projects to Subversion _now_ and
other projects _later_. This situation is typically encountered in
large organizations where each project has a separate lifecycle and
schedule, and a one-step conversion process is not practical.

First you have to decide whether you want to put your converted
projects into a single Subversion repository or multiple repositories.
This is mostly an administrative decision and is beyond the scope of
this FAQ. See [the Subversion
book](http://svnbook.red-bean.com/en/1.2/svn.reposadmin.projects.html#svn.reposadmin.projects.chooselayout)
for a discussion of repository organization.

If you decide to convert your projects into separate Subversion
repositories, then please follow the instructions in "How can I
convert part of a CVS repository?", once for each repository.

If, on the other hand, you want to convert the CVS projects at
different times but put them into a single Subversion repository, then
you need to follow the instructions in this section.

**NOTE:** importing projects one at a time into a single Subversion
repository will usually break date-based range commands (e.g. `svn
diff -r {2002-02-17:2002-03-18}`) for the overlapping dates. This is
because Subversion uses a bisect-based search to locate commits from a
given date, and this algorithm fails for non-monotonic dates. While
this is not the end of the world, it can be an inconvenience.

Remember that a multiproject Subversion repository should usually be
laid out like this:

    project-a/
       trunk/
          ...
       branches/
          ...
       tags/
          ...
    project-b/
       trunk/
          ...
       branches/
          ...
       tags/
          ...

Note that each project has its own top-level directory that contains
`trunk`, `branches`, and `tags` subdirectories. The procedure is to
convert each project separately to a dumpfile with the following
directory structure:

    project-a/
       trunk/
          ...
       branches/
          ...
       tags/
          ...

and then to load the dumpfile into the Subversion repository using
`svnadmin load`.

Example:

1. If the svn repository doesn't already exist, create it:
    ```
    svnadmin create /path/to/svnrepos
    ```

2. Remember to **make a backup** before starting. Never run cvs2svn on
    a live CVS repository—always work on a copy of your repository.

3. Run cvs2svn against one of the projects that you want converted:

    ```
    # Create a dumpfile containing the new CVS repository contents
    $ cvs2svn --dumpfile=/tmp/project-a.dump \
              --trunk=project-a/trunk \
              --branches=project-a/branches \
              --tags=project-a/tags \
              /path/to/cvsrepo/project-a
    ```

4. Use `svnadmin load` to import the dump into the Subversion
    repository:

    ```
    $ cd ~/svndump
    $ svnadmin load /path/to/svnrepos &lt;/tmp/project-a.dump
    ```

5. Repeat steps 3 and 4 for each module you want to convert.

Variations:

* It is possible to convert more than one CVS repository per batch; to
  do so, see "How can I convert separate projects in my CVS repository
  into a single Subversion repository?", remembering to have cvs2svn
  write its output to a dumpfile each time.

* For more complicated directory arrangements, it might be necessary
  to use `svnadmin load`'s `--parent-dir` option to place directories
  in their final location. For example, suppose you want the following
  layout in Subversion:

    ```
    server/
        project-a/
        project-b/
    client/
        project-c/
        project-d/
    ```

    but you want to convert `project-a` and `project-b` at different
    times. The above recipe will not work, because `svnadmin load`
    would give an error when `project-b` tries to create directory
    `server/`, because the directory already exists from when
    `project-a` was loaded. The solution is to convert `project-b` as
    a top-level project:
    ```
    $ cvs2svn --dumpfile=/tmp/project-b.dump \
              /path/to/cvsrepo/project-b
    ```
    but then load it using the `--parent-dir` option:
    ```
    $ svnadmin load --parent-dir=project-b /path/to/svnrepos &lt;/tmp/project-b.dump
    ```


### How do I fix up end-of-line translation problems?

Warning: cvs2svn's handling of end-of-line options changed between
version 1.5.x and version 2.0.x. **This documentation applies to
version 2.0.x and later.** The documentation applying to an earlier
version can be found in the `www` directory of that release of
cvs2svn.

Starting with version 2.0, the default behavior of cvs2svn is to treat
all files as binary except those explicitly determined to be text.
(Previous versions treated files as text unless they were determined
to be binary.) This behavior was changed because, generally speaking,
it is safer to treat a text file as binary than vice versa.

However, it is often preferred to set `svn:eol-style=native` for text
files, so that their end-of-file format is converted to that of the
client platform when the file is checked out. This section describes
how to get the settings that you want.

If a file is marked as binary in CVS (with `cvs admin -kb`, then
cvs2svn will always treat the file as binary. For other files, cvs2svn
has a number of options that can help choose the correct end-of-line
translation parameters during the conversion:

* `--auto-props=FILE` — Set arbitrary Subversion properties on files
    based on the `auto-props` section of a file in svn config format.
    The `auto-props` file might have content like this:

        [auto-props]
        *.txt = svn:mime-type=text/plain;svn:eol-style=native
        *.doc = svn:mime-type=application/msword;!svn:eol-style

    This option can also be used in combination with
    `--eol-from-mime-type`.

    To force end-of-line translation off, use a setting of the form
    `!svn:eol-style` (with a leading exclamation point).

* `--mime-types=FILE` — Specifies an Apache-style `mime.types` file
    for setting files' `svn:mime-type` property based on the file
    extension. The mime-types file might have content like this:

        text/plain              txt
        application/msword      doc

    This option only has an effect on `svn:eol-style` if it is used in
    combination with `--eol-from-mime-type`.

* `--eol-from-mime-type` — Set `svn:eol-style` based on the file's
    mime type (if known). If the mime type starts with `text/`, then
    the file is treated as a text file; otherwise, it is treated as
    binary. This option is useful in combination with `--auto-props`
    or `--mime-types`.

* `--default-eol=STYLE` — Usually cvs2svn treats a file as binary
    unless one of the other rules determines that it is not binary and
    it is not marked as binary in CVS. But if this option is
    specified, then cvs2svn uses the specified style as the default.
    `STYLE` can be `binary` (default), `native`, `CRLF`, `LF`, or
    `CR`. If you have been diligent about annotating binary files in
    CVS, or if you are confident that the above options will catch all
    of your binary files, then `--default-style=native` should give
    good results.

If you don't use any of these options, then cvs2svn will not arrange
any line-end translation whatsoever. The file contents in the SVN
repository should be the same as the contents you would get if
checking out with CVS on the machine on which cvs2svn is run. This
also means that the EOL characters of text files will be the same no
matter where the SVN data are checked out (i.e., not translated to the
checkout machine's EOL format).

To do a better job, you can use `--auto-props`, `--mime-types`, and
`--eol-from-mime-type` to specify exactly which properties to set on
each file based on its filename.

For total control over setting properties on files, you can use the
`--options`-file method and write your own `FilePropertySetter` or
`RevisionPropertySetter` in Python. For example,

```
from cvs2svn_lib.property_setters import FilePropertySetter

class MyPropertySetter(FilePropertySetter):
  def set_properties(self, cvs_file):
    if cvs_file.cvs_path.startswith('path/to/funny/files/'):
      cvs_file.properties['svn:mime-type'] = 'text/plain'
      cvs_file.properties['svn:eol-style'] = 'CRLF'

ctx.file_property_setters.append(MyPropertySetter())
```

Please note that the class must be defined in a separate file.

See the file `cvs2svn_lib/property_setters.py` for many examples of
property setters.


### I want a single project but tag-rewriting rules that vary by subdirectory. Can this be done?

This is an example of how the cvs2svn conversion can be customized
using Python.

Suppose you want to write symbol transform rules that are more
complicated than "replace `REGEXP` with `PATTERN`". This can easily be
done by writing just a little bit of Python code.

When a symbol is encountered, cvs2svn iterates through the list of
`SymbolTransform` objects defined for the project. For each one, it
calls `symbol_transform.transform(cvs_file, symbol_name, revision)`.
That method can return any legal symbol name, which will be used in
the conversion instead of the original name.

To use this feature, you will have to use an `--options` file to start
the conversion. You then write a new `SymbolTransform` class that
inherits from `RegexpSymbolTransform` but checks the path before
deciding whether to transform the symbol. You can do something like
the following:

```
from cvs2svn_lib.symbol_transform import RegexpSymbolTransform

class MySymbolTransform(RegexpSymbolTransform):
    def __init__(self, path, pattern, replacement):
        """Transform only symbols that occur within the specified PATH."""

        self.path = path
        RegexpSymbolTransform.__init__(self, pattern, replacement)

    def transform(self, cvs_file, symbol_name, revision):
        # Is the file is within the path we are interested in?
        if cvs_file.cvs_path.startswith(path + '/'):
            # Yes -> Allow RegexpSymbolTransform to transform the symbol:
            return RegexpSymbolTransform.transform(
                    self, cvs_file, symbol_name, revision)
        else:
            # No -> Return the symbol unchanged:
            return symbol_name

# Note that we use a Python loop to fill the list of symbol_transforms:
symbol_transforms = []
for subdir in ['project1', 'project2', 'project3']:
    symbol_transforms.append(
        MySymbolTransform(
            subdir,
            r'release-(\d+)_(\d+)',
            r'%s-release-\1.\2' % subdir))

# Now register the project, using our own symbol transforms:
run_options.add_project(
    'your_cvs_path',
    trunk_path='trunk',
    branches_path='branches',
    tags_path='tags',
    symbol_transforms=symbol_transforms))
```

Please note that the class must be defined in a separate file.

This example causes any symbol under `project1` that looks like
`release-3_12` to be transformed into a symbol named
`project1-release-3.12`, whereas if the same symbol appears under
`project2` it will be transformed into `project2-release-3.12`.


### How can I convert a CVSNT repository?

CVSNT is a version control system that started out by adding support
for running CVS under Windows NT. Since then it has made numerous
extensions to the RCS file format, to the point where CVS
compatibility does not imply CVSNT compatibility with any degree of
certainty.

cvs2svn _might_ happen to successfully convert a CVSNT repository,
especially if the repository has never had any CVSNT-only features
used on it, but **this use is not supported and should not be expected
to work**.

If you want to experiment with converting a CVSNT repository, then
please consider the following suggestions:

* Use cvs2svn's `--use-cvs` option.

* Use CVSNT's version of the `cvs` executable (i.e., ensure that the
  first `cvs` program in your `$PATH` is the one that came with
  CVSNT).

* Carefully check the result of the conversion before you rely on it,
  _even if the conversion completed without any errors or warnings_.

Patches to support the conversion of CVSNT repositories would be
welcome.


### How do I get cvs2svn to run on OS X 10.5.5?

Attempting to run cvs2svn on a standard OS X 10.5.5 installation
yields the following error:

> ERROR: cvs2svn uses the anydbm package, which depends on lower level
> dbm libraries. Your system has dbm, with which cvs2svn is known to
> have problems. To use cvs2svn, you must install a Python dbm library
> other than dumbdbm or dbm. See
> http://python.org/doc/current/lib/module-anydbm.html for more
> information.

The problem is that the standard distribution of python on OS X 10.5.5
does not include any other dbm libraries other than the standard dbm.
In order for cvs2svn to work, we need to install the gdbm library, in
addition to a new version of python that enables the python gdbm
module.

The precompiled versions of python for OS X available from python.org
or activestate.com (currently version 2.6.2) do not have gdbm support
turned on. To check for gdbm support, check for the library module
(`libgdmmodule.so`) within the python installation.

Here is the procedure for a successful installation of cvs2svn and all
supporting libs:

1. Download the gdbm-1.8.3 (or greater) source, unarchive and change
   directory to gdbm-1.8.3. We need to install the gdbm libraries so
   python's gdbm module can use them.

   1. Type `./configure`

   2. Edit `Makefile` so that the owner and group are not the
      non-existing "bin" owner and group by changing

        ```
        BINOWN = bin
        BINGRP = bin
        ```

      to

        ```
        BINOWN = root
        BINGRP = admin
        ```

    3. Type `make`

    4. Type `sudo make install`

2. Download the Python2.6 (or greater) source, unarchive, and change
   directory to Python2.6. We need to enable python gdbm support which
   is not enabled in the default OS X 10.5.5 installation of python,
   as the gdbm libs are not included. However, we just installed the
   gdbm libs in step 1, so we can now compile python with gdbm
   support.

    1. Edit the file `Modules/Setup` by uncommenting the line which
       links against gdbm by changing

        ```
        #gdbm gdbmmodule.c -I/usr/local/include -L/usr/local/lib -lgdbm
        ```

        to

        ```
        gdbm gdbmmodule.c -I/usr/local/include -L/usr/local/lib -lgdbm
        ```

    2. Edit the file `Modules/Setup` by uncommenting the line to
       create shared libs by changing

        ```
        #*shared*
        ```

        to

        ```
        *shared*
        ```

    3. Type `./configure --enable-framework --enable-universalsdk` in
       the top-level Python2.6 directory. This will configure the
       installation of python as a shared OS X framework, and usable
       with OS X GUI frameworks and SDKs. You may have problems
       building if you don't have the SDKs that support the PPC
       platform. If you do, just specify `--disable-universalsdk`. By
       default, python will be installed in
       `/Library/Frameworks/Python.framework`, which is what we
       want.

    4. Type `make`

    5. Type `sudo make install`

    6. Type `cd /usr/local/bin; sudo ln -s python2.6 python`

    7. Make sure `/usr/local/bin` is at the front of your search path
       in `~/.profile` or `~/.bashrc` etc.

    8. Type `source ~/.profle` or `source ~/.bashrc` etc. or
       alternatively, just open a new shell window. When you type
       `which python` it should give you the new version in
       `/usr/local/bin` **not** the one in `/usr/bin`.

3. Download the cvs2svn-2.2.0 (or greater) source, unarchive and
   change directory to cvs2svn-2.2.0. Many people can't get cvs2svn to
   work except in the installation directory. The reason for this is
   that the installation places copies of `cvs2svn`, `cvs2svn_libs`,
   and `cvs2svn_rcsparse` in the
   `/Library/Frameworks/Python.framework` hierarchy. All we need to do
   is make a link in `/usr/local/bin` pointing to the location of
   cvs2svn in the python framework hierarchy. And for good measure we
   also make links to the lib and include directories:

    1. Type `sudo make install`

    2. Create the required links by typing the following:

        ```
        sudo ln -s /Library/Frameworks/Python.framework/Versions/2.6/bin/cvs2svn /usr/local/bin/cvs2svn
        sudo ln -s /Library/Frameworks/Python.framework/Versions/2.6/lib/python2.6 /usr/local/lib/python2.6
        sudo ln -s /Library/Frameworks/Python.framework/Versions/2.6/include/python2.6 /usr/local/include/python2.6
        ```

The installation is complete. Change directory out of the
cvs2svn-2.2.0 installation directory, and you should be able to run
cvs2svn. Be careful *not* to copy the version of `cvs2svn` in the
cvs2svn-2.2.0 installation directory to `/usr/local/bin`, as this has
a different python environment setting at the top of the file than the
one that was installed in the `/Library/Frameworks/Python.framework`
hierarchy. Follow the instructions exactly, and it should work.


## Problems

### I get an error "A CVS repository cannot contain both repo/path/file.txt,v and repo/path/Attic/file.txt,v". What can I do?

Background: Normally, if you have a file called `path/file.txt` in
your project, CVS stores its history in a file called
`repo/path/file.txt,v`. But if `file.txt` is deleted on the main line
of development, CVS moves its history file to a special `Attic`
subdirectory: `repo/path/Attic/file.txt,v`. (If the file is recreated,
then it is moved back out of the `Attic` subdirectory.) Your
repository should never contain both of these files at the same time.

This cvs2svn error message thus indicates a mild form of corruption in
your CVS repository. The file has two conflicting histories, and even
CVS does not know the correct history of `path/file.txt`. The
corruption was probably created by using tools other than CVS to
backup or manipulate the files in your repository. With a little work
you can learn more about the two histories by viewing each of the
`file.txt,v` files in a text editor.

There are four straightforward approaches to fixing the repository
corruption, but each has potential disadvantages. Remember to **make a
backup** before starting. Never run cvs2svn on a live CVS
repository—always work on a copy of your repository.

1. Restart the conversion with the `--retain-conflicting-attic-files`
   option. This causes the non-attic and attic versions of the file to
   be converted separately, with the `Attic` version stored to a new
   subdirectory as `path/Attic/file.txt`. This approach avoids losing
   any history, but by moving the `Attic` version of the file to a
   different subdirectory it might cause historical revisions to be
   broken.

2. Remove the `Attic` version of the file and restart the conversion.
   Sometimes it represents an old version of the file that was deleted
   long ago, and it won't be missed. But this completely discards one
   of the file's histories, probably causing `file.txt` to be missing
   in older historical revisions. (For what it's worth, this is
   probably how CVS would behave in this situation.)

    ```
    # You did make a backup, right?
    $ rm repo/path/Attic/file.txt,v
    ```

3. Remove the non-`Attic` version of the file and restart the
   conversion. This might be appropriate if the non-`Attic` version
   has less important content than the `Attic` version. But this
   completely discards one of the file's histories, probably causing
   `file.txt` to be missing in recent historical revisions.

    ```
    # You did make a backup, right?
    $ rm repo/path/file.txt,v
    ```

4. Rename the non-`Attic` version of the file and restart the
   conversion. This avoids losing history, but it changes the name of
   the non-`Attic` version of the file to `file-not-from-Attic.txt`
   whenever it appeared, and might thereby cause revisions to be
   broken.

    ```
    # You did make a backup, right?
    $ mv repo/path/file.txt,v repo/path/file-not-from-Attic.txt,v
    ```

If you run cvs2svn on a case-insensitive operating system, it is
possible to get this error even if the filename of the file in `Attic`
has different case than the one out of the `Attic`. This could happen,
for example, if the CVS repository was served from a case-sensitive
operating system at some time. A workaround for this problem is to
copy the CVS repository to a case-sensitive operating system and
convert it there.


### I get an error "ERROR: `FILENAME,v` is not a valid `,v` file."

The named file is corrupt in some way. (Corruption is surprisingly
common in CVS repositories.) It is likely that even CVS has problems
with this file; try checking out the head revision, revision 1.1, and
the tip revision on each branch of this file; probably one or more of
them don't work.

Here are some options:

1. Omit this file from the conversion (by making a copy of your
   repository, deleting this file from the copy, then converting from
   the copy).

2. Restore an older copy of this file from backups, if you have
   backups from before it was corrupted.

3. Hand-fix the file as best you can by opening it in a binary editor
   and trying to put it back in RCS file format (documented in the
   `rcsfile(5)` manpage). Often it is older revisions that are
   affected by corruption; you might need to delete some old revisions
   to salvage newer ones.


### gdbm.error: (45, 'Operation not supported')

This has been reported to be caused by trying to create gdbm databases
on an NFS partition. Apparently gdbm does not support databases on NFS
partitions. The workaround is to use the `--tmpdir` option to choose a
local partition for cvs2svn to write its temporary files.


### When converting a CVS repository that was used on a Macintosh, the contents of some files are incorrect in SVN.

Some Macintosh CVS clients use a nonstandard trick to store the
resource fork of files in CVS: instead of storing the file contents
directly, store an [AppleSingle](http://rfc.net/rfc1740.html) data
stream containing both the data fork and resource fork. When checking
the file out, the client unpacks the AppleSingle data and writes the
two forks separately to disk. By default, cvs2svn treats the file
contents literally, so when you check the file out of Subversion, the
file contains the combined data in AppleSingle format rather than only
the data fork of the file as expected.

Subversion does not have any special facilities for dealing with
Macintosh resource forks, so there is nothing cvs2svn can do to
preserve both forks of your data. However, sometimes the resource fork
is not needed. If you would like to discard the resource fork and only
record the data fork in Subversion, then start your conversion using
the `--options` file method and set the following option to `True` in
your options file:

    ctx.decode_apple_single = True

There is more information about this option in the comments in
`cvs2svn-example.options`.


### Using cvs2svn 1.3.x, I get an error "The command '['co', '-q', '-x,v', '-p1.1', '-kk', '/home/cvsroot/myfile,v']' failed" in pass 8.

_What are you using cvs2svn version 1.3.x for anyway? Upgrade!_

But if you must, either install RCS, or ensure that CVS is installed
and use cvs2svn's `--use-cvs` option.


### Vendor branches created with "cvs import -b &lt;branch number&gt;" are not correctly handled.

Normally, people using `cvs import` don't specify the `-b` flag.
cvs2svn handles this normal case fine.

If you have a file which has an _active_ vendor branch, i.e. there
have never been any trunk commits but only "cvs imports" onto the
vendor branch, then cvs2svn will handle this fine. (Even if you've
used the `-b` option to specify a non-standard branch number).

If you've used `cvs import -b BRANCH_NUMBER`, you didn't specify the
standard CVS vendor branch number of 1.1.1, and there has since been a
commit on trunk (either a modification or delete), then your history
has been damaged. This isn't cvs2svn's fault. CVS simply doesn't
record the branch number of the old vendor branch, it assumes it was
1.1.1. You will even get the wrong results from `cvs checkout -D` with
a date when the vendor branch was active.

Symptoms of this problem can include:

* cvs2svn refusing to let you exclude the vendor branch, because some
  other branch depends on it

* if you did more than one import onto the vendor branch, then your
  SVN history "missing" one of the changes on trunk (though the change
  will be on the vendor branch).

(Note: There are other possible causes for these symptoms; don't
assume you have a non-standard vendor branch number just because you
see these symptoms).

The way to solve this problem is to renumber the vendor branch to the
standard 1.1.1 branch number. This has to be done before you run
cvs2svn. To help you do this, there is the `renumber_branch.py` script
in the `contrib` directory of the cvs2svn distribution.

The typical usage, assuming you used `cvs import -b 1.1.2 ...`
to create your vendor branch, is:

    contrib/renumber_branch.py 1.1.2 1.1.1 repos/dir/file,v

You should only run this on a **copy** of your CVS repository, as it
edits the repository in-place. You can fix a single file or a whole
directory tree at a time.

The script will check that the 1.1.1 branch doesn't already exist; if
it does exist then it will fail with an error message.


## Getting help

### How do I get help?

There are several sources of help for cvs2svn:

* The [user manual](cvs2svn.md) not only describes how to run cvs2svn,
  but also discusses some limitations, pitfalls, and conversion
  strategies. Please remember that the online manual describes the
  latest `master` version of the software, which may be different than
  the version that you are using.

* The frequently asked questions (FAQ) list is the document that you
  are now reading. Please make sure you've scanned through the list of
  topics to see if your question is already answered.

* ~~The [mailing list
  archives](http://cvs2svn.tigris.org/servlets/ProjectMailingListList).
  Maybe your question has already been discussed on either the
  `user@cvs2svn.tigris.org` or `dev@cvs2svn.tigris.org` mailing
  list.~~ _Unfortunately, the mailing list archive doesn't seem to be
  available anymore._

* [cvs2svn issues](https://github.com/mhagger/cvs2svn/issues) Be sure
  to include the information listed in "What information should I
  include when requesting help?"

* If you think you have found a bug, please refer to "How do I report
  a bug?"


### What information should I include when requesting help?

If you create an issue, it is important that you include the following
information. Failure to include important information is the best way
to dissuade the volunteers of the cvs2svn project from trying to help
you.

1. _Exactly what version_ of cvs2svn are you using? If you are not
   using an official release, please tell us the branch and commit
   from the Git repository that you are using. If you have modified
   cvs2svn, please tell us exactly what you have changed.

2. What platform are you using (Linux, BSD, Windows, etc.)? What
   python version (e.g., type `python --version`)?

3. What is the _exact command line_ that you used to start the
   conversion? If you used the `--options` option, please attach a
   copy of the options file that you used.

4. What happened when you ran the program? How did that differ from
   what you wanted/expected? Include transcripts and/or error output
   if available.

5. If you think you have found a bug, try to submit a repository that
   we can use to reproduce the problem. See "How can I produce a
   useful test case?" for more information. In most cases, if we
   cannot reproduce the problem, there is nothing we can do to help
   you.


### How do I report a bug?

cvs2svn is an open source project that is largely developed and
supported by volunteers in their free time. Therefore please try to
help out by reporting bugs in a way that will enable us to help you
efficiently.

The first question is whether the problem you are experiencing is
caused by a cvs2svn bug at all. A large fraction of reported "bugs"
are caused by problems with the user's CVS repository, especially mild
forms of repository corruption or trying to convert a CVSNT repository
with cvs2svn. Please also double-check the [manual](cvs2svn.html) to
be sure that you are using the command-line options correctly.

A good way to localize potential repository corruption is to use the
`shrink_test_case.py` script (which is located in the `contrib`
directory of the cvs2svn source tree). This script tries to find the
minimum subset of files in your repository that still shows the same
problem. **Warning: Only apply this script to a backup copy of your
repository, as it destroys the repository that it operates on!** Often
this script can narrow the problem down to a single file which, as
often as not, is corrupt in some way. Even if the problem is not in
your repository, the shrunk-down test case will be useful for
reporting the bug. Please see "How can I produce a useful test case?"
and the comments at the top of `shrink_test_case.py` for information
about how to use this script.

Assuming that you still think you have found a bug, the next step is
to investigate whether the bug is already known. Please look through
the [issue tracker](https://github.com/mhagger/cvs2svn/issues) for
bugs that sound familiar. If the bug is already known, then there is
no need to report it (though possibly you could contribute a useful
test case or a workaround).

If your bug seems new, then the best thing to do is report it as [an
issue](https://github.com/mhagger/cvs2svn/issues/new). Be sure to
include the information listed in "What information should I include
when requesting help?"


### How can I produce a useful test case?

If you need to report a bug, it is extremely helpful if you can
include a test repository with your bug report. In most cases, if we
cannot reproduce the problem, there is nothing we can do to help you.
This section describes ways to overcome the most common problems that
people have in producing a useful test case. When you have a
reasonable-sized test case (say under 1 MB—the smaller the better),
you can just tar it up and attach it to the issue in which you report
the bug.

#### If the repository is too big and/or contains proprietary information

You don't want to send us your proprietary information, and we don't
want to receive it either. Short of open-sourcing your software, here
is a way to strip out most of the proprietary information and
simultaneously reduce the size of the archive tremendously.

The `destroy_repository.py` script tries to delete as much
information as possible out of your repository while still preserving
its basic structure (and therefore hopefully any cvs2svn bugs).
Specifically, it tries to delete file descriptions, text content, all
nontrivial log messages, and all author names.  It also renames all
files and directories to have generic names (e.g.,
`dir015/file053,v`).  (It does not affect the number and dates
of revisions to the files.)

1. This procedure will **destroy the repository** that it is applied
   to, so be sure to **make a backup copy of your repository and work
   with the backup!**

2. Make sure you have the `destroy_repository.py` script. If you don't
   already have it, you should [download the source
   code](https://github.com/mhagger/cvs2svn) for cvs2svn (there is no
   need to install it). The script is located in the `contrib`
   subdirectory.

3. Run `destroy_repository.py` by typing

    ```
    # You did make a backup, right?
    /path/to/config/destroy_repository.py /path/to/copy/of/repo
    ```

4. Try converting the "destroyed" repository using cvs2svn, and ensure
   that the bug still exists.

5. Verify that the "destroyed" archive does not include any
   information that you consider proprietary. Your data security is
   ultimately your responsibility, and we make no guarantees that the
   `destroy_repository.py` script works correctly. You can open the
   `*,v` files using a text editor to see what they contain.

6. Take a note of the exact cvs2svn command line that you used and
   include it along with a tarball of the "destroyed" repository with
   your bug report.

If running `destroy_repository.py` with its default options causes the
bug to go away, consider using `destroy_repository.py` command-line
options to leave part of the repository information intact. Run
`destroy_repository.py --help` for more information.


#### The repository is still too large

This step is a tiny bit more work, so if your repository is already
small enough to send you can skip this step. But this step helps
narrow down the problem (maybe even point you to a corrupt file in
your repository!) so it is still recommended.

The `shrink_test_case.py` script tries to delete as many files and
directories from your repository as possible while preserving the
cvs2svn bug. To use this command, you need to write a little test
script that tries to convert your repository and checks whether the
bug is still present. The script should exit successfully (e.g., `exit
0`) if the bug is still _present_, and fail (e.g., `exit 1`) if the
bug has _disappeared_. The form of the test script depends on the bug
that you saw, but it can be as simple as something like this:

```
#! /bin/sh

cvs2svn --dry-run /path/to/copy/of/repo 2>&1 | grep -q 'KeyError'
```

If the bug is more subtle, then the test script obviously needs to be
more involved.

Once the test script is ready, you can shrink your repository via the
following steps:

1. This procedure will **destroy the repository** that it is applied
   to, so be sure to **make a backup copy of your repository and work
   with the backup!**

2. Make sure you have the `shrink_test_case.py` script. If you don't
   already have it, you should [download the source
   code](https://github.com/mhagger/cvs2svn) for cvs2svn (there is no
   need to install it). The script is located in the `contrib`
   subdirectory.

3. Run `shrink_test_case.py` by typing

    ```
    # You did make a backup, right?
    /path/to/config/shrink_test_case.py /path/to/copy/of/repo testscript.sh
    ```

   where `testscript.sh` is the name of the test script described
   above. This script will execute `testscript.sh` many times, each
   time using a subset of the original repository.

4. If the shrunken repository only consists of one or two files, look
   inside the files with a text editor to see whether they are
   corrupted in any obvious way. (Many so-called cvs2svn "bugs" are
   actually the result of a corrupt CVS repository.)

5. Try converting the "shrunk" repository using cvs2svn, to make sure
   that the original bug still exists. Take a note of the exact
   cvs2svn command line that you used, and include it along with a
   tarball of the "destroyed" repository with your bug report.
