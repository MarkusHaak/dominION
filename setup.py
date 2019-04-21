#!/usr/bin/env python3

import sys, os
from setuptools import setup
import configparser

# ensure python version 3.5 or greater is used
if (sys.version_info.major + .1 * sys.version_info.minor) < 3.5:
	print('ERROR: please execute setup.py with python version >=3.5')
	sys.exit(1)

# get version string from seperate file
# https://stackoverflow.com/questions/458550/standard-way-to-embed-version-into-python-package
# https://stackoverflow.com/questions/436198/what-is-an-alternative-to-execfile-in-python-3/437857#437857
VERSIONFILE="dominion/version.py"
with open(VERSIONFILE) as f:
	code = compile(f.read(), VERSIONFILE, 'exec')
	exec(code)
if not __version__:
	print("ERROR: unable to read version string from file {}".format(VERSIONFILE))
	exit()

DESCR = '''dominION - for monitoring, protocoling and analysis of sequencing runs performed on the ONT GridION sequencer'''

# load long description from Markdown file
with open('README.md', 'rb') as readme:
	LONG_DESCR = readme.read().decode()

# check if defaults for user, host and dest are set for file transfer
setup_dir = os.path.dirname(os.path.abspath(__file__))
config = configparser.ConfigParser(allow_no_value=True)
inifile = os.path.join(setup_dir, "dominion", "resources", "defaults.ini")
config.read(inifile)
missing_args = [arg for arg in ['user', 'host', 'dest'] if not config['DEFAULT'][arg]]
if missing_args:
	print("Apparently, not all defaults for rsync file transfer where set. Please enter the following information:")
for arg in missing_args:
	config['DEFAULT'][arg] = input("{} for rsync file transfer (as in USER@HOST:DEST): ".format(arg))
with open(inifile, 'w') as f:
	config.write(f)

setup(name='dominion',
	  version=__version__,
	  description=DESCR,
	  long_description=LONG_DESCR,
	  url='http://github.com/MarkusHaak/dominION',
	  author='Markus Haak',
	  author_email='markus.haak@posteo.net',
	  license='GPL',
	  packages=['dominion'],
	  install_requires=['watchdog', 'numpy', 'pandas', 'matplotlib'],
	  include_package_data=True,
	  zip_safe=False,
	  entry_points={"console_scripts": ['dominion = dominion.dominion:main_and_args',
	  									'statsparser = dominion.statsparser:standalone']},
	  scripts=['bin/watchnchop'])