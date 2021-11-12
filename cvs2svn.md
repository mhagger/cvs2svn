# cvs2svn Documentation

:warning: cvs2svn is now in maintenance mode and is not actively being
developed. :warning:

## Introduction

cvs2svn is a program that can be used to migrate a CVS repository
to [Subversion](https://subversion.apache.org/) (otherwise
known as "SVN") or [Git](https://git-scm.com/)

Documentation:

* The [list of cvs2svn features](features.md) explains briefly why
  converting a repository from CVS is nontrivial and gives a
  comprehensive list of cvs2svn's many features.

* The document you are currently reading contains a lot of general
  information about converting from CVS, and specifically how to use
  cvs2svn to convert your repository to Subversion.

* [cvs2svn.md](cvs2git.md) describes how to use cvs2svn to convert
  your CVS repository to git.

* The [FAQ](faq.md) provides frequently asked questions and answers,
  including important topics such as how to convert multiple projects
  within a single repository, how to fix problems with end-of-line
  translation, how to get more help and how to report bugs including a
  useful test case.


## Requirements

cvs2svn requires the following:

* Direct (filesystem) access to a copy of the CVS repository that you
  want to convert. cvs2svn parses the files in the CVS repository
  directly, so it is not enough to have remote CVS access. See the
  [FAQ](faq.md) for more information and a possible workaround.

* Python 2, version 2.4 or later. See http://www.python.org/.
  (`cvs2svn` does **not** work with Python 3.x.)

* A compatible database library, usually `gdbm`, and the corresponding
  Python bindings. Neither `dumbdbm` nor standard `dbm` is sufficient.

* If you use the `--use-rcs` option, then RCS's `co` program is
  required. The RCS home page is
  http://www.cs.purdue.edu/homes/trinkle/RCS/. See the `--use-rcs`
  flag for more details.

* If you use the `--use-cvs` option, then the `cvs` command is
  required. The CVS home page is http://ccvs.cvshome.org/. See the
  `--use-cvs` flag for more details.


## CVSNT repositories

cvs2svn does not support conversion of CVSNT repositories. Some people
have indicated success with such conversions, while others have had
problems. In other words, _such conversions, even if apparently
successful, should be checked carefully before use_. See
the FAQ for more information.

## Installation

* As root, run `make install`.

* Or, if you do not wish to install cvs2svn on your system, you can
  simply run it out of this directory. As long as it can find the
  `cvs2svn_rcsparse` library, it should be happy.

* If you want to create Unix-style manpages for the main programs, run
  `make man`.


## Deciding how much to convert

If you're looking to switch an existing CVS repository to Subversion,
you have a number of choices for migrating your existing CVS data to a
Subversion repository, depending on your needs.

There are a few basic routes to choose when switching from CVS to
Subversion, and the one you choose will depend on how much historical
data you want in your Subversion repository. You may be content to
refer to your existing (soon-to-be-converted-to-read-only) CVS
repository for "pre-Subversion" data and start working with a new
Subversion repository. Maybe you prefer to squeeze every last drop of
data out of your CVS repository into your Subversion repository. Then
again, perhaps you want a conversion somewhere in between these two.
Based on these needs, we've come up with these different recommended
paths for converting your CVS repository to a Subversion
repository.

* [Top-skim](#top-skimming) (Doesn't require cvs2svn!)

* [Trunk only](#trunk-only)

* [Pick and choose](#pick-and-choose)

* [Full conversion](#full-conversion)

* [Smorgasbord](#smorgasbord)

* [One project at a time](#one-project-at-a-time)

If you decide that top-skimming doesn't meet your needs and you're
going to use cvs2svn (yay!), then be sure to read the section below on
prepping your repository before you start your conversion.


### Top-skimming

This is the quickest and easiest way to get started in your new
repository. You're basically going to export the latest revision of
your cvs repository, possibly do some rearranging, and then import the
resulting files into your Subversion repository. Typically, if you
top-skim, that means you'll be either be keeping your old CVS
repository around as a read-only reference for older data or just
tossing that historical data outright (Note to you data packrats who
have just stopped breathing, please take a deep breath and put down
the letter opener. You don't _have_ to do this yourself—it's
just that some people don't feel the same way you do about historical
data. They're really not _bad_ people. Really.)

* **Pros:** Quick, easy, convenient, results in a very compact and
  "neat" Subversion repository.

* **Cons:** You've got no historical data, no branches, and no tags in
  your Subversion repository. If you want any of this data, you'll
  have to go back into the CVS Repository and get it.


### Trunk only

If you decide that you'd like to have the main development line of
your historical data in your Subversion repository but don't need to
carry over the tags and branches, you may want to skip converting your
CVS tags and branches entirely and only convert the "trunk" of your
repository. To do this, you'll use the `--trunk-only` switch to
cvs2svn.

* **Pros:** Saves disk space in your new Subversion repository.
  Attractive to neatniks.

* **Cons:** You've got no branches and no tags in your Subversion
  repository.


### Pick and choose

Let's say, for example, that you want to convert your CVS repository's
historical data but you have no use for the myriad daily build tags
that you've got in your CVS repository. In addition to that, you want
some branches but would prefer to ignore others. In this case, you'll
want to use the `--exclude` switch to instruct cvs2svn which branches
and tags it should ignore.

* **Pros:** You only get what you want from your CVS repository. Saves
  some space.

* **Cons:** If you forgot something, you'll have to go to your CVS
  repository.


### Full conversion

If you want to convert your entire CVS repository, including all tags
and branches, you want a full conversion. This is cvs2svn's default
behavior.

* **Pros:** Converts every last byte of your CVS repository.

* **Cons:** Requires more disk space.


### Smorgasbord

You can convert your repository (or repositories) piece by piece using
a combination of the above.

* **Pros:** You get exactly what you want.

* **Cons:** Importing converted repositories multiple times into a
  single Subversion repository will likely break date-based range
  commands (e.g. `svn diff -r {2002-02-17:2002-03-18}`) since
  Subversion does a binary search through the repository for dates.
  While this is not the end of the world, it can be a minor
  inconvenience.


### One project at a time

If you have many diverse projects in your CVS repository and you don't
want to move them all to Subversion at once, you may want to convert
to Subversion one project at a time. This requires a few extra steps,
but it can make the conversion of a large CVS repository much more
manageable. See "How can I convert my CVS repository one module at a
time? in the cvs2svn FAQ for a detailed example of converting your CVS
repository one project at a time.

* **Pros:** Allows multiple projects in a single repository to convert
  to Subversion according to a schedule that works best for them.

* **Cons:** Requires some extra steps to accomplish the conversion.
  Importing converted repositories multiple times into a single
  Subversion repository will likely break date-based range commands
  (e.g. `svn diff -r {2002-02-17:2002-03-18}`) since Subversion does a
  binary search through the repository for dates. While this is not
  the end of the world, it can be a minor inconvenience.


## Prepping your repository

There are a number of reasons that you may need to prep your CVS
Repository. If you decide that you need to change part of your CVS
repository, we **strongly** recommend working on a **copy** of it
instead of working on the real thing. cvs2svn itself does not make any
changes to your CVS repository, but if you start moving things around
and deleting things in a CVS repository, it's all too easy to shoot
yourself in the foot.

### End-of-line translation

One of the most important topics to consider when converting a
repository is the distinction between binary and text files. If you
accidentally treat a binary file as text **your repository contents
will be corrupted**.

Text files are handled differently than binary files by both CVS and
Subversion. When a text file is checked out, the character used to
denote the end of line ("EOL") is converted to the local computer's
format. This is usually the most convenient behavior for text files.
Moreover, both CVS and Subversion allow "keywords" in text files (such
as `$Id$`), which are expanded with version control information when
the file is checked out. However, if line-end translation or keyword
expansion is applied to a binary file, the file will usually be
corrupted.

CVS treats a file as text unless you specifically tell it that the
file is binary. You can tell CVS that a file is binary by using the
command `cvs admin -kb FILENAME`. But often CVS users forget to
specify which files are binary, and as long as the repository is only
used under Unix, they may never notice a problem, because the internal
format of CVS is the same as the Unix format. But Subversion is not as
forgiving as CVS if you tell it to treat a binary file as text.

If you have been conscientious about marking files as binary in
CVS, then you should be able to use `--default-eol=native`.  If
you have been sloppy, then you have a few choices:

* Convert your repository with cvs2svn's default options. Your text
  files will be treated as binary, but that usually isn't very harmful
  (at least no information will be lost).

* Mend your slovenly ways by fixing your CVS repository _before_
  conversion: run `cvs admin -kb FILENAME` for each binary file in the
  repository. Then you can use `--default-eol=native` along with the
  anal-retentive folks.

* Use cvs2svn options to help cvs2svn deduce which files are binary
  _during_ the conversion. The useful options are
  `--eol-from-mime-type`, `--keywords-off`, `--auto-props`, and
  `--default-eol`. See the FAQ for more information.


### Converting part of repository

If you want to convert a subdirectory in your repository, you can just
point cvs2svn at the subdirectory and go. There is no need to delete
the unwanted directories from the CVS repository.

If the subdirectory that you are converting contains any files that
you _don't_ want converted into your new Subversion repository, you
should delete them or move them aside. Such files can be deleted from
HEAD after the conversion, but they will still be visible in the
repository history.

Lastly, even though you can move and copy files and directories around
in Subversion, you may want to do some rearranging of project
directories before running your conversion to get the desired
repository project organization.


## Command line vs. options file

There are two ways to specify the options that define a conversion:
via the cvs2svn command line, or via an options file. The command line
is useful for simple conversions, but the options file method is
recommended for nontrivial conversions as it gives the user more
flexibility.

### Command line method

A command-line conversion allows the use of all of the command line
options listed below (except for `--options`). This method allows
almost all of the built-in conversion options to be selected, with the
primary limitation that it does not support multiproject conversions.
However, it may require a _long_ command line to specify all of the
options for a complicated conversion.


### Options file method

The options file method allows full control of the conversion process,
including multiproject conversions. It also allows expert users to
customize the conversion even more radically by writing Python code.
Finally, the options file used in the conversion can be retained as
permanent record of the options used in a conversion.

To use the options file method, you need to create a file defining all
of the options that are to be used for the conversion. A
heavily-commented sample options file, `cvs2svn-example.options`, is
included in the cvs2svn distribution. The easiest way to create your
own options file is to make a copy of the sample file and modify it as
directed by the comments in that file.

**Note:** The options file format changes frequently. Please be sure
to base your options file on the `cvs2svn-example.options` file from
the version of cvs2svn that you plan to use.

To start a conversion using an options file, invoke cvs2svn like this:

    $ cvs2svn --options=OPTIONSFILE

Only the following options are allowed in combination with
`--options`: `-h`/`--help`, `--help-passes`, `--version`,
`-v`/`--verbose`, `-q`/`--quiet`, `-p`/`--pass`/`--passes`,
`--dry-run`, and `--profile`.

**Note:** If you want to customize your conversion using your own
Python classes, these classes must be defined in a separate Python
file then imported into the options file. See the FAQ for more
details.


## Symbol handling

cvs2svn converts CVS tags and branches into Subversion tags and
branches. This section discusses issues related to symbol handling.

**HINT:** If there are problems with symbol usage in your repository,
they are usually reported during `CollateSymbolsPass` of the
conversion, causing the conversion to be interrupted. However, it is
not necessary to restart the whole conversion to fix the problems.
Usually it is sufficient to adjust the symbol-handling options then
re-start cvs2svn starting at `CollateSymbolsPass`, by adding the
option `-p CollateSymbolsPass:`. This trick can save a lot of time if
you have a large repository, as it might take a few iterations before
you find the best set of options to convert your repository.


### Placement of trunk, branches, and tags directories

cvs2svn converts CVS branches and tags into Subversion branches and
tags following the [standard Subversion
convention](http://svnbook.red-bean.com/en/1.2/svn.branchmerge.maint.html#svn.branchmerge.maint.layout).
For single-project conversions, the default is to put the trunk,
branches, and tags directories at the top level of the repository
tree, though this behavior can be changed by using the `--trunk`,
`--branches`, and `--tags` options. For multiproject conversions, you
must specify the location of each project's trunk, branches, and tags
directory in the options file; [repository layout
strategies](http://svnbook.red-bean.com/en/1.4/svn.branchmerge.maint.html#svn.branchmerge.maint.layout)
are discussed in the [Subversion book](http://svnbook.red-bean.com/).
For even finer control over the conversion, you can use a
`--symbol-hints` file to specify the SVN path to be used for each CVS
tag and branch.


### Excluding tags and branches

Often a CVS repository contains tags and branches that will not be
needed after the conversion to Subversion. You can instruct cvs2svn to
exclude such symbols from the conversion, in which case they will not
be present in the resulting Subversion repository. Please be careful
when doing this; excluding symbols causes information that was present
in CVS to be omitted in Subversion, thereby discarding potentially
useful historical information. Also be aware that if you exclude a
branch, then all CVS revisions that were committed to that branch will
also be excluded.

To exclude a tag or branch, use the option `--exclude=SYMBOL`. You can
also exclude a whole group of symbols matching a specified regular
expression; for example, `--exclude='RELEASE_0_.*'`. (The regular
expression has to match the _whole_ symbol name for the rule to
apply.)

However, please note the following restriction. If a branch has a
subbranch or a tag on it, then the branch cannot be excluded unless
the dependent symbol is also excluded. cvs2svn checks for this
situation; if it occurs then `CollateSymbolsPass` outputs an error
message like the following:

    ERROR: The branch 'BRANCH' cannot be excluded because the following symbols depend on it:
        'TAG'
        'SUBBRANCH'

In such a case you can either exclude the dependent symbol(s) (in this
case by using `--exclude=TAG --exclude=SUBBRANCH`) or _not_ exclude
`BRANCH`.

#### Excluding vendor branches

There is one more special case related to branch handling. A [vendor
branch](http://cvsbook.red-bean.com/cvsbook.html#Tracking%20Third-Party%20Sources%20(Vendor%20Branches))
is a CVS branch that is used to track source code received from an
outside source. A vendor branch typically has CVS branch number
`1.1.1` and revision numbers `1.1.1.1`, `1.1.1.2`, etc. Vendor
branches are created automatically whenever the `cvs import` command
is used. Vendor branches have the strange property that, under certain
circumstances, a file that appears on a vendor branch also implicitly
exists on trunk. cvs2svn knows all about vendor branches and does its
best to ensure that a file that appears on a vendor branch is also
copied to trunk, to give Subversion behavior that is as close as
possible to the CVS behavior.

However, often vendor branches exist for reasons unrelated to tracking
outside sources. Indeed, some CVS documentation recommends using the
`cvs import` command to import your own code into your CVS repository
(which is arguably a misuse of the `cvs import` command). Vendor
branches created by this practice are useless and would only serve to
clutter up your Subversion repository. Therefore, cvs2svn allows
vendor branches to be excluded, in which case the vendor branch
revisions are grafted onto the history of trunk. This is allowed _even
if_ other branches or tags appear to sprout from the vendor branch, in
which case the dependent tags are grafted to trunk as well. Such
branches can be recognized in the `--write-symbol-info` output by
looking for a symbol that is a "pure import" in the same number of
files that it appears as a branch. It is typically advantageous to
exclude such branches.


### Tag/branch inconsistencies

In CVS, the same symbol can appear as a tag in some files (e.g., `cvs
tag SYMBOL file1.txt`) and a branch in others (e.g., `cvs tag -b
SYMBOL file2.txt`). Subversion takes a more global view of your
repository, and therefore works better when each symbol is used in a
self-consistent way—either always as a branch or always as a tag.
cvs2svn provides features to help you resolve these ambiguities.

If your repository contains inconsistently-used symbols, then
`CollateSymbolsPass`, by default, uses heuristics to decide which
symbols to convert as branches and which as tags. Often this behavior
will be adequate, and you don't have to do anything special. You can
use the `--write-symbol-info=FILENAME` option to cause cvs2svn to list
to `FILENAME` all of the symbols in your repository and how it chose
to convert them.

However, if you want to take finer control over how symbols are
converted, you can do so. The first step is probably to change the
default symbol handling style from `heuristic` (the default value) to
`strict` using the option `--symbol-default=strict`. With the `strict`
setting, cvs2svn prints error messages and aborts the conversion if
there are any ambiguous symbols. The error messages look like this:

    ERROR: It is not clear how the following symbols should be converted.
    Use --symbol-hints, --force-tag, --force-branch, --exclude, and/or
    --symbol-default to resolve the ambiguity.
        'SYMBOL1' is a tag in 1 files, a branch in 2 files and has commits in 0 files
        'SYMBOL2' is a tag in 2 files, a branch in 1 files and has commits in 0 files
        'SYMBOL3' is a tag in 1 files, a branch in 2 files and has commits in 1 files

You have to tell cvs2svn how to fix the inconsistencies, then restart
the conversion at `CollateSymbolsPass`.

There are three ways to deal with an inconsistent symbol: treat it as
a tag, treat it as a branch, or exclude it from the conversion
altogether.

In the example above, the symbol `SYMBOL1` was used as a branch in two
files but used as a tag in only one file. Therefore, it might make
sense to convert it as a branch, by using the option
`--force-branch=SYMBOL1`. However, no revisions were committed on this
branch, so it would also be possible to convert it as a tag, by using
the option `--force-tag=SYMBOL1`. If the symbol is not needed at all,
it can be excluded by using `--exclude=SYMBOL1`.

Similarly, `SYMBOL2` was used more often as a tag, but can still be
converted as a branch or a tag, or excluded.

`SYMBOL3`, on the other hand, was sometimes used as a branch, and at
least one revision was committed on the branch. It can be converted as
a branch, using `--force-branch=SYMBOL3`. But it cannot be converted
as a tag (because tags are not allowed to have revisions on them). If
it is excluded, using `--exclude=SYMBOL3`, then both the branch and
the revisions on the branch will be left out of the Subversion
repository.

If you are not so picky about which symbols are converted as tags and
which as branches, you can ask cvs2svn to decide by itself. To do
this, specify the `--symbol-default=OPTION`, where `OPTION` can be
either `heuristic` (the default; decide how to treat each ambiguous
symbol based on whether it was used more often as a branch or as a tag
in CVS), `branch` (treat every ambiguous symbol as a branch), or `tag`
(treat every ambiguous symbol as a tag). You can use the
`--force-branch` and `--force-tag` options to specify the treatment of
particular symbols, in combination with `--symbol-default` to specify
the default to be used for other ambiguous symbols.

Finally, you can have cvs2svn write a text file showing how each
symbol was converted, by using the `--write-symbol-info` option. If
you disagree with any of cvs2svn's choices, you can make a copy of
this file, edit it, then pass it to cvs2svn by using the
`--symbol-hints` option. In this manner you can influence how each
symbol is converted and also the parent line of development of each
symbol (the line of development from which the symbol sprouts).


## Command line reference

    cvs2svn [OPTIONS]... [-s SVN-REPOS-PATH|--dumpfile=PATH|--dry-run] CVS-REPOS-PATH
    cvs2svn [OPTIONS]... --options=PATH

* `CVS-REPOS-PATH` — The filesystem path of the part of the CVS
    repository that you want to convert. It is not possible to convert
    a CVS repository to which you only have remote access; see the FAQ
    for details. This doesn't have to be the top level directory of a
    CVS repository; it can point at a project within a repository, in
    which case only that project will be converted. This path or one
    of its parent directories has to contain a subdirectory called
    CVSROOT (though the CVSROOT directory can be empty).

### Configuration via options file

* `--options=PATH` — Read the conversion options from the specified
    file. See section "options file method" for more information.

### Output options

* `-s PATH`, `--svnrepos PATH` — Write the output of the conversion
    into a Subversion repository located at `PATH`. This option causes
    a new Subversion repository to be created at `PATH` unless the
    `--existing-svnrepos` option is also used.

* `--existing-svnrepos` — Load the converted CVS repository into an
    existing Subversion repository, instead of creating a new
    repository. (This option should be used in combination with
    `-s`/`--svnrepos`.) The repository must either be empty or contain
    no paths that overlap with those that will result from the
    conversion. Please note that you need write permission for the
    repository files.

* `--fs-type=TYPE` — Pass the `--fs-type=TYPE` option to `svnadmin
    create` if creating a new Subversion repository.

* `--bdb-txn-nosync` — Pass the `--bdb-txn-nosync` switch to `svnadmin
    create` if creating a new Subversion repository.

* `--create-option=OPT` — Pass `OPT` to `svnadmin create` if creating
    a new Subversion repository (can be specified multiple times to
    pass multiple options).

* `--dumpfile=PATH` — Output the converted CVS repository into a
    Subversion dumpfile instead of a Subversion repository (useful for
    importing a CVS repository into an existing Subversion
    repository). `PATH` is the filename in which to store the
    dumpfile.

* `--dry-run` — Do not create a repository or a dumpfile; just print
    the details of what cvs2svn would do if it were really converting
    your repository.

### Conversion options

* `--trunk-only` — Convert only the main line of development from the
    CVS repository (commonly referred to in Subversion parlance as
    "trunk"), ignoring all tags and branches.

* `--trunk=PATH` — The top-level path to use for trunk in the
    Subversion repository. The default value is "trunk".

* `--branches=PATH` — The top-level path to use for branches in the
    Subversion repository. The default value is "branches".

* `--tags=PATH` — The top-level path to use for tags in the Subversion
    repository. The default value is "tags".

* `--include-empty-directories` — Treat empty subdirectories within
    the CVS repository as actual directories, creating them when the
    parent directory is created and removing them if and when the
    parent directory is pruned.

* `--no-prune` — When all files are deleted from a directory in the
    Subversion repository, don't delete the empty directory (the
    default is to delete any empty directories.

* `--encoding=ENC` — Use ENC as the encoding for filenames, log
    messages, and author names in the CVS repos. (By using an
    `--options` file, it is possible to specify one set of encodings
    to use for filenames and a second set for log messages and author
    names.) This option may be specified multiple times, in which case
    the encodings are tried in order until one succeeds. Default:
    ascii. Other possible values include the [standard Python
    encodings](http://docs.python.org/lib/standard-encodings.html).

* `--fallback-encoding=ENC` — If none of the encodings specified with
    `--encoding` succeed in decoding an author name or log message,
    then fall back to using `ENC` in lossy `replace` mode. Use of this
    option may cause information to be lost, but at least it allows
    the conversion to run to completion. This option only affects the
    encoding of log messages and author names; there is no fallback
    encoding for filenames. (By using an `--options` file, it is
    possible to specify a fallback encoding for filenames.) Default:
    disabled.

* `--no-cross-branch-commits` — Prevent the creation of SVN commits
    that affect multiple branches or trunk and a branch. Instead,
    break such changesets into multiple commits, one per branch.

* `--retain-conflicting-attic-files` — If a file appears both inside
    an outside of the CVS attic, retain the attic version in an SVN
    subdirectory called `Attic`. (Normally this situation is treated
    as a fatal error.)

### Symbol handling

* `--symbol-transform=PAT:SUB` — Transform RCS/CVS symbol names before
    entering them into Subversion. `PAT` is a Python regular
    expression pattern that is matched against the entire symbol name.
    If it matches, the symbol is replaced with `SUB`, which is a
    replacement pattern using Python's reference syntax. You may
    specify any number of these options; they will be applied in the
    order given on the command line.

    This option can be useful if you're converting a repository in
    which the developer used directory-wide symbol names like `1_0`,
    `1_1` and `2_1` as a kludgy form of release tagging (the `C-x v s`
    command in Emacs VC mode encourages this practice). A command like

        cvs2svn --symbol-transform='([0-9])-(.*):release-\1.\2' -s SVN RCS

    will transform a local CVS repository into a local SVN repository,
    performing the following sort of mappings of RCS symbolic names to
    SVN tags:

    * `1-0` → `release-1.0`
    * `1-1` → `release-1.1`
    * `2-0` → `release-2.0`

* `--symbol-hints=PATH` — Read symbol conversion hints from `PATH`.
    The format of `PATH` is the same as the format output by
    `--write-symbol-info`, namely a text file with four
    whitespace-separated columns:

        project-id symbol conversion svn-path parent-lod-name

    * `project-id` is the numerical ID of the project to which the
      symbol belongs, counting from 0. `project-id` can be set to `.`
      if project-specificity is not needed.
    * `symbol-name` is the name of
      the symbol being specified.
    * `conversion` specifies how the symbol should be converted, and
      can be one of the values `branch`, `tag`, or `exclude`. If
      `conversion` is `.`, then this rule does not affect how the
      symbol is converted.
    * `svn-path` is the name of the SVN path to which this line of
      development should be written. If `svn-path` is omitted or `.`,
      then this rule does not affect the SVN path of this symbol.
    * `parent-lod-name` is the name of the symbol from which this
      symbol should sprout, or `.trunk.` if the symbol should sprout
      from trunk. If `parent-lod-name` is omitted or `.`, then this
      rule does not affect the preferred parent of this symbol.

    The file may contain blank lines or comment lines (lines whose
    first non-whitespace character is `#`).

    The simplest way to use this option is to run the conversion
    through `CollateSymbolsPass` with `--write-symbol-info` option,
    copy the symbol info and edit it to create a hints file, then
    re-start the conversion at `CollateSymbolsPass` with this option
    enabled.

* `--symbol-default=OPT` — Specify how to convert ambiguous symbols
    (i.e., those that appear in the CVS archive as both branches and
    tags). `OPT` is one of the following:

    * `heuristic`: Decide how to treat each ambiguous symbol based on
      whether it was used more often as a branch or tag in CVS. (This
      is the default behavior.)
    * `strict`: No default; every ambiguous symbol has to be resolved
      manually using `--symbol-hints`, `--force-branch`,
      `--force-tag`, or `--exclude`.
    * `branch`: Treat every ambiguous symbol as a branch.
    * `tag`: Treat every ambiguous symbols as a tag.

* `--force-branch=REGEXP` Force symbols whose names match `REGEXP` to
    be branches.

* `--force-tag=REGEXP` — Force symbols whose names match `REGEXP` to
    be tags. This will cause an error if such a symbol has commits on
    it.

* `--exclude=REGEXP` — Exclude branches and tags whose names match
    `REGEXP` from the conversion.

* `--keep-trivial-imports` — Do not exclude branches that were only
    used for a single import. (By default such branches are excluded
    because they are usually created by the inappropriate use of `cvs
    import`.)

### Subversion properties

* `--username=NAME` — Use `NAME` as the author for cvs2svn-synthesized
    commits (the default value is no author at all.</td> </tr>

* `--auto-props=FILE` — Specify a file in the format of Subversion's
    config file, whose `[auto-props]` section can be used to set
    arbitrary properties on files in the Subversion repository based
    on their filenames. (The `[auto-props]` section header must be
    present; other sections of the config file, including the
    `enable-auto-props` setting, are ignored.) Filenames are matched
    to the filename patterns case-insensitively, consistent with
    Subversion's behavior. The auto-props file might have content like
    this:

        [auto-props]
        *.txt = svn:mime-type=text/plain;svn:eol-style=native
        *.doc = svn:mime-type=application/msword;!svn:eol-style

    Please note that cvs2svn allows properties to be explicitly
    _unset_: if cvs2svn sees a setting like `!svn:eol-style` (with a
    leading exclamation point), it forces the property to remain
    _unset_, even if later rules would otherwise set the property.

* `--mime-types=FILE` — Specify an apache-style `mime.types` file for
    setting `svn:mime-type` properties on files in the Subversion
    repository.

* `--eol-from-mime-type` — For files that don't have the `kb`
    expansion mode but have a known mime type, set the eol-style based
    on the mime type. For such files, set the `svn:eol-style` property
    to `native` if the mime type begins with `text/`, and leave it
    unset (i.e., no EOL translation) otherwise. Files with unknown
    mime types are not affected by this option. This option has no
    effect unless the `--mime-types` option is also specified.

* `--default-eol=STYLE` — Set `svn:eol-style` to `STYLE` for files
    that don't have the `kb` expansion mode and whose end-of-line
    translation mode hasn't been determined by one of the other
    options. STYLE can be `binary` (default), `native`, `CRLF`, `LF`,
    or `CR`.

* `--keywords-off` — By default, cvs2svn sets `svn:keywords` on CVS
    files to `Author Date Id Revision` if the file's `svn:eol-style`
    property is set (see the `--default-eol` option). The
    `--keywords-off` switch prevents cvs2svn from setting
    `svn:keywords` for any file. (The result for files that _do_
    contain keyword strings is somewhat unexpected: the keywords will
    be left with the expansions that they had when committed to CVS,
    which is usually the expansion for the _previous_ revision.)

* `--keep-cvsignore` — Include `.cvsignore` files in the output.
    (Normally they are unneeded because cvs2svn sets the corresponding
    `svn:ignore` properties.)

* `--cvs-revnums` — Record CVS revision numbers as file properties in
    the Subversion repository. (Note that unless it is removed
    explicitly, the last CVS revision number will remain associated
    with the file even after the file is changed within
    Subversion.)

### Extraction options

* `--use-internal-co` — Use internal code to extract the contents of
    CVS revisions. This is the default extraction option. This is up
    to 50% faster than `--use-rcs`, but needs a lot of disk space:
    roughly the size of your CVS repository plus the peak size of a
    complete checkout of the repository with all branches that existed
    and still had commits pending at a given time. If this option is
    used, the `$Log$` keyword is not handled.

* `--use-rcs` — Use RCS's `co` command to extract the contents of CVS
    revisions. RCS is much faster than CVS, but in certain rare cases
    it has problems with data that CVS can handle. Specifically:

    * RCS can't handle spaces in author names.
    * "Unterminated keyword" misread by RCS.
    * RCS handles the `$Log$` keyword differently than CVS

    If you are having trouble in `OutputPass` of a conversion when
    using the `--use-rcs` option, the first thing to try is using the
    `--use-cvs` option instead.

* `--use-cvs` — If RCS `co` is having trouble extracting CVS
    revisions, you may need to pass this flag, which causes cvs2svn to
    use CVS instead of RCS to read the repository. See `--use-rcs` for
    more information.

### Environment options

* `--tmpdir=PATH` — Use the directory `PATH` for all of cvs2svn's
    temporary data (which can be a _lot_ of data). The default is to
    store the temporary data in a subdirectory under the platform's
    usual place for temporary files (e.g., `/tmp`). Please note that
    if you want to use the `--passes` feature, you have to pass the
    same `--tmpdir` option at each invocation.

* `--svnadmin=PATH` — If the `svnadmin` program is not in your
    `$PATH`, you should specify its absolute path with this switch.
    (`svnadmin` is needed when the `-s`/`--svnrepos` output option is
    used.)

* `--co=PATH` — If the `co` program (a part of RCS) is not in your
    `$PATH` you should specify its absolute path with this switch.
    (`co` is needed if the `--use-rcs` extraction option is
    used.)

* `--cvs=PATH` — If the `cvs` program is not in your `$PATH` you
    should specify its absolute path with this switch. (`cvs` is
    needed if the `--use-cvs` extraction option is used.)

### Partial conversions

* `-p PASS`, `--pass PASS` — Execute only pass `PASS` of the
    conversion. `PASS` can be specified by name or by number (see
    `--help-passes`).

* `-p [START]:[END]`, `--passes [START]:[END]` — Execute passes
    `START` through `END` of the conversion (inclusive). `START` and
    `END` can be specified by name or by number (see `--help-passes`).
    If `START` or `END` is missing, it defaults to the first or last
    pass, respectively.

### Information options

* `--version` — Print the version number.

* `--help`, `-h` — Print the usage message and exit with success.

* `--help-passes` — Print the numbers and names of the conversion
    passes and exit with success.

* `--man` — Write the manpage for this program to standard output.

* `--verbose`, `-v` — Tell cvs2svn to print lots of information about
    what it's doing to stdout. This option can be specified twice to
    get debug-level output.

* `--quiet`, `-q` — Tell cvs2svn to operate in quiet mode, printing
    little more than pass starts and stops to stdout. This option may
    be specified twice to suppress all non-error output.

* `--write-symbol-info=PATH` — Write symbol statistics and information
    about how symbols were converted to `PATH` during
    `CollateSymbolsPass`. See `--symbol-hints` for a description of
    the output format.

* `--skip-cleanup` — Prevent the deletion of the temporary files that
    cvs2svn creates in the process of conversion.

* `--profile` — Dump Python
    [cProfile](http://docs.python.org/library/profile.html) profiling
    data to the file `cvs2svn.cProfile`. In Python 2.4 and earlier, if
    cProfile is not installed, it will instead dump
    [Hotshot](http://docs.python.org/library/hotshot.html) profiling
    data to the file `cvs2svn.hotshot`.


## A Few Examples

To create a new Subversion repository by converting an existing CVS
repository, run the script like this:

    $ cvs2svn --svnrepos NEW_SVNREPOS CVSREPOS

To create a new Subversion repository containing only trunk commits,
and omitting all branches and tags from the CVS repository, do

    $ cvs2svn --trunk-only --svnrepos NEW_SVNREPOS CVSREPOS

To create a Subversion dumpfile (suitable for `svnadmin load`) from a
CVS repository, run it like this:

    $ cvs2svn --dumpfile DUMPFILE CVSREPOS

To use an options file to define all of the conversion parameters,
specify `--options`:

    $ cvs2svn --options OPTIONSFILE

As it works, cvs2svn creates many temporary files (see `--tmpdir`).
This is normal. After a pass completes successfully, the temporary
files that are no longer needed are deleted automatically. If a pass
fails, or if you specify the `--skip-cleanup` option, cvs2svn will
leave the temporary files behind for possible debugging and/or
resumption of the pass using the `--passes` option.
