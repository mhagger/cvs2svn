# This is a convenience Makefile, allowing "make" to be invoked in the
# cvs2svn_lib directory.  It simply re-invokes make in the main
# project directory.

.PHONY: all
all::
	$(MAKE) -C ..

%:
	$(MAKE) -C .. $@

