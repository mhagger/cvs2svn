%define make_cvs2svn_check 1
Summary: Convert CVS repositories to Subversion repositories.
Name: cvs2svn
Version: @VERSION@
Release: @RELEASE@
Copyright: BSD
Group: Utilities/System
URL: http://cvs2svn.tigris.org
SOURCE0: cvs2svn-%{version}-%{release}.tar.gz
Vendor: Summersoft
BuildArchitectures: noarch
Packager: David Summers <david@summersoft.fay.ar.us>
Requires: python >= 2
Requires: rcs
Requires: subversion-python >= 1.0.1
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}
Prefix: /usr
%description
Convert CVS repositories to Subversion repositories.

%changelog
* Wed Jul 06 2004 David Summers <david@summersoft.fay.ar.us> 0.1237-1
- Make use of new DESTDIR capability for "make install".
- Take out hacks to install files and delete CVS and .cvsignore files.

* Tue Jul 06 2004 David Summers <david@summersoft.fay.ar.us> 0.1222-1
- Track changes to build system.
- Now uses Makefile.
- Cleanup CVS directories from package.

* Mon Mar 15 2004 David Summers <david@summersoft.fay.ar.us> 0.829-1
- Switched version to accomodate suggestions in mailing list.
- Packaged verify-cvs2vn script.

* Wed Feb 25 2004 David Summers <david@summersoft.fay.ar.us> 0.1-1
- First version.  This doesn't yet pass all the regression tests.

%prep
%setup -q

%if %{make_cvs2svn_check}
echo "*** Running regression tests on cvs2svn ***"

# RPM build sets LANG=C which doesn't pass the tests so (temporarily) "fix" this.
LANG=en_US.UTF-8
export LANG

make check
%endif

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/bin

make install DESTDIR=$RPM_BUILD_ROOT

# Install verify-cvs2svn.
#sed -e 's;#!/usr/bin/env python;#!/usr/bin/env python2;' < $RPM_BUILD_DIR/%{name}-%{version}/verify-cvs2svn.py > $RPM_BUILD_ROOT/usr/bin/verify-cvs2svn
#chmod a+x $RPM_BUILD_ROOT/usr/bin/verify-cvs2svn

# Check for man page (in future?)
if [ -f $RPM_BUILD_DIR/cvs2svn-%{version}/cvs2svn.1 ]; then
   cp $RPM_BUILD_DIR/cvs2svn-%{version}/cvs2svn.1 $RPM_BUILD_ROOT/usr/share/man/man1
fi


# Patch in version number to cvs2svn
sed -e "s/^VERSION = .*/VERSION = '%{version}'/" < $RPM_BUILD_ROOT/usr/bin/cvs2svn.py > $RPM_BUILD_ROOT/usr/bin/cvs2svn
rm -f $RPM_BUILD_ROOT/usr/bin/cvs2svn.py
chmod a+x $RPM_BUILD_ROOT/usr/bin/cvs2svn


%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root)
%doc BUGS COMMITTERS COPYING HACKING README
%doc design-notes.txt
/usr/bin/*
/usr/lib/python2.2/site-packages/*
