# Makefile for packaging and installing cvs2svn.

DESTDIR=/usr/local

all:
	@echo "Use 'make install' to install, or 'make dist' to package",
	@echo " or 'make check' to run tests."

dist:
	@./dist.sh

install:
	@./setup.py install --prefix=${DESTDIR}

check:
	@./run-tests.py

clean:
	@rm -rf cvs2svn-*.tar.gz *.pyc build
