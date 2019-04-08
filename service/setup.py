#!/usr/bin/env python

import glob
import distutils.log

from distutils.core import setup
from distutils.command.install import install
from errno import EEXIST
from storage_service import __version__, __ConfDir__, __ConfFile__, __LogConfFile__, __ScriptDir__, __PidDir__

NAME = 'storage_service'
wrapper_script = 'storage_serviced'
default_log_directory = '/var/log/storage_service'

setup(name = NAME,
      version = __version__,
      packages = [NAME],
      scripts = [wrapper_script],
      data_files = [(__ConfDir__, [__ConfFile__, __LogConfFile__]),
                    (__ScriptDir__, glob.glob('./scripts/*')),
                    (__PidDir__, []),
                    (default_log_directory, [])]
)
