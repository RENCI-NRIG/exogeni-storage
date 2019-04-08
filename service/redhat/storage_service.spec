%if ! (0%{?fedora} > 12 || 0%{?rhel} > 5)
%{!?python_sitearch: %global python_sitearch %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}
%endif

Name:           storage_service
Version:        1.4
Release:        1
Summary:        A daemon implementing an authenticated XMLRPC interface for provisioning storage.

Group:          Applications/System
License:        BSD
URL:            https://bitbucket.org/dromao/exogeni-storage/overview
Source:         %{name}-%{version}.tgz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root

BuildRequires: python-virtualenv python-pip python-setuptools gcc
Requires: httpd-tools
Requires(post): /sbin/chkconfig
Requires(preun): /sbin/chkconfig /sbin/service

%define venv_base_dir /opt
%define venv_name storage_service
%define venv_dir %{venv_base_dir}/%{venv_name}

# Disable debuginfo packaging...
%global debug_package %{nil}

%description
storage_service provides an authenticated XMLRPC interface for provisioning storage.
Currently, only iSCSI LUNs are provisionable, but a generic interface for both file and block based storage provisioning is envisioned.

%prep
%setup -q

%build
if [ -d %{_builddir}%{venv_dir} ]; then
    echo "Cleaning out stale build directory" 1>&2
    rm -rf %{_builddir}%{venv_dir}
fi
mkdir -p %{_builddir}%{venv_dir}
virtualenv %{_builddir}%{venv_dir}
%{_builddir}%{venv_dir}/bin/pip install greenlet==0.4.7
%{_builddir}%{venv_dir}/bin/pip install gevent==1.0.2
%{_builddir}%{venv_dir}/bin/pip install futures==3.0.3
%{_builddir}%{venv_dir}/bin/pip install lockfile==0.8
%{_builddir}%{venv_dir}/bin/pip install python-daemon==1.5.5
%{_builddir}%{venv_dir}/bin/pip install passlib==1.6.5
%{_builddir}%{venv_dir}/bin/pip install setproctitle==1.1.9
%{_builddir}%{venv_dir}/bin/python setup.py build
%{_builddir}%{venv_dir}/bin/python setup.py install_lib
%{_builddir}%{venv_dir}/bin/python setup.py install_scripts
# And make the virtualenv relocatable.
virtualenv --relocatable %{_builddir}%{venv_dir}
echo "FIXING virtualenv PATHS"
find -H %{_builddir}%{venv_dir}/bin -type f | while read filename;
do
     perl -p -i.bak -e "s|%{_builddir}||g" ${filename}
     if [ -f ${filename}.bak ]; then
        rm -f ${filename}.bak
        echo "FIXED ${filename}"
     fi
done

%install
mkdir -p %{buildroot}%{venv_base_dir}
cp -R %{_builddir}%{venv_dir} %{buildroot}%{venv_base_dir}
%{buildroot}%{venv_dir}/bin/python setup.py install_data --root %{buildroot}
install -p -D -m 755 redhat/storage_service.init %{buildroot}/%{_initrddir}/storage_service
chmod +x %{buildroot}/%{_datarootdir}/storage_service/scripts/*.sh

# Correct the virtualenv lib64 symlink to what it will point to on a real install:
rm %{buildroot}%{venv_dir}/lib64
ln -s %{venv_dir}/lib %{buildroot}%{venv_dir}/lib64

# This avoids prelink & RPM helpfully breaking the package signatures:
/usr/sbin/prelink -u %{buildroot}%{venv_dir}/bin/python

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%attr(755, root, root) %dir %{_sysconfdir}/storage_service
%attr(755, root, root) %dir %{_datarootdir}/storage_service
%attr(755, root, root) %dir %{_localstatedir}/log/storage_service
%config(noreplace) %{_sysconfdir}/storage_service/config
%config(noreplace) %{_sysconfdir}/storage_service/logging.config
%{_initddir}/storage_service
%{_datarootdir}/storage_service/scripts
%{venv_dir}
%exclude %{venv_dir}/lib/python2.6/*.pyc
%verify(not md5 size mtime) %{venv_dir}/lib/python2.6/*.pyc

%post
if [ "$1" = "1" ]; then
    /sbin/chkconfig --add storage_service >/dev/null 2>&1 ||:
fi

%preun
if [ "$1" = "0" ]; then
    /sbin/chkconfig --del storage_service >/dev/null 2>&1 ||:
    /etc/rc.d/init.d/storage_service stop
fi

%changelog
* Wed Aug 19 2015 Victor J. Orlikowski <vjo@duke.edu> - 1.4-1
- 1.4 New release, with operation timeouts.

* Mon Aug 17 2015 Victor J. Orlikowski <vjo@duke.edu> - 1.3-1
- 1.3 Making up for the brown paper bag release. Using new gevent, after wrappering everything into a virtualenv.

* Mon Aug 17 2015 Victor J. Orlikowski <vjo@duke.edu> - 1.2-1
- 1.2 Brown paper bag release. Gevent version shipped in RHEL 6 does not monkey patch subprocess.

* Sun Aug 16 2015 Victor J. Orlikowski <vjo@duke.edu> - 1.1-1
- 1.1 Using gevent, in order to decrease memory burden.

* Mon Feb 09 2015 Victor J. Orlikowski <vjo@duke.edu> - 1.0-1
- 1.0 Initial packaging of storage_service.
