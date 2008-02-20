#!/usr/bin/perl -w

# Process each tag in a git repository. If the tagged content is
# identical with the content of one of the parents for the commit,
# then the tag is moved to the parent.

# The script is meant to be run against a repository converted
# by cvs2svn, since cvs2svn creates empty commits for all tags.

use strict;

# Find all available tags
my @tags = sort( split( /\n/, qx/git tag -l/ ) );

foreach my $tag (@tags) {
#  print "Processing $tag\n";

  TryToMoveTag( $tag, $tag, 0 )
      or print "$tag not moved\n";
}

sub TryToMoveTag {
  my( $tag, $startcommit, $level ) = @_;

  my @parents = FindParents( $startcommit );

  foreach my $parent (@parents) {
    if( IdenticalTrees( $tag, $parent ) ) {
      if( not TryToMoveTag( $tag, $parent, $level++ ) ) {
#   system( "git tag -f ${tag}-org $tag" );
    system( "git tag -f ${tag} $parent" );
#   print "$tag moved $level levels\n";
      }

      return 1;
    }
  }

  # None of the parents were identical.
  return 0;
}

sub FindParents {
  my( $tag ) = @_;

  my $commit = qx/git cat-file commit $tag/;

  my @parents;

  foreach my $line (split( /\n/, $commit ) ) {
    last if $line =~ /^\s*$/;
    my( $parent ) = ($line =~ /^parent ([0-9a-f]+)$/);
    push @parents, $parent if defined $parent;
  }

  return @parents;
}


sub IdenticalTrees {
  my( $tree1, $tree2 ) = @_;

  # We cannot use git diff --quiet --exit-code, since it doesn't set the
  # correct exit-code in Git 1.5.2.5

  my $diff = qx(git diff  --name-only $tree1 $tree2 -- | wc -l);

  if( $diff > 0 ) {
    # Differences found.
    return 0;
  }
  else {
    # No differences found
    return 1;
  }
}

