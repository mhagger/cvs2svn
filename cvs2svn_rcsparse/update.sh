#!/bin/sh

# Update the rcsparse library from ViewCVS CVS

# First update the rcsparse files
cvs update

# Now update compat.py (which is not in this directory, in the upstream CVS)
# -f option is to suppress possible -d in .cvsrc
cvs -f update compat
cp compat/compat.py compat.py

