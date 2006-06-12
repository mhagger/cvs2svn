# Makefile for packaging and installing cvs2svn.

all:
	@echo "Use 'make install' to install, or 'make dist' to package",
	@echo " or 'make check' to run tests."

dist:
	./dist.sh

install:
	@case "${DESTDIR}" in \
	"") \
	echo ./setup.py install ; \
	./setup.py install ; \
	;; \
	*) \
	echo ./setup.py install --root=${DESTDIR} ; \
	./setup.py install --root=${DESTDIR} ; \
	;; \
	esac

check:
	./run-tests.py

clean:
	rm -rf cvs2svn-*.tar.gz build tmp
	for d in . cvs2svn_lib cvs2svn_rcsparse svntest ; \
	do \
		rm -f $$d/*.pyc $$d/*.pyo; \
	done

