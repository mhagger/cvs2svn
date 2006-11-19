#!/usr/bin/perl -w

#
# (C) 2005 The Measurement Factory   http://www.measurement-factory.com/
# This software is distributed under Apache License, version 2.0.
#

# The cvsVsvn.pl script compares CVS and Subversion projects.  The
# user is notified if project files maintained by CVS differ from
# those maintained by Subversion:
#
#   $ CVSROOT=/my/cvsrepo ./cvsVsvn project1 svn+ssh://host/path/projects/p1
#   collecting CVS tags...
#   found 34 CVS tags
#   comparing tagged snapshots...
#   HEAD snapshots appear to be the same
#   ...
#   CVS and SVN repositories differ because cvs_foo and svn_tags_foo
# export directories differ in cvsVsvn.tmp
#
# The comparison is done for every CVS tag and branch (including
# HEAD), by exporting corresponding CVS and Subversion snapshots and
# running 'diff' against the two resulting directories.  One can edit
# the script or use the environment variable DIFF_OPTIONS to alter
# 'diff' behavior (e.g., ignore differences in some files).

# Commit logs are not compared, unfortunately.  This script is also
# confused by files that differ due to different keyword expansion by
# CVS and SVN.

use strict;

# cvsVsvn exports a user-specified module from CVS and Subversion
# repositories and compares the two exported directories using the
# 'diff' tool.  The procedure is performed for all CVS tags (including
# HEAD and branches).

die(&usage()) unless @ARGV == 2;
my ($CvsModule, $SvnModule) = @ARGV;

my $TmpDir = 'cvsVsvn.tmp'; # directory to store temporary files

my @Tags = &collectTags();

print(STDERR "comparing tagged snapshots...\n");
foreach my $tagPair (@Tags) {
    &compareTags($tagPair->{cvs}, $tagPair->{svn});
}

print(STDERR "CVS and Subversion repositories appear to be the same\n");
exit(0);

sub collectTags {
    print(STDERR "collecting CVS tags...\n");

    my @tags = (
        {
            cvs => 'HEAD',
            svn => 'trunk'
        }
    );

    # get CVS log headers with symbolic tags
    my %names = ();
    my $inNames;
    my $cmd = sprintf('cvs rlog -h %s', $CvsModule);
    open(IF, "$cmd|") or die("cannot execute $cmd: $!, stopped");
    while (<IF>) {
        if ($inNames) {
            my ($name, $version) = /\s+(\S+):\s*(\d\S*)/;
            if ($inNames = defined $version) {
                my @nums = split(/\./, $version);
                my $isBranch =
                    (2*int(@nums/2) != @nums) ||
                    (@nums > 2 && $nums[$#nums-1] == 0);
                my $status = $isBranch ? 'branches' : 'tags';
                my $oldStatus = $names{$name};
                next if $oldStatus && $oldStatus eq $status;
                die("change in $name tag status, stopped") if $oldStatus;
                $names{$name} = $status;
            }
        } else {
            $inNames = /^symbolic names:/;
        }
    }
    close(IF);

    while (my ($name, $status) = each %names) {
        my $tagPair = {
            cvs => $name,
            svn => sprintf('%s/%s', $status, $name)
        };
        push (@tags, $tagPair);
    }

    printf(STDERR "found %d CVS tags\n", scalar @tags);
    return @tags;
}

sub compareTags {
    my ($cvsTag, $svnTag) = @_;

    &prepDirs();

    &cvsExport($cvsTag);
    &svnExport($svnTag);

    &diffDir($cvsTag, $svnTag);

    # identical directories, clean up
    &cleanDirs();
}

sub diffDir {
    my ($cvsTag, $svnTag) = @_;
    my $cvsDir = &cvsDir($cvsTag);
    my $svnDir = &svnDir($svnTag);

    my $same = systemf('diff --brief -b -B -r "%s" "%s"',
        $cvsDir, $svnDir) == 0;
    die("CVS and SVN repositories differ because ".
        "$cvsDir and $svnDir export directories differ in $TmpDir; stopped")
        unless $same;

    print(STDERR "$cvsTag snapshots appear to be the same\n");
    return 0;
}

sub makeDir {
    my $dir = shift;
    &systemf('mkdir %s', $dir) == 0 or die("cannot create $dir: $!, stopped");
}

sub prepDirs {
    &makeDir($TmpDir);
    chdir($TmpDir) or die($!);
}

sub cleanDirs {
    chdir('..') or die($!);
    &systemf('rm -irf %s', $TmpDir) == 0
        or die("cannot delete $TmpDir: $!, stopped");
}

sub cvsExport {
    my ($cvsTag) = @_;

    my $dir = &cvsDir($cvsTag);
    &makeDir($dir);
    &systemf('cvs -Q export -r %s -d %s %s', $cvsTag, $dir, $CvsModule) == 0
        or die("cannot export $cvsTag of CVS module '$CvsModule', stopped");
}

sub svnExport {
    my ($svnTag) = @_;

    my $dir = &svnDir($svnTag);
    my $cvsOk =
        &systemf('svn list %s/%s > /dev/null', $SvnModule, $svnTag) == 0
        && &systemf('svn -q export %s/%s %s', $SvnModule, $svnTag, $dir) == 0;
    die("cannot export $svnTag of svn module '$SvnModule', stopped")
        unless $cvsOk && -d $dir;
}

sub tag2dir {
    my ($category, $tag) = @_;

    my $dir = sprintf('%s_%s', $category, $tag);
    # remove dangerous chars
    $dir =~ s/[^A-z0-9_\.\-]+/_/g;
    return $dir;
}

sub cvsDir {
    return &tag2dir('cvs', @_);
}

sub svnDir {
    return &tag2dir('svn', @_);
}

sub systemf {
    my ($fmt, @params) = @_;

    my $cmd = sprintf($fmt, (@params));
    #print(STDERR "$cmd\n");
    return system($cmd);
}

sub usage {
    return "usage: $0 <CVS module name> <Subversion URL>\n";
}


