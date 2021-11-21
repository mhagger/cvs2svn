# cvs2svn features

The primary goal of cvs2svn is to migrate as much information as
possible from your old CVS repository to your new Subversion or git
repository.

Unfortunately, CVS doesn't record complete information about your
project's history. For example, CVS doesn't record what file
modifications took place together in the same CVS commit. Therefore,
cvs2svn attempts to infer from CVS's incomplete information what
_really_ happened in the history of your repository. So the second
goal of cvs2svn is to reconstruct as much of your CVS repository's
history as possible.

The third goal of cvs2svn is to allow you to customize the conversion
process and the form of your output repository as flexibly as
possible. cvs2svn has very many conversion options that can be used
from the command line, many more that can be configured via an options
file, and provides many hooks to allow even more extreme customization
by writing Python code.

## Feature summary

### No information lost

cvs2svn works hard to avoid losing any information from your CVS
repository (unless you specifically ask for a partial conversion using
`--trunk-only` or `--exclude`).

### Changesets

CVS records modifications file-by-file, and does not keep track of
what files were modified at the same time. cvs2svn uses information
like the file modification times, log messages, and dependency
information to deduce the original changesets. cvs2svn allows
changesets that affect multiple branches and/or multiple projects (as
is allowed by CVS), or it can be configured to split such changesets
up into separate commits (`--no-cross-branch-commits`; see also
options file).

### Multiproject conversions

cvs2svn can convert a CVS repository that contains multiple projects
into a single Subversion repository with the conventional multiproject
directory layout. See the FAQ for more information.

### Branch vs. tag

CVS allows the same symbol name to be used sometimes as a branch,
sometimes as a tag. cvs2svn has options and heuristics to decide how
to convert such "mixed" symbols (`--symbol-hints`, `--force-branch`,
`--force-tag`, `--symbol-default`).

### Branch/tag exclusion

cvs2svn allows the user to specify branches and/or tags that should be
excluded from the conversion altogether (`--symbol-hints`,
`--exclude`). It checks that the exclusions are self-consistent (e.g.,
it doesn't allow a branch to be excluded if a branch that sprouts from
it is not excluded).

### Branch/tag renaming

cvs2svn can rename branches and tags during the conversion using
regular-expression patterns (`--symbol-transform`).

### Choosing SVN paths for branches/tags

You can choose what SVN paths to use as the trunk/branches/tags
directories (`--trunk`, `--branches`, `--tags`), or set arbitrary
paths for specific CVS branches/tags (`--symbol-hints`). For example,
you might want to store some tags to the `project/tags` directory, but
others to `project/releases`.

### Branch and tag parents

In many cases, the CVS history is ambiguous about which branch served
as the parent of another branch or tag. cvs2svn determines the most
plausible parent for symbols using cross-file information. You can
override cvs2svn's choices on a case-by-case basis by using the
`--symbol-hints` option.

### Branch and tag creation times

CVS does not record when branches and tags are created. cvs2svn
creates branches and tags at a reasonable time, consistent with the
file revisions that were tagged, and tries to create each one within a
single Subversion commit if possible.

### Mime types

CVS does not record files' mime types. cvs2svn provides several
mechanisms for choosing reasonable file mime types (`--mime-types`,
`--auto-props`).

### Binary vs. text

Many CVS users do not systematically record which files are binary and
which are text. (This is mostly important if the repository is used on
non-Unix systems.) cvs2svn provides a number of ways to infer this
information (`--eol-from-mime-type`, `--default-eol`,
`--keywords-off`, `--auto-props`).

### Subversion file properties

Subversion allows arbitrary text properties to be attached to files.
cvs2svn provides a mechanism to set such properties when a file is
first added to the repository (`--auto-props`) as well as a hook that
users can use to set arbitrary file properties via Python code.

### Handling of `.cvsignore`

`.cvsignore` files in the CVS repository are converted into the
equivalent `svn:ignore` properties in the output. By default, the
`.cvsignore` files themselves are _not_ included in the output; this
behavior can be changed by specifying the `--keep-cvsignore` option.

### Subversion repository customization

cvs2svn provides many options that allow you to customize the
structure of the resulting Subversion repository (`--trunk`,
`--branches`, `--tags`, `--include-empty-directories`, `--no-prune`,
`--symbol-transform`, etc.; see also the additional customization
options available by using the `--options`-file method).

### Support for multiple character encodings

CVS does not record which character encoding was used to store
metainformation like file names, author names and log messages.
cvs2svn provides options to help convert such text into UTF-8
(`--encoding`, `--fallback-encoding`).

### Vendor branches

CVS supports "vendor branches", which (under some circumstances)
affect the contents of the main line of development. cvs2svn detects
vendor branches whenever possible and handles them intelligently. For
example,

* cvs2svn explicitly copies vendor branch revisions back to trunk so
  that a checkout of trunk gives the same results under SVN as under
  CVS.

* If a vendor branch is excluded from the conversion, cvs2svn grafts
  the relevant vendor branch revisions onto trunk so that the contents
  of trunk are still the same as in CVS. If other tags or branches
  sprout from these revisions, they are grafted to trunk as well.

* When a file is imported into CVS, CVS creates two revisions (`1.1`
  and `1.1.1.1`) with the same contents. cvs2svn discards the
  redundant `1.1` revision in such cases (since revision `1.1.1.1`
  will be copied to trunk anyway).

* Often users create vendor branches unnecessarily by using `cvs
  import` to import their own sources into the CVS repository. Such
  vendor branches do not contain any useful information, so by default
  cvs2svn excludes any vendor branch that was only used for a single
  import. You can change this default behavior by specifying the
  `--keep-trivial-imports` option.

### CVS quirks

cvs2svn goes to great length to deal with CVS's many quirks. For
example,

* CVS introduces spurious `1.1` revisions when a file is added on a
  branch. cvs2svn discards these revisions.

* If a file is added on a branch, CVS introduces a spurious "dead"
  revision at the beginning of the branch to indicate that the file
  did not exist when the branch was created. cvs2svn deletes these
  spurious revisions and adds the file on the branch at the correct
  time.

### Robust against repository corruption

cvs2svn knows how to handle several types of CVS repository corruption
that have been reported frequently, and gives informative error
messages in other cases:

* An RCS file that exists both in and out of the `Attic` directory.
* Multiple deltatext blocks for a single CVS file revision.
* Multiple revision headers for the same CVS file revision.
* Tags and branches that refer to non-existent revisions or ill-formed
  revision numbers.
* Repeated definitions of a symbol name to the same revision number.
* Branches that have no associated labels.
* A directory name that conflicts with a file name (in or out of the
  `Attic`).
* Filenames that contain forbidden characters.
* Log messages with variant end-of-line styles.
* Vendor branch declarations that refer to non-existent branches.

### Timestamp error correction

Many CVS repositories contain timestamp errors due to servers' clocks
being set incorrectly during part of the repository's history.
cvs2svn's history reconstruction is relatively robust against
timestamp errors and it writes monotonic timestamps to the Subversion
repository.

### Scalable

cvs2svn stores most intermediate data to on-disk databases so that it
can convert very large CVS repositories using a reasonable amount of
RAM. Conversions are organized as multiple passes and can be restarted
at an arbitrary pass in the case of problems.

### Configurable/extensible using Python

Many aspects of the conversion can be customized using Python plugins
that interact with cvs2svn through documented interfaces
(`--options`).
