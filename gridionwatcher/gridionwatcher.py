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

import argparse
import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
from watchdog.events import FileSystemEventHandler
#import multiprocessing as mp
from collections import OrderedDict
import re
import copy
import json
import subprocess
#import sched
import webbrowser
from shutil import copyfile
import dateutil
from datetime import datetime
from operator import itemgetter
from .version import __version__
from .statsparser import get_argument_parser as sp_get_argument_parser
from .statsparser import parse_args as sp_parse_args
from .helper import initLogger, package_dir, ArgHelpFormatter, r_file, r_dir, rw_dir, get_script_dir
import threading
import logging
import queue
from pathlib import Path

ALL_RUNS = {}
UPDATE_STATUS_PAGE = False
logger = None

class parse_statsparser_args(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test = values.split(' ')
		argument_parser = sp_get_argument_parser()
		args = sp_parse_args(argument_parser, to_test)
		setattr(namespace,self.dest,to_test)

def main_and_args():
	#### args #####
	parser = argparse.ArgumentParser(description='''A tool for monitoring and protocoling sequencing runs 
												 performed on the Oxford Nanopore Technologies GridION 
												 sequencer and for automated post processing and transmission 
												 of generated data. It collects information on QC and 
												 sequencing experiments and displays summaries of mounted 
												 flow cells as well as comprehensive reports about currently 
												 running and previously performed experiments.''',
									 formatter_class=ArgHelpFormatter, 
									 add_help=False)

	main_options = parser.add_argument_group('Main options')
	main_options.add_argument('-d', '--database_dir',
							  action=rw_dir,
							  default='reports',
							  help='Path to the base directory where experiment reports shall be saved')
	main_options.add_argument('-s', '--status_page_dir',
							  default='GridIONstatus',
							  help='''Path to the directory where all files for the GridION status page 
								   will be stored''')

	sp_options = parser.add_argument_group('Statsparser arguments',
										   'Arguments passed to statsparser for formatting html pages')
	sp_options.add_argument('--statsparser_args',
							action=parse_statsparser_args,
							default=[],
							help='''Arguments that are passed to the statsparser.
								   See a full list of possible options with --statsparser_args " -h" ''')

	io_group = parser.add_argument_group('I/O options', 
										 'Further input/output options. Only for special use cases')
	arg_basedir = \
	io_group.add_argument('-b', '--data_basedir',
						  action=rw_dir,
						  default='/data',
						  help='Path to the directory where basecalled data is saved')
	io_group.add_argument('-l', '--minknow_log_basedir',
						  action=r_dir,
						  default='/var/log/MinKNOW',
						  help='''Path to the base directory of GridIONs log files''')
	io_group.add_argument('-r', '--resources_dir',
						  action=r_dir,
						  default=os.path.join(package_dir,'resources'),
						  help='''Path to the directory containing template files and resources 
							   for the html pages (default: PACKAGE_DIR/resources)''')
	io_group.add_argument('--logfile',
						  help='''File in which logs will be safed''')

	exe_group = parser.add_argument_group('Executables paths', 
										  'Paths to mandatory executables')
	exe_group.add_argument('--watchnchop_path',
						   action=r_file,
						   default='/home/grid/scripts/watchnchop_update1.pl',
						   help='''Path to the watchnchop executable''')
	exe_group.add_argument('--statsparser_path',
						   action=r_file,
						   default=os.path.join(get_script_dir(),'statsparser'),
						   help='''Path to statsparser.py (default: PACKAGE_SCRIPT_PATH/statsparser)''')
	exe_group.add_argument('--python3_path',
						   action=r_file,
						   default=sys.executable,
						   help='''Path to the python3 executable (default: sys.executable)''')
	exe_group.add_argument('--perl_path',
						   action=r_file,
						   default='/usr/bin/perl',
						   help='''Path to the perl executable''')

	general_group = parser.add_argument_group('General options', 
											  'Advanced options influencing the program execution')
	general_group.add_argument('--bc_kws',
							   nargs='*',
							   default=['RBK', 'NBD', 'RAB', 'LWB', 'PBK', 'RPB', 'barcod', 'Barcode'],
							   help='''if at least one of these key words is a substring of the run name,
									   then watchnchop is executed with argument -b for barcode''')
	general_group.add_argument('-u', '--update_interval',
							   type=int,
							   default=300,
							   help='Time inverval (in seconds) for updating the stats webpage contents')
	general_group.add_argument('-m', '--ignore_file_modifications',
							   action='store_true',
							   help='''Ignore file modifications and only consider file creations regarding 
									determination of the latest log files''')
	general_group.add_argument('--no_watchnchop',
							   action='store_true',
							   help='''If specified, watchnchop is not executed''')

	help_group = parser.add_argument_group('Help')
	help_group.add_argument('-h', '--help', 
							action='help', 
							default=argparse.SUPPRESS,
							help='Show this help message and exit')
	help_group.add_argument('--version', 
							action='version', 
							version=__version__,
							help="Show program's version number and exit")
	help_group.add_argument('-v', '--verbose',
							action='store_true',
							help='Additional status information is printed to stdout')
	help_group.add_argument('-q', '--quiet', #TODO: implement
							action='store_true',
							help='Only error messages are printed to stdout')


	args = parser.parse_args()

	ns = argparse.Namespace()
	arg_basedir(parser, ns, args.database_dir, '') # call action

	#### main #####

	global logger
	if args.verbose:
		verbosity = logging.DEBUG
	elif args.quiet:
		verbosity = logging.WARNING
	else:
		verbosity = logging.INFO
	initLogger(logfile=args.logfile, level=verbosity)

	logger = logging.getLogger(name='gw')

	logger.info("##### starting gridIONwatcher {} #####\n".format(__version__))

	global ALL_RUNS

	logger.info("setting up GridION status page environment")
	global UPDATE_STATUS_PAGE
	if not os.path.exists(args.status_page_dir):
		os.makedirs(args.status_page_dir)
	if not os.path.exists(os.path.join(args.status_page_dir, 'res')):
		os.makedirs(os.path.join(args.status_page_dir, 'res'))
	for res_file in ['style.css', 'flowcell.png', 'no_flowcell.png']:
		copyfile(os.path.join(args.resources_dir, res_file), 
				 os.path.join(args.status_page_dir, 'res', res_file))

	logger.info("loading previous runs from database:")
	load_runs_from_database(args.database_dir)

	logger.info("starting watchers:")
	watchers = []
	for channel in range(5):
		watchers.append(Watcher(args.minknow_log_basedir, 
								channel, 
								args.ignore_file_modifications, 
								args.database_dir, 
								args.data_basedir, 
								args.statsparser_args,
								args.update_interval,
								args.no_watchnchop,
								args.resources_dir,
								args.watchnchop_path,
								args.statsparser_path,
								args.python3_path,
								args.perl_path,
								args.bc_kws))

	logger.info("initiating GridION status page")
	update_status_page(watchers, args.resources_dir, args.status_page_dir)
	webbrowser.open('file://' + os.path.realpath(os.path.join(args.status_page_dir, "GridIONstatus.html")))

	#w_fps = [[],[],[],[],[]]
	#for i,watcher in enumerate(watchers):
	#	for fn in os.listdir(watcher.observed_dir):
	#		fp = os.path.join(watcher.observed_dir, fn)
	#		if os.path.isfile(fp):
	#			if "server" in fp or "bream" in fp:
	#				w_fps[i].append(fp)
	#
	#time.sleep(0.01)
	#logger.error("attempting to restore history")
	#while len([item for sublist in w_fps for item in sublist]):
	#	for i,watcher in enumerate(watchers):
	#		if len(w_fps[i]):
	#			fp = w_fps[i].pop()
	#			watcher.logger.error("touching {}".format(fp))
	#			Path(fp).touch()
	#	time.sleep(4)
	#time.sleep(600)
	#logger.error("restoring history complete")

	logger.info("entering main loop")
	try:
		n = 0
		while True:
			for watcher in watchers:
				watcher.check_q()
			if UPDATE_STATUS_PAGE:
				update_status_page(watchers, args.resources_dir, args.status_page_dir)
				UPDATE_STATUS_PAGE = False
			time.sleep(0.25)
			n += 1
			if n == 80:
				n = 0
				UPDATE_STATUS_PAGE = True
	except KeyboardInterrupt:
	#except:
		#logger.info("### Collected information ###")
		for watcher in watchers:
			watcher.observer.stop()
			if watcher.spScheduler:
				if watcher.spScheduler.is_alive():
					watcher.spScheduler.join(timeout=0.05)
			#try:
			#	watcher.logfile.close()
			#except:
			#	logger.warning("could not close watcher's logfile")
	for watcher in watchers:
		logger.info("joining GA{}0000's observer".format(watcher.channel))
		watcher.observer.join()
		if watcher.spScheduler:
			if watcher.spScheduler.is_alive():
				logger.info("joining GA{}0000's scheduler".format(watcher.channel))
				if self.spScheduler.is_alive():
					watcher.spScheduler.join(1.2)

def load_runs_from_database(database_dir):
	for fn in os.listdir(database_dir):
		fp = os.path.join(database_dir, fn)
		if os.path.isfile(fp):
			with open(fp, "r") as f:
				try:
					flowcell, run_data, mux_scans = json.loads(f.read(), object_pairs_hook=OrderedDict)
				except:
					logger.warning("Failed to load {}, probably the json format is corrupt!".format(fn))
					continue

				asic_id_eeprom = flowcell['asic_id_eeprom']
				run_id = run_data['run_id']
				if asic_id_eeprom in ALL_RUNS:
					if run_id in ALL_RUNS[asic_id_eeprom]:
						logger.warning("{} exists multiple times in database entry for flowcell {}!".format(run_id, 
																										  asic_id_eeprom))
						logger.warning("conflicting runs: {}, {}".format(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['user_filename_input'],
																		 run_data['user_filename_input']))
						logger.warning("conflict generating report file: {}".format(fn))
						continue
				else:
					ALL_RUNS[asic_id_eeprom] = {}
				
				ALL_RUNS[asic_id_eeprom][run_id] = {'flowcell': flowcell,
												 'run_data': run_data,
												 'mux_scans': mux_scans}
				try:
					logger.info('{} - loaded experiment "{}" performed on flowcell "{}" on "{}"'.format(asic_id_eeprom, 
																								  run_data['experiment_type'], 
																								  flowcell['flowcell_id'], 
																								  run_data['protocol_start']))
				except:
					pass

def update_status_page(watchers, resources_dir, status_page_dir):
	channel_to_css = {0:"one", 1:"two", 2:"three", 3:"four", 4:"five"}

	with open(os.path.join(resources_dir, 'gridIONstatus_brick.html'), 'r') as f:
		gridIONstatus_brick = f.read()

	gridIONstatus_brick = gridIONstatus_brick.format("{0}", "{1}", __version__, "{}".format(datetime.now())[:-7])

	for watcher in watchers:
		with open(os.path.join(resources_dir, 'flowcell_brick.html'), 'r') as f:
			flowcell_brick = f.read()
		with open(os.path.join(resources_dir, 'flowcell_info_brick.html'), 'r') as f:
			flowcell_info_brick = f.read()

		latest_qc = None
		flowcell_runs = []
		asic_id_eeprom = None
		try:
			asic_id_eeprom = watcher.channel_status.flowcell['asic_id_eeprom']
		except:
			#logger.info("NO FLOWCELL")
			pass

		if asic_id_eeprom:
			if asic_id_eeprom in ALL_RUNS:
				for run_id in ALL_RUNS[asic_id_eeprom]:
					protocol_start = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_start'])
					experiment_type = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type']
					if 'seq' in experiment_type.lower(): # to increase compatibility in future
						flowcell_runs.append(run_id)
					else: # only "sequencing" and "platform_qc"
						if latest_qc:
							_protocol_start = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][latest_qc]['run_data']['protocol_start'])
							if protocol_start > _protocol_start:
								latest_qc = run_id
						else:
							latest_qc = run_id

		# FILL flowcell_brick AND flowcell_info_brick
		# case no flowcell on minion/channel:
		if not asic_id_eeprom:
			flowcell_brick = flowcell_brick.format("no_")
			flowcell_info_brick = flowcell_info_brick.format(
				channel_to_css[watcher.channel],
				"-",
				"",
				"")
		else:
			flowcell_brick = flowcell_brick.format("")
			# case flowcell new / unused
			if latest_qc == None and flowcell_runs == []:
				flowcell_info_brick = flowcell_info_brick.format(
					channel_to_css[watcher.channel],
					"NO RECORDS",
					"",
					"")
			else:
				# case only qc:
				if latest_qc and flowcell_runs == []:
					flowcell_info_brick = flowcell_info_brick.format(
						channel_to_css[watcher.channel],
						ALL_RUNS[asic_id_eeprom][latest_qc]['flowcell']['flowcell_id'],
						'<p><u>Latest QC</u> ({0}):<br><br>* : {1}<br>1 : {2}<br>2 : {3}<br>3 : {4}<br>4 : {5}</p>'.format(
							dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][latest_qc]['run_data']['protocol_start']).date(),
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group * total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 1 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 2 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 3 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 4 total']),
						""
						)
				# case only flowcell_runs:
				elif latest_qc == None and flowcell_runs:
					runs_string = '<p><u>Runs</u>:<br><br>'
					for run in flowcell_runs:
						relative_path = "NA"
						if 'relative_path' in ALL_RUNS[asic_id_eeprom][run]['run_data']:
							if ALL_RUNS[asic_id_eeprom][run]['run_data']['relative_path']:
								relative_path = ALL_RUNS[asic_id_eeprom][run]['run_data']['relative_path']
						runs_string += '<a href="{0}" target="_blank">{1}</a><br>'.format(
							os.path.join(watcher.data_basedir,relative_path,'filtered','results.html'),
							ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'])
					runs_string += '</p>'

					flowcell_info_brick = flowcell_info_brick.format(
						channel_to_css[watcher.channel],
						ALL_RUNS[asic_id_eeprom][flowcell_runs[0]]['flowcell']['flowcell_id'],
						"",
						runs_string
						)
				# case both:
				else:
					runs_string = '<p><u>Runs</u>:<br><br>'
					for run in flowcell_runs:
						relative_path = "NA"
						if 'relative_path' in ALL_RUNS[asic_id_eeprom][run]['run_data']:
							if ALL_RUNS[asic_id_eeprom][run]['run_data']['relative_path']:
								relative_path = ALL_RUNS[asic_id_eeprom][run]['run_data']['relative_path']
						runs_string += '<a href="{0}" target="_blank">{1}</a><br>'.format(
							os.path.join(watcher.data_basedir,relative_path,'filtered','results.html'),
							ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'])
					runs_string += '</p>'

					flowcell_info_brick = flowcell_info_brick.format(
						channel_to_css[watcher.channel],
						ALL_RUNS[asic_id_eeprom][latest_qc]['flowcell']['flowcell_id'],
						'<p><u>Latest QC</u> ({0}):<br><br>* : {1}<br>1 : {2}<br>2 : {3}<br>3 : {4}<br>4 : {5}</p>'.format(
							dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][latest_qc]['run_data']['protocol_start']).date(),
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group * total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 1 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 2 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 3 total'],
							ALL_RUNS[asic_id_eeprom][latest_qc]['mux_scans'][0]['group 4 total']),
						runs_string
						)

		gridIONstatus_brick =  gridIONstatus_brick.format(flowcell_brick + "\n{0}",
														  flowcell_info_brick + "\n{1}")


	gridIONstatus_brick = gridIONstatus_brick.format("", "")

	
	with open(os.path.join(resources_dir, 'gridIONstatus_bottom_brick.html'), 'r') as f:
		bottom_brick = f.read()

	blank_line = '<tr>\n<th><a href="{}" target="_blank">{}</a></th>\n<td>{}</td>\n<td>{}</td>\n<td>{}</td>\n<td>{}</td></tr>'

	all_runs_info = []
	for asic_id_eeprom in ALL_RUNS:
		for run_id in ALL_RUNS[asic_id_eeprom]:
			experiment_type = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type']
			if 'seq' in experiment_type.lower(): # to increase compatibility in future
				protocol_start = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_start'])
				time_diff = "N/A"
				if 'protocol_end' in ALL_RUNS[asic_id_eeprom][run_id]['run_data']:
					if ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_end']:
						protocol_end = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_end'])
						#time_diff = "{}".format(protocol_end - protocol_start)[:-7]
						time_diff = "{}".format(protocol_end - protocol_start).split('.')[0]
				#protocol_start = "{}".format(protocol_start)[:-7]
				protocol_start = "{}".format(protocol_start).split('.')[0]
				sequencing_kit = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['sequencing_kit']
				user_filename_input = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['user_filename_input']
				minion_id = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['minion_id']
				#link = os.path.join(watchers[0].data_basedir, 
				#					user_filename_input,
				#					minion_id,
				#					'filtered',
				#					'results.html')
				relative_path = "NA"
				if 'relative_path' in ALL_RUNS[asic_id_eeprom][run_id]['run_data']:
					if ALL_RUNS[asic_id_eeprom][run_id]['run_data']['relative_path']:
						relative_path = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['relative_path']
				link = os.path.join(watchers[0].data_basedir,
									relative_path,
									'filtered',
									'results.html')
				all_runs_info.append( (link, user_filename_input, minion_id, sequencing_kit, protocol_start, time_diff) )

	all_runs_info = sorted(all_runs_info, key=itemgetter(1), reverse=True)

	for run_info in all_runs_info:
		bottom_brick = bottom_brick.format(blank_line.format(run_info[0], 
															 run_info[1], 
															 run_info[2], 
															 run_info[3], 
															 run_info[4], 
															 run_info[5]) + "\n{0}")
	bottom_brick = bottom_brick.format("")

	with open(os.path.join(status_page_dir, 'GridIONstatus.html'), 'w') as f:
		print(gridIONstatus_brick + bottom_brick, file=f)


class ChannelStatus():
	empty_run_data = OrderedDict([
		('run_id', None),
		('user_filename_input', None), # user Run title
		('minion_id', None),
		('sequencing_kit', None),
		('protocol_start', None),
		('protocol_end', None),
		('relative_path', None)
		])

	empty_flowcell = OrderedDict([
		('flowcell_id', None),
		('asic_id', None),
		('asic_id_eeprom', None),
		('flowcell', None)
		])

	empty_mux = OrderedDict()

	def __init__(self, minion_id, channel):
		self.minion_id = minion_id
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.mux_scans = []
		self.run_data['minion_id'] = minion_id
		self.logger = logging.getLogger(name='gw.w{}.cs'.format(channel+1))

	def update(self, content, overwrite=False):
		for key in content:
			if key in self.flowcell:
				if self.flowcell[key]:
					if overwrite:
						self.logger.info("changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
						self.flowcell[key] = content[key]
					else:
						self.logger.debug("not changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
					continue
				else:
					self.flowcell[key] = content[key]
					self.logger.info("new flowcell value for {} : {}".format(key, content[key]))
					continue
			elif key in self.run_data:
				if self.run_data[key]:
					if overwrite:
						self.logger.info("changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
						self.run_data[key] = content[key]
					else:
						self.logger.debug("not changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
					continue
			self.run_data[key] = content[key]
			self.logger.info("new run value for {} : {}".format(key, content[key]))

	def update_mux(self, group, channels, mux, timestamp):
		if self.mux_scans:
			if not group in self.mux_scans[-1]:
				self.mux_scans[-1][group] = []
			if len(self.mux_scans[-1][group]) < 4:
				self.mux_scans[-1][group].append(int(channels))
				self.logger.debug("update mux: group {} has {} active channels in mux {}".format(group, channels, mux))

	def update_mux_group_totals(self, group, channels, timestamp):
		if not self.mux_scans:
			self.new_mux(timestamp)
		self.mux_scans[-1]['group {} total'.format(group)] = channels
		self.logger.debug("update mux group totals: group {} has a total of {} active channels".format(group, channels))

	def new_mux(self, timestamp):
		if self.mux_scans:
			self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234" if i in self.mux_scans[-1]])
			self.logger.info("calculated mux total to {}".format(self.mux_scans[-1]['total']))
		self.mux_scans.append(copy.deepcopy(self.empty_mux))
		self.mux_scans[-1]['timestamp'] = timestamp
		self.logger.debug("added new mux result")

	def flowcell_disconnected(self):
		self.logger.info("executing FLOWCELL DISCONNECTED")
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []

	def run_finished(self):
		self.logger.info("executing RUN FINISHED")
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []

	def find_relative_path(self, data_basedir):
		if not self.run_data['user_filename_input']:
			self.logger.error("Could not determine relative data path, 'user_filename_input' is not set")
			return
		rel_path = os.path.join(self.run_data['user_filename_input'],
								self.run_data['user_filename_input'])	# TODO: change to sample_name
		basedir = os.path.join(data_basedir, rel_path)	
		if not os.path.isdir(basedir):
			self.logger.error("Could not determine relative data path, base directory {} does not exist!".format(basedir))
			return

		if self.run_data['run_id']:
			exp_id_substring = self.run_data['run_id'].split('-')[0]
		else:
			self.logger.warning("'run_id' is not set, therefore relative_path has to be guessed!")
			exp_id_substring = None
		
		sub_dirs = [item for item in os.listdir(basedir) if os.path.isdir(os.path.join(basedir, item))]
		if not sub_dirs:
			self.logger.error("Could not determine relative data path, no sub directories in {}".format(basedir))
			return
		if exp_id_substring:
			for sub_dir in sub_dirs:
				if sub_dir.rstrip('/').endswith(exp_id_substring):
					self.update({"relative_path":os.path.join(rel_path, sub_dir)}, overwrite=True)
					return
		# if no relative path was found by now, then it is probably the case that the run_id was not parsed correctly
		# --> attempt to choose a subdirectory which belongs to the correct flowcell
		if self.flowcell['flowcell_id']:
			for sub_dir in sub_dirs:
				if self.flowcell['flowcell_id'] in sub_dir:
					self.update({"relative_path":os.path.join(rel_path, sub_dir)}, overwrite=True)
					self.logger.warning("chose any sub directory that belongs to flowcell {}!".format(self.flowcell['flowcell_id']))
					return
		self.logger.error("Could not determine any relative data path!")
		return


class WatchnchopScheduler(threading.Thread):

	def __init__(self, perl_path, watchnchop_path, data_basedir, relative_path, user_filename_input, bc_kws, channel):
		threading.Thread.__init__(self)
		if getattr(self, 'daemon', None) is None:
			self.daemon = True
		else:
			self.setDaemon(True)
		self.stoprequest = threading.Event()
		self.logger = logging.getLogger(name='gw.w{}.wcs'.format(channel+1))

		self.observed_dir = os.path.join(data_basedir, relative_path, 'fastq_pass')
		# define the command that is to be executed
		self.cmd = [perl_path,
					watchnchop_path,
					'-v']
		if len([kw for kw in bc_kws if kw in user_filename_input]) > 0:
			self.cmd.append('-b')
		self.cmd.append(os.path.join(data_basedir, relative_path, ''))
		self.cmd = " ".join(self.cmd)

	def run(self):
		while not self.stoprequest.is_set():
			if os.path.exists(self.observed_dir):
				if [fn for fn in os.listdir(self.observed_dir) if fn.endswith('.fastq')]:
					try:
						subprocess.Popen(self.cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
					except:
						self.logger.error("FAILED to start watchnchop, Popen failed")
						return
					self.logger.info("STARTED WATCHNCHOP with arguments: {}".format(self.cmd))
					return
			time.sleep(1)

	def join(self, timeout=None):
		self.stoprequest.set()
		super(WatchnchopScheduler, self).join(timeout)


class StatsparserScheduler(threading.Thread):

	def __init__(self, update_interval, statsfp, statsparser_args, 
				 user_filename_input, minion_id, flowcell_id, protocol_start,
				 resources_dir, statsparser_path, python3_path, channel):
		threading.Thread.__init__(self)
		if getattr(self, 'daemon', None) is None:
			self.daemon = True
		else:
			self.setDaemon(True)
		self.stoprequest = threading.Event()
		self.logger = logging.getLogger(name='gw.w{}.sps'.format(channel+1))

		self.update_interval = update_interval
		self.resources_dir = resources_dir
		self.statsfp = statsfp
		self.statsparser_path = statsparser_path
		self.statsparser_args = statsparser_args
		self.user_filename_input = user_filename_input
		self.minion_id = minion_id
		self.flowcell_id = flowcell_id
		self.protocol_start = protocol_start
		self.python3_path = python3_path
		

	def run(self):
		page_opened = False
		while not self.stoprequest.is_set():
			last_time = time.time()
			self.logger.info("STARTING STATSPARSING")

			if os.path.exists(self.statsfp):
				cmd = [self.statsparser_path, self.statsfp,
					   '--user_filename_input', self.user_filename_input,
					   '--minion_id', self.minion_id,
					   '--flowcell_id', self.flowcell_id,
					   '--protocol_start', self.protocol_start,
					   '--resources_dir', self.resources_dir,
					   '-q']
				cmd.extend(self.statsparser_args)
				cp = subprocess.run(cmd) # waits for process to complete
				if cp.returncode == 0:
					self.logger.info("STATSPARSING COMPLETED")
					if not page_opened:
						basedir = os.path.abspath(os.path.dirname(self.statsfp))
						fp = os.path.join(basedir, 'results.html')
						self.logger.info("OPENING " + fp)
						page_opened = webbrowser.open('file://' + os.path.realpath(fp))
				else:
					self.logger.error("ERROR while running statsparser")
			else:
				self.logger.warning("statsfile does not exist (yet?)")

			this_time = time.time()
			while (this_time - last_time < self.update_interval) and not self.stoprequest.is_set():
				time.sleep(1)
				this_time = time.time()

	def join(self, timeout=None):
		self.stoprequest.set()
		super(StatsparserScheduler, self).join(timeout)


class Watcher():

	def __init__(self, minknow_log_basedir, channel, ignore_file_modifications, database_dir, 
				 data_basedir, statsparser_args, update_interval, no_watchnchop,
				 resources_dir, watchnchop_path, statsparser_path, python3_path, perl_path, bc_kws):
		#self.q = queue.SimpleQueue()
		self.q = queue.PriorityQueue()
		self.watchnchop = not no_watchnchop
		self.channel = channel
		self.database_dir = database_dir
		self.data_basedir = data_basedir
		self.statsparser_args = statsparser_args
		self.update_interval = update_interval
		self.resources_dir = resources_dir
		self.watchnchop_path = watchnchop_path
		self.statsparser_path = statsparser_path
		self.python3_path = python3_path
		self.perl_path = perl_path
		self.observed_dir = os.path.join(minknow_log_basedir, "GA{}0000".format(channel+1))
		self.event_handler = LogFilesEventHandler(self.q, ignore_file_modifications, channel)
		self.observer = Observer()
		self.bc_kws = bc_kws

		self.observer.schedule(self.event_handler, 
							   self.observed_dir, 
							   recursive=False)
		self.observer.start()
		#self.logfile = open(os.path.join(os.path.abspath(os.path.dirname(self.watchnchop_path)),
		#								 "GA{}0000_watchnchop_log.txt".format(channel+1)), 'w')
		self.channel_status = ChannelStatus("GA{}0000".format(channel+1), channel)
		self.spScheduler = None
		self.wcScheduler = None
		self.logger = logging.getLogger(name='gw.w{}'.format(channel+1))

		self.logger.info("...watcher for {} ready".format(self.observed_dir))

	def check_q(self):
		# checking sheduler queue
		if not self.q.empty():
			self.logger.debug("Queue content for {}:".format(self.observed_dir))
		while not self.q.empty():
			timestamp, origin, line = self.q.get()
			self.logger.debug("received '{}' originating from '{} log' at '{}'".format(line, origin, timestamp))

			if origin == 'server':
				self.parse_server_log_line(line)
			elif origin == 'bream':
				self.parse_bream_log_line(line)

	def parse_server_log_line(self, line):
		global UPDATE_STATUS_PAGE
		dict_content = {}
		overwrite = False

		if   	"protocol_started"										in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True
			self.logger.info("PROTOCOL START")
			UPDATE_STATUS_PAGE = True
			self.channel_status.run_data['protocol_start'] = line[:23]

		elif	"protocol_finished" 									in line:
			self.logger.info("PROTOCOL END")
			UPDATE_STATUS_PAGE = True
			self.channel_status.run_data['protocol_end'] = line[:23]
			if self.channel_status.mux_scans:
				self.save_report()
			self.channel_status.run_finished()
			if self.spScheduler:
				if self.spScheduler.is_alive():
					self.spScheduler.join(1.2)
			self.spScheduler = None

		elif	"[engine/info]: : flowcell_discovered" 					in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True
			self.logger.info("FLOWCELL DISCOVERED")
			UPDATE_STATUS_PAGE = True
			self.channel_status.flowcell_disconnected()
			if self.spScheduler:
				if self.spScheduler.is_alive():
					self.spScheduler.join(1.2)
			self.spScheduler = None

		elif   	"[engine/info]: : data_acquisition_started"				in line:# or \
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True

		elif	"flowcell_disconnected"									in line:
			self.logger.info("FLOWCELL DISCONNECTED")
			UPDATE_STATUS_PAGE = True
			self.channel_status.flowcell_disconnected()


		if dict_content:
			self.channel_status.update(dict_content, overwrite)

	def parse_bream_log_line(self, line):
		global UPDATE_STATUS_PAGE
		dict_content = {}
		overwrite = False

		if 		"root - INFO - argument"								in line:
			for m in re.finditer("([^\s,]+) was set to (.+)", line): 
				dict_content[m.group(1)] = m.group(2)

		elif 	"INFO - Adding the following context_tags:" 			in line or \
				"INFO - Context tags set to"							in line:
			for m in re.finditer("'([^\s,]+)'[:,] u?'([^\s,]+)'", line):
				dict_content[m.group(1)] = m.group(2)
			if 'filename' in dict_content:
				dict_content['flowcell_id'] = dict_content['filename'].split("_")[2]

		elif	"bream.core.base.database - INFO - group"				in line:
			for m in re.finditer("group ([0-9]+) has ([0-9]+) channels in mux ([0-9]+)", line):
				self.channel_status.update_mux(m.group(1), m.group(2), m.group(3), line[:23])
				UPDATE_STATUS_PAGE = True

		elif	"[user message]--> group "								in line.lower():
			for m in re.finditer("roup ([0-9]+) has ([0-9]+) active", line):
				self.channel_status.update_mux_group_totals(m.group(1), m.group(2), line[:23])
				UPDATE_STATUS_PAGE = True

		elif	"[user message]--> A total of"							in line:
			for m in re.finditer("total of ([0-9]+) single pores", line):
				self.channel_status.update_mux_group_totals("*", m.group(1), line[:23])
				UPDATE_STATUS_PAGE = True

		elif	"INFO - [user message]--> Finished Mux Scan"			in line:
			self.logger.info("MUX SCAN FINISHED")
			UPDATE_STATUS_PAGE = True
			self.channel_status.new_mux(line[:23])
			self.save_report()

		elif	"platform_qc.PlatformQCExperiment'> finished"			in line:
			self.logger.info("QC FINISHED")
			UPDATE_STATUS_PAGE = True

		elif	"INFO - STARTING MAIN LOOP"								in line:
			dict_content["sequencing_start_time"] = line[:23]
			self.logger.info("SEQUENCING STARTS")
			UPDATE_STATUS_PAGE = True

			#try to identify the path in which the experiment data is saved, relative to data_basedir
			self.channel_status.find_relative_path(self.data_basedir)
			if self.channel_status.run_data['relative_path'] and False:
				#start watchnchop (porechop & filter & rsync)
				if self.watchnchop:
					self.start_watchnchop()

				#start creation of plots at regular time intervals
				if self.spScheduler:
					if self.spScheduler.is_alive():
						self.spScheduler.join(1.1)
				
				relative_path = self.channel_status.run_data['relative_path']
				statsfp = os.path.join(self.data_basedir,
									   relative_path,
									   'filtered',
									   'stats.txt')
				self.logger.info('SCHEDULING update of stats-webpage every {0:.1f} minutes for stats file '.format(self.update_interval/1000) + statsfp)
				self.spScheduler = StatsparserScheduler(self.update_interval, 
														statsfp, 
														self.statsparser_args, 
														self.channel_status.run_data['user_filename_input'], 
														"GA{}0000".format(self.channel+1), 
														self.channel_status.flowcell['flowcell_id'], 
														self.channel_status.run_data['protocol_start'],
														self.resources_dir,
														self.statsparser_path,
														self.python3_path,
														self.channel)
				self.spScheduler.start()
			else:
				self.logger.warning("not started watchnchop and statsparser because relative path unknown")

		if dict_content:
			self.channel_status.update(dict_content, overwrite)

	def save_report(self):
		for key in ['experiment_type', 'run_id']:
			if not self.channel_status.run_data[key]:
				self.logger.warning("NOT SAVING REPORT for channel GA{}0000 because run_data is missing crucial attribute '{}'".format(self.channel+1, key))
				return
		for key in ['flowcell_id', 'asic_id_eeprom']:
			if not self.channel_status.flowcell[key]:
				self.logger.warning("NOT SAVING REPORT for channel GA{}0000 because flowcell is missing crucial attribute '{}'".format(self.channel+1, key))
				return

		fn = []
		if "qc" in self.channel_status.run_data['experiment_type']:
			if self.channel_status.run_data['user_filename_input']:
				self.logger.warning("NOT SAVING REPORT for {} because it is not absolutely clear if it a qc or sequencing run".format(self.channel_status.run_data['run_id']))
				return
			fn.append("QC")
		else:
			if not self.channel_status.run_data['user_filename_input']:
				self.logger.warning("NOT SAVING REPORT because sequencing run is missing crucial attribute 'user_filename_input'")
				return
			fn.append(self.channel_status.run_data['user_filename_input'])
		fn.append(self.channel_status.flowcell['flowcell_id'])
		fn.append(self.channel_status.run_data['run_id'])
		fn = "_".join(fn) + ".txt"

		data = (self.channel_status.flowcell, self.channel_status.run_data, self.channel_status.mux_scans)
		with open( os.path.join(self.database_dir, fn), 'w') as f:
			print(json.dumps(data, indent=4), file=f)

		run_id = self.channel_status.run_data['run_id']
		asic_id_eeprom = self.channel_status.flowcell['asic_id_eeprom']
		if asic_id_eeprom in ALL_RUNS:
			ALL_RUNS[asic_id_eeprom][run_id] = {'flowcell': data[0],
											 'run_data': data[1],
											 'mux_scans': data[2]}
		else:
			ALL_RUNS[asic_id_eeprom] = {}
			ALL_RUNS[asic_id_eeprom][run_id] = {'flowcell': data[0],
											 'run_data': data[1],
											 'mux_scans': data[2]}

	def start_watchnchop(self):
		for key in ['user_filename_input', 'relative_path']:
			if not self.channel_status.run_data[key]:
				self.logger.warning("NOT executing watchnchop for channel GA{}0000 because run_data is missing crucial attribute '{}'".format(self.channel+1, key))
				return

		if self.wcScheduler:
			if self.wcScheduler.is_alive():
				self.logger.error("watchnchop was not started successfully for previous run!")
				self.wcScheduler.join(1.2)

		self.wcScheduler = WatchnchopScheduler(self.perl_path,
											   self.watchnchop_path,
											   self.data_basedir,
											   self.channel_status.run_data['relative_path'],
											   self.channel_status.run_data['user_filename_input'],
											   self.bc_kws,
											   self.channel)
		self.wcScheduler.start()
		return


class OpenedFilesHandler():
	'''manages a set of opened files, reads their contents and 
	processes them line by line. Incomplete lines are stored until
	they are "completed" by a newline character.'''
	def __init__(self, channel):
		self.logger = logging.getLogger(name='gw.w{}.ofh'.format(channel+1))
		self.open_files = {}

	def open_new_file(self, path):
		self.logger.info("Opening file {}".format(path))
		self.open_files[path] = [open(path, 'r'), ""]

	def close_file(self, path):
		self.logger.debug("Attempting to close file {}".format(path))
		try:
			self.open_files[path][0].close()
		except:
			self.logger.debug("File handle of file {} couldn't be closed".format(path))
		if path in self.open_files:
			del self.open_files[path]
			self.logger.debug("Deleted entry in open_files for file {}".format(path))

	def process_lines_until_EOF(self, process_function, path):
		file = self.open_files[path][0]
		while 1:
			line = file.readline()
			if line == "":
				break
			elif line.endswith("\n"):
				line = (self.open_files[path][1] + line).strip()
				if line:
					#parent.process(line)
					process_function(line)
				self.open_files[path][1] = ""
			else:
				#line potentially incomplete
				self.open_files[path][1] = self.open_files[path][1] + line


class LogFilesEventHandler(FileSystemEventHandler):
	control_server_log = None
	bream_log = None

	def __init__(self, q, ignore_file_modifications, channel):
		super(LogFilesEventHandler, self).__init__()
		self.ignore_file_modifications = ignore_file_modifications
		self.file_handler = OpenedFilesHandler(channel)
		self.comm_q = q

		# while no server log file is opened, all lines read are buffered in a seperate Priority Queue
		self.buff_q = queue.PriorityQueue()
		self.q = self.buff_q
		self.logger = logging.getLogger(name='gw.w{}.lfeh'.format(channel+1))

	def on_moved(self, event):
		pass

	def on_created(self, event):
		if not event.is_directory:
			activate_q = False
			self.logger.debug("File {} was created".format(event.src_path))
			basename = os.path.basename(event.src_path)
			if basename.startswith("control_server_log"):
				if self.control_server_log:
					self.file_handler.close_file(event.src_path)
					self.logger.info("Replacing current control_server_log file {} with {}".format(self.control_server_log, event.src_path))
				else:
					# read lines of server file first, then activate the real communication q
					activate_q = True
				self.control_server_log = event.src_path
				self.logger.info("New control_server_log file {}".format(self.control_server_log))
				process_function = self.enqueue_server_log_line
			elif basename.startswith("bream"):
				if self.bream_log:
					self.file_handler.close_file(event.src_path)
					self.logger.info("Replacing current bream_log file {} with {}".format(self.bream_log, event.src_path))
					#TODO: Find out if more than one bream log file can belong to a running experiment (probably not)
				self.bream_log = event.src_path
				self.logger.info("New bream_log file {}".format(self.bream_log))
				process_function = self.enqueue_bream_log_line
				self.logger.info("NEW EXPERIMENT")
			else:
				self.logger.debug("File {} is not of concern for this tool".format(event.src_path))
				return
			self.file_handler.open_new_file(event.src_path)
			self.file_handler.process_lines_until_EOF(process_function, event.src_path)
			self.logger.info("approx. queue size: {}".format(self.q.qsize()))
			if activate_q:
				self.activate_q()

	def activate_q(self):
		self.logger.info("activating communication queue")
		self.q = self.comm_q
		while not self.buff_q.empty():
			self.q.put(self.buff_q.get())

	def on_deleted(self, event):
		if not event.is_directory:
			self.logger.debug("File {} was deleted".format(event.src_path))
			#self.file_handler.close_file(event.src_path)
			if self.control_server_log == event.src_path:
				control_server_log = None
				self.logger.warning("Current control_server_log file {} was deleted!".format(event.src_path))
			elif self.bream_log == event.src_path:
				self.bream_log = None
				self.logger.info("EARNING: Current bream_log file {} was deleted".format(event.src_path))
			else:
				self.logger.debug("File {} is not opened and is therefore not closed.".format(event.src_path))
				#return 
			self.file_handler.close_file(event.src_path)

	def on_modified(self, event):
		if not event.is_directory:
			self.logger.debug("File {} was modified".format(event.src_path))
			if event.src_path in self.file_handler.open_files:
				if self.control_server_log == event.src_path:
					self.file_handler.process_lines_until_EOF(self.enqueue_server_log_line, event.src_path)
				elif self.bream_log == event.src_path:
					self.file_handler.process_lines_until_EOF(self.enqueue_bream_log_line, event.src_path)
				else:
					self.logger.warning("case not handled")
					return
			else:
				if not self.ignore_file_modifications:
					self.on_created(event)
				else:
					self.logger.debug("File {} existed before this script was started".format(event.src_path))

	def enqueue_server_log_line(self, line):
		try:
			self.q.put( (dateutil.parser.parse(line[:23]), 'server', line) )
		except ValueError:
			self.logger.debug("the timestamp of the following line in the server log file could not be parsed:\n{}".format(line))

	def enqueue_bream_log_line(self, line):
		try:
			self.q.put( (dateutil.parser.parse(line[:23]), 'bream', line) )
		except ValueError:
			self.logger.debug("the timestamp of the following line in the bream log file could not be parsed:\n{}".format(line))

if __name__ == "__main__":
	main_and_args()
