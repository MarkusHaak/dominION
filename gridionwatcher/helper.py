"""
Copyright 2018 Markus Haak (markus.haak@posteo.net)
https://github.com/MarkusHaak/GridIONwatcher

This file is part of GridIONwatcher. GridIONwatcher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version. GridIONwatcher is distributed in
the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details. You should have received a copy of the GNU General Public License along with GridIONwatcher. If
not, see <http://www.gnu.org/licenses/>.
"""

import logging
import os
import shutil
import argparse
from setuptools import Distribution
from setuptools.command.install import install
import socket

package_dir = os.path.dirname(os.path.abspath(__file__))
resources_dir = os.path.join(package_dir,'resources')
hostname = socket.gethostname()
logger_initialized = False

class ArgHelpFormatter(argparse.HelpFormatter):
	'''
	Formatter adding default values to help texts.
	'''
	def __init__(self, prog):
		super().__init__(prog)

	## https://stackoverflow.com/questions/3853722
	#def _split_lines(self, text, width):
	#	if text.startswith('R|'):
	#		return text[2:].splitlines()  
	#	# this is the RawTextHelpFormatter._split_lines
	#	return argparse.HelpFormatter._split_lines(self, text, width)

	def _get_help_string(self, action):
		text = action.help
		if 	action.default is not None and \
			action.default != argparse.SUPPRESS and \
			'default' not in text.lower():
			text += ' (default: {})'.format(action.default)
		return text

class r_file(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isfile(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a file'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class r_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class w_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class rw_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.exists(to_test):
			os.makedirs(to_test)
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		if not os.access(to_test, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))
		setattr(namespace,self.dest,to_test)

def tprint(*args, **kwargs):
	if not QUIET:
		print("["+strftime("%H:%M:%S", gmtime())+"] "+" ".join(map(str,args)), **kwargs)
	sys.stdout.flush()


# Taken from https://stackoverflow.com/questions/25066084
class OnlyGetScriptPath(install):
    def run(self):
        # does not call install.run() by design
        self.distribution.install_scripts = self.install_scripts
# Taken from https://stackoverflow.com/questions/25066084
def get_script_dir():
    dist = Distribution({'cmdclass': {'install': OnlyGetScriptPath}})
    dist.dry_run = True  # not sure if necessary, but to be safe
    dist.parse_config_files()
    command = dist.get_command_obj('install')
    command.ensure_finalized()
    command.run()
    return dist.install_scripts

def initLogger(logfile=None, level=logging.INFO):
	global logger_initialized
	if not logger_initialized:
		logger = logging.getLogger()
		formatter = logging.Formatter(fmt='%(asctime)s %(name)-10s - %(levelname)s - %(message)s',
									  datefmt='%Y-%m-%d %H:%M:%S')
		if logfile:
			fh = logging.FileHandler(logfile)
			fh.setFormatter(formatter)
		ch = logging.StreamHandler()
		ch.setFormatter(formatter)
		if logfile:
			logger.addHandler(fh)
		logger.addHandler(ch)
		logger.setLevel(level)
		logger_initialized = True

