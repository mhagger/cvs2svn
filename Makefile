# Makefile for packaging and installing cvs2svn.

all:
	@echo "Use 'make install' to install, or 'make dist' to package."

dist:
	@./dist.sh

install:
	@./setup.py install

clean:
	@rm -rf cvs2svn-*.tar.gz *.pyc
