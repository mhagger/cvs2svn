%define make_cvs2svn_check 1
Summary: Convert CVS repositories to Subversion repositories.
Name: cvs2svn
Version: 0.1
Release: 1
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
* Wed Feb 25 2004 David Summers <david@summersoft.fay.ar.us> 0.1-1
- First version.

%prep
%setup -q

%if %{make_cvs2svn_check}
echo "*** Running regression tests on cvs2svn ***"
./run-tests.py
%endif

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/bin

sed -e 's;#!/usr/bin/env python;#!/usr/bin/env python2;' < $RPM_BUILD_DIR/%{name}-%{version}/cvs2svn.py > $RPM_BUILD_ROOT/usr/bin/cvs2svn
chmod a+x $RPM_BUILD_ROOT/usr/bin/cvs2svn
mkdir -p $RPM_BUILD_ROOT/usr/lib/python2.2/site-packages
cp -r rcsparse $RPM_BUILD_ROOT/usr/lib/python2.2/site-packages/rcsparse
if [ -f $RPM_BUILD_DIR/cvs2svn-%{version}/cvs2svn.1 ]; then
   cp $RPM_BUILD_DIR/cvs2svn-%{version}/cvs2svn.1 $RPM_BUILD_ROOT/usr/share/man/man1
fi

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root)
%doc BUGS COMMITTERS COPYING HACKING README
/usr/bin/cvs2svn
/usr/lib/python2.2/site-packages/*
