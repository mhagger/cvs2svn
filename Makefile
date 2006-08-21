# Makefile for packaging and installing cvs2svn.

# The python interpreter to be used can be overridden here or via
# something like "make ... PYTHON=python2.2":
PYTHON=python

all:
	@echo "Use 'make install' to install, or 'make dist' to package",
	@echo " or 'make check' to run tests."

dist:
	./dist.sh

install:
	@case "${DESTDIR}" in \
	"") \
	echo ${PYTHON} ./setup.py install ; \
	${PYTHON} ./setup.py install ; \
	;; \
	*) \
	echo ${PYTHON} ./setup.py install --root=${DESTDIR} ; \
	${PYTHON} ./setup.py install --root=${DESTDIR} ; \
	;; \
	esac

check:
	${PYTHON} ./run-tests.py

clean:
	rm -rf cvs2svn-*.tar.gz build tmp
	for d in . cvs2svn_lib cvs2svn_rcsparse svntest ; \
	do \
		rm -f $$d/*.pyc $$d/*.pyo; \
	done

