# Makefile for packaging and installing cvs2svn.

# The python interpreter to be used can be overridden here or via
# something like "make ... PYTHON=/path/to/python2.5".  Please note
# that this option only affects the "install" and "check" targets:
PYTHON := python

all:
	@echo "Supported make targets:"
	@echo "    man -- Create manpages for the main programs"
	@echo "    install -- Install software using distutils"
	@echo "    dist -- Create an installation package"
	@echo "    check -- Run cvs2svn tests"
	@echo "    pycheck -- Use pychecker to check cvs2svn Python code"
	@echo "    clean -- Clean up source tree and temporary directory"

man: cvs2svn.1 cvs2git.1 cvs2bzr.1

cvs2svn.1:
	./cvs2svn --man >$@

cvs2git.1:
	./cvs2git --man >$@

cvs2bzr.1:
	./cvs2bzr --man >$@

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

check: clean
	${PYTHON} ./run-tests.py

pycheck:
	pychecker cvs2svn_lib/*.py

clean:
	-rm -rf cvs2svn-*.tar.gz build cvs2svn-tmp cvs2*.1
	-for d in . cvs2svn_lib cvs2svn_rcsparse svntest contrib ; \
	do \
		rm -f $$d/*.pyc $$d/*.pyo; \
	done

# Create a docker image, tagged `cvs2svn`, which is ready to run
# `cvs2svn` (as its ENTRYPOINT). The image can be used as follows:
#
#     docker run -it --rm \
#         --mount 'src=/path/to/my/cvs,dst=/cvs,readonly' \
#         --mount 'type=volume,src=/tmp,dst=/tmp' \
#         cvs2svn [OPTS] /cvs
#
# By default, temporary files are stored under `/tmp`, so this
# invocation mounts your local `/tmp` directory there. You should
# either make sure that your `/tmp` partition has enough free space,
# or mount a different directory there.
.PHONY: docker-image
docker-image:
	docker build --target=run -t cvs2svn .

# Create a docker image, then use it to run the automated tests.
.PHONY: docker-test
docker-test:
	docker build --target=test -t cvs2svn-test .
	docker run -it --rm --mount 'type=tmpfs,dst=/tmp' cvs2svn-testing
