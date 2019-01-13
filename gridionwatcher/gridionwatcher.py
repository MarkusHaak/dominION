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
import multiprocessing as mp
from collections import OrderedDict
import re
import copy
import json
import subprocess
import sched
import webbrowser
from shutil import copyfile
import dateutil
from datetime import datetime
from operator import itemgetter
from .version import __version__
from .statsparser import get_argument_parser as sp_get_argument_parser
from .statsparser import parse_args as sp_parse_args
from .helper import logger, package_dir, ArgHelpFormatter, r_file, r_dir, rw_dir
#import logging

VERBOSE = False
QUIET = False
ALL_RUNS = {}
UPDATE_STATUS_PAGE = False

class parse_statsparser_args(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test = values.split(' ')
		argument_parser = sp_get_argument_parser()
		args = sp_parse_args(argument_parser, to_test)
		print (to_test)
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
	main_options.add_argument('--status_page_dir',
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
	a_d = \
	io_group.add_argument('-b', '--basecalled_basedir',
						  action=rw_dir,
						  default='/data/basecalled',
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

	exe_group = parser.add_argument_group('Executables paths', 
										  'Paths to mandatory executables')
	exe_group.add_argument('--watchnchop_path',
						   action=r_file,
						   default='watchnchop.pl',
						   help='''Path to the watchnchop executable''')
	exe_group.add_argument('--statsparser_path',
						   action=r_file,
						   default=os.path.join(package_dir,'statsparser.py'),
						   help='''Path to statsparser.py (default: PACKAGE_DIR/statsparser.py)''')
	exe_group.add_argument('--python3_path',
						   action=r_file,
						   default='/usr/bin/python3',
						   help='''Path to the python3 executable''')
	exe_group.add_argument('--perl_path',
						   action=r_file,
						   default='/usr/bin/perl',
						   help='''Path to the perl executable''')

	general_group = parser.add_argument_group('General options', 
											   'Advanced options influencing the program execution')
	general_group.add_argument('-u', '--update_interval',
							   type=int,
							   default=600,
							   help='Time inverval (in seconds) for updating the stats webpage contents')
	general_group.add_argument('-m', '--ignore_file_modifications',
							   action='store_false',
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
							help='No prints to stdout')


	args = parser.parse_args()

	ns = argparse.Namespace()
	a_d(parser, ns, args.database_dir, 'no string') # call action

	global QUIET
	QUIET = args.quiet
	global VERBOSE
	VERBOSE = args.verbose

	#### main #####

	if not QUIET: print("#######################################")
	if not QUIET: print("######### grinIONwatcher {} #########".format(__version__))
	if not QUIET: print("#######################################")
	if not QUIET: print("")
	sys.stdout.flush()

	global ALL_RUNS

	logger.info("setting up GrinIOn status page environment")
	global UPDATE_STATUS_PAGE
	if not os.path.exists(args.status_page_dir):
		os.makedirs(args.status_page_dir)
	if not os.path.exists(os.path.join(args.status_page_dir, 'res')):
		os.makedirs(os.path.join(args.status_page_dir, 'res'))
	copyfile(os.path.join(args.resources_dir, 'style.css'), 
			 os.path.join(args.status_page_dir, 'res', 'style.css'))
	copyfile(os.path.join(args.resources_dir, 'flowcell.png'), 
			 os.path.join(args.status_page_dir, 'res', 'flowcell.png'))
	copyfile(os.path.join(args.resources_dir, 'no_flowcell.png'), 
			 os.path.join(args.status_page_dir, 'res', 'no_flowcell.png'))


	logger.info("loading previous runs from database:")
	load_runs_from_database(args.database_dir)
	print()
	sys.stdout.flush()

	logger.info("starting watchers:")
	watchers = []
	for channel in range(5):
		watchers.append(Watcher(args.minknow_log_basedir, 
								channel, 
								args.modified_as_created, 
								args.database_dir, 
								args.basecalled_basedir, 
								args.statsparser_args,
								args.update_interval,
								args.no_watchnchop,
								args.resources_dir,
								args.watchnchop_path,
								args.statsparser_path,
								args.python3_path,
								args.perl_path))
	print()
	sys.stdout.flush()

	logger.info("Initiating GrinIOn status page")
	update_status_page(watchers, args.resources_dir, args.status_page_dir)
	webbrowser.open('file://' + os.path.realpath(os.path.join(args.status_page_dir, "GridIONstatus.html")))

	logger.info("entering main loop")
	try:
		n = 0
		while True:
			for watcher in watchers:
				watcher.check_q()
			if UPDATE_STATUS_PAGE:
				update_status_page(watchers, args.resources_dir, args.status_page_dir)
				UPDATE_STATUS_PAGE = False
			time.sleep(1)
			n += 1
			if n == 20:
				n = 0
				UPDATE_STATUS_PAGE = True
	except KeyboardInterrupt:
		logger.info("### Collected information ###")
		for watcher in watchers:
			watcher.observer.stop()
			if watcher.scheduler:
				watcher.scheduler.terminate()
			print('')
			for key in watcher.channel_status.run_data:
				if watcher.channel_status.run_data[key]:
					print(key, ":\t\t", watcher.channel_status.run_data[key])
			print('')
			for i,mux_scan in enumerate(watcher.channel_status.mux_scans):
				print("mux_scan {}:".format(i))
				for key in mux_scan:
					print(key, ":\t\t", mux_scan[key])
			#print(watcher.channel_status.mux_scans)
			print('')
			sys.stdout.flush()
	for watcher in watchers:
		print("joining GA{}0000's observer".format(watcher.channel))
		watcher.observer.join()
		if watcher.scheduler:
			print("joining GA{}0000's scheduler".format(watcher.channel))
			watcher.scheduler.join()
		sys.stdout.flush()

def load_runs_from_database(database_dir):
	for fn in os.listdir(database_dir):
		fp = os.path.join(database_dir, fn)
		with open(fp, "r") as f:
			try:
				flowcell, run_data, mux_scans = json.loads(f.read(), object_pairs_hook=OrderedDict)
			except:
				print("ERROR: Failed to load {}, probably json format corrupted!".format(fn))
				continue

			#key = run_data['run_id']+flowcell['flowcell_id']
			#flowcell_id = flowcell['asic_id'] + flowcell['asic_id_eeprom']
			flowcell_id = flowcell['asic_id_eeprom']
			run_id = run_data['run_id']
			if flowcell_id in ALL_RUNS:
				if run_id in ALL_RUNS[flowcell_id]:
					print("ERROR: {} exists multiple times in database entry for flowcell {}!".format(run_id, 
																									  flowcell_id))
					continue
			else:
				ALL_RUNS[flowcell_id] = {}
			
			ALL_RUNS[flowcell_id][run_id] = {'flowcell': flowcell,
											 'run_data': run_data,
											 'mux_scans': mux_scans}

			try:
				print('{} - loaded experiment "{}" performed on flowcell "{}" on "{}"'.format(flowcell_id, 
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
						'<p><u>Last QC</u> ({0}):<br><br>* : {1}<br>1 : {2}<br>2 : {3}<br>3 : {4}<br>4 : {5}</p>'.format(
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
						runs_string = runs_string + '<a href="{0}" target="_blank">{1}</a><br>'.format(
							os.path.join(watcher.basecalled_basedir, 
										 ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'],
										 ALL_RUNS[asic_id_eeprom][run]['run_data']['minion_id'],
										 'filtered',
										 'results.html'),
							ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'])
					runs_string = runs_string + '</p>'

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
						runs_string = runs_string + '<a href="{0}" target="_blank">{1}</a><br>'.format(
							os.path.join(watcher.basecalled_basedir, 
										 ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'],
										 ALL_RUNS[asic_id_eeprom][run]['run_data']['minion_id'],
										 'filtered',
										 'results.html'),
							ALL_RUNS[asic_id_eeprom][run]['run_data']['user_filename_input'])
					runs_string = runs_string + '</p>'

					flowcell_info_brick = flowcell_info_brick.format(
						channel_to_css[watcher.channel],
						ALL_RUNS[asic_id_eeprom][latest_qc]['flowcell']['flowcell_id'],
						'<p><u>Last QC</u> ({0}):<br><br>* : {1}<br>1 : {2}<br>2 : {3}<br>3 : {4}<br>4 : {5}</p>'.format(
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
						time_diff = "{}".format(protocol_end - protocol_start)[:-7]
				protocol_start = "{}".format(protocol_start)[:-7]
				sequencing_kit = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['sequencing_kit']
				user_filename_input = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['user_filename_input']
				minion_id = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['minion_id']
				link = os.path.join(watchers[0].basecalled_basedir, 
									user_filename_input,
									minion_id,
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
		('protocol_end', None)
		])

	empty_flowcell = OrderedDict([
		('flowcell_id', None),
		('asic_id', None),
		('asic_id_eeprom', None),
		('flowcell', None)
		])

	empty_mux = OrderedDict()

	def __init__(self, minion_id):
		self.minion_id = minion_id
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.mux_scans = []
		self.run_data['minion_id'] = minion_id

	def update(self, content, overwrite=False):
		for key in content:
			if key in self.flowcell:
				if self.flowcell[key]:
					if overwrite:
						logger.info("changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
						self.flowcell[key] = content[key]
					else:
						if VERBOSE: logger.info("not changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
					continue
				else:
					self.flowcell[key] = content[key]
					logger.info("new value for {} : {}".format(key, content[key]))
					continue
			elif key in self.run_data:
				if self.run_data[key]:
					if overwrite:
						logger.info("changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
						self.run_data[key] = content[key]
					else:
						if VERBOSE: logger.info("not changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
					continue
			self.run_data[key] = content[key]
			logger.info("new value for {} : {}".format(key, content[key]))

	def update_mux(self, group, channels, mux, timestamp):
		if self.mux_scans:
			if not group in self.mux_scans[-1]:
				self.mux_scans[-1][group] = []
			if len(self.mux_scans[-1][group]) < 4:
				self.mux_scans[-1][group].append(int(channels))
				if VERBOSE: logger.info("update mux: group {} has {} active channels in mux {}".format(group, channels, mux))

	def update_mux_group_totals(self, group, channels, timestamp):
		if not self.mux_scans:
			self.new_mux(timestamp)
		self.mux_scans[-1]['group {} total'.format(group)] = channels
		if VERBOSE: logger.info("update mux group totals: group {} has a total of {} active channels".format(group, channels))

	def new_mux(self, timestamp):
		if self.mux_scans:
			self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234" if i in self.mux_scans[-1]])
			logger.info("calculated mux total to {}".format(self.mux_scans[-1]['total']))
		self.mux_scans.append(copy.deepcopy(self.empty_mux))
		self.mux_scans[-1]['timestamp'] = timestamp
		if VERBOSE: logger.info("added new mux result")

	def flowcell_disconnected(self):
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []

	def run_finished(self):
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []


class Scheduler(mp.Process):

	def __init__(self, update_interval, statsfp, statsparser_args, 
				 user_filename_input, minion_id, flowcell_id, protocol_start,
				 resources_dir, statsparser_path, python3_path):
		mp.Process.__init__(self)
		self.exit = mp.Event()
		#self.sched_q = sched_q
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
		while not self.exit.is_set():
			last_time = time.time()
			#print("updating stats page")
			#self.doNotDisturb = True
			# do something!
			logger.info("STARTING STATSPARSING")

			if os.path.exists(self.statsfp):
				args = [self.python3_path, self.statsparser_path, self.statsfp,
						'--user_filename_input', self.user_filename_input,
						'--minion_id', self.minion_id,
						'--flowcell_id', self.flowcell_id,
						'--protocol_start', self.protocol_start,
						'--resources_dir', self.resources_dir,
						'-q']
				args.extend(self.statsparser_args)
				cp = subprocess.run(args) # waits for process to complete
				if cp.returncode == 0:
					logger.info("STATSPARSING COMPLETED")
					if not page_opened:
						basedir = os.path.abspath(os.path.dirname(self.statsfp))
						fp = os.path.join(basedir, 'results.html')
						logger.info("OPENING " + fp)
						page_opened = webbrowser.open('file://' + os.path.realpath(fp))
				else:
					logger.info("ERROR while running statsparser")
			else:
				logger.info("WARNING: statsfile does not exist (yet?)")

			#self.doNotDisturb = False
			this_time = time.time()
			while (this_time - last_time < self.update_interval) and not self.exit.is_set():
				time.sleep(1)
				this_time = time.time()


class Watcher():

	def __init__(self, minknow_log_basedir, channel, modified_as_created, database_dir, 
				 basecalled_basedir, statsparser_args, update_interval, no_watchnchop,
				 resources_dir, watchnchop_path, statsparser_path, python3_path, perl_path):
		self.q = mp.SimpleQueue()
		self.watchnchop = not no_watchnchop
		self.channel = channel
		self.database_dir = database_dir
		self.basecalled_basedir = basecalled_basedir
		self.statsparser_args = statsparser_args
		self.update_interval = update_interval
		self.resources_dir = resources_dir
		self.watchnchop_path = watchnchop_path
		self.statsparser_path = statsparser_path
		self.python3_path = python3_path
		self.perl_path = perl_path
		self.observed_dir = os.path.join(minknow_log_basedir, "GA{}0000".format(channel+1))
		self.event_handler = StatsFilesEventHandler(self.q, modified_as_created)
		self.observer = Observer()
		self.observer.schedule(self.event_handler, 
							   self.observed_dir, 
							   recursive=False)
		self.observer.start()
		print("...watcher for {} ready".format(self.observed_dir))

		self.channel_status = ChannelStatus("GA{}0000".format(channel+1))

		#self.ctx = mp.get_context('spawn')
		#self.sched_q = mp.SimpleQueue()
		self.scheduler = None

	def check_q(self):
		# checking sheduler queue
		if not self.q.empty:
			if VERBOSE: logger.info("Queue content for {}:".format(self.observed_dir))
		while not self.q.empty():
			content = self.q.get()
			#logger.info(content)
			if VERBOSE: print("received:", content)

			# case content is new data for channel report
			if isinstance(content[0], dict):
				self.channel_status.update(content[0], content[1])

			# case timestamped information
			else:
				timestamp = content[0]
				global UPDATE_STATUS_PAGE
				UPDATE_STATUS_PAGE = True
				# case content is mux information
				if isinstance(content[1], tuple):
					if len(content[1]) == 3:
						self.channel_status.update_mux(content[1][0], content[1][1], content[1][2], timestamp)
					elif len(content[1]) == 2:
						self.channel_status.update_mux_group_totals(content[1][0], content[1][1], timestamp)
					elif len(content[1]) == 1:
						self.channel_status.update_mux_group_totals("*", content[1][0], timestamp)
				elif content[1] == "Finished Mux Scan":
					logger.info("MUXSCAN FINISHED")
					self.channel_status.new_mux(timestamp)
					self.save_report()
				elif content[1] == "sequencing start":
					logger.info("SEQUENCING STARTS")

					#start porechop & filter & rsync
					if self.watchnchop:
						self.start_watchnchop()

					#start regular creation of plots
					if self.scheduler:
						self.scheduler.terminate()
						self.scheduler.join()
					statsfp = os.path.join(self.basecalled_basedir, 
										   self.channel_status.run_data['user_filename_input'],
										   "GA{}0000".format(self.channel+1),
										   'filtered',
										   'stats.txt')
					logger.info('SCHEDULING update of stats-webpage every {0:.1f} minutes for stats file '.format(self.update_interval/1000) + statsfp)
					self.scheduler = Scheduler(self.update_interval, 
											   statsfp, 
											   self.statsparser_args, 
											   self.channel_status.run_data['user_filename_input'], 
											   "GA{}0000".format(self.channel+1), 
											   self.channel_status.flowcell['flowcell_id'], 
											   self.channel_status.run_data['protocol_start'],
											   self.resources_dir,
											   self.statsparser_path,
											   self.python3_path)
					self.scheduler.start()

				elif content[1] == "flowcell discovered":
					logger.info("FLOWCELL DISCOVERED")
					self.channel_status.flowcell_disconnected()
					if self.scheduler:
						self.scheduler.terminate()
						self.scheduler.join()
					self.scheduler = None

				elif content[1] == "Finished QC":
					logger.info("QC FINISHED")
					#self.save_report()
					#self.channel_status.run_finished()
				elif content[1] == "new bream_log file":
					logger.info("NEW EXPERIMENT RUN")
					#self.channel_status.run_finished()
				elif content[1] == "flowcell disconnected":
					logger.info("FLOWCELL DISCONNECTED")
					self.channel_status.flowcell_disconnected()
				elif content[1] == "protocol started":
					logger.info("PROTOCOL STARTED")
					self.channel_status.run_data['protocol_start'] = content[0]
				elif content[1] == "protocol finished":
					logger.info("PROTOCOL FINISHED")
					self.channel_status.run_data['protocol_end'] = content[0]
					if self.channel_status.mux_scans:
						self.save_report()
					self.channel_status.run_finished()
					if self.scheduler:
						self.scheduler.terminate()
						self.scheduler.join()
					self.scheduler = None
				elif content[1] == "flowcell lookup":
					logger.info("LOADING PREVIOUS FLOWCELL RUNS")
					#self.lookup_flowcell()

	def lookup_flowcell(self):
		try:
			#flowcell_id = self.channel_status.flowcell['asic_id'] + self.channel_status.flowcell['asic_id_eeprom']
			flowcell_id = self.channel_status.flowcell['asic_id_eeprom']
		except:
			logger.info("ERROR: flowcell lookup failed")
			return
		if flowcell_id in ALL_RUNS:
			for run in ALL_RUNS[flowcell_id]:
				print()
				print('#### {} ####'.format(run))
				print()
				for info in ALL_RUNS[flowcell_id][run]:
					print(info)
					if isinstance(ALL_RUNS[flowcell_id][run][info], dict):
						for key in ALL_RUNS[flowcell_id][run][info]:
							print("\t", key, ":", ALL_RUNS[flowcell_id][run][info][key])
					elif isinstance(ALL_RUNS[flowcell_id][run][info], list):
						for entry in ALL_RUNS[flowcell_id][run][info]:
							print()
							if isinstance(entry, dict):
								for key in entry:
									print("\t", key, entry[key])
							else:
								print("\t", entry)
		else:
			logger.info("no entrys for this flowcell in the database")


	def save_report(self):
		try:
			fn = []
			if self.channel_status.run_data['user_filename_input']:
				fn.append(self.channel_status.run_data['user_filename_input'])
			else:
				fn.append("QC")
			if self.channel_status.flowcell['flowcell_id']:
				fn.append(self.channel_status.flowcell['flowcell_id'])
			fn.append(self.channel_status.run_data['run_id'])
			fn = "_".join(fn) + ".txt"

			data = (self.channel_status.flowcell, self.channel_status.run_data, self.channel_status.mux_scans)

			with open( os.path.join(self.database_dir, fn), 'w') as f:
				print(json.dumps(data, indent=4), file=f)

			#key = self.channel_status.run_data['run_id'] + self.channel_status.flowcell['flowcell_id']
			run_id = self.channel_status.run_data['run_id']
			#flowcell_id = self.channel_status.flowcell['flowcell_id']
			#flowcell_id = self.channel_status.flowcell['asic_id'] + self.channel_status.flowcell['asic_id_eeprom']
			flowcell_id = self.channel_status.flowcell['asic_id_eeprom']
			if flowcell_id in ALL_RUNS:
				ALL_RUNS[flowcell_id][run_id] = {'flowcell': data[0],
												 'run_data': data[1],
												 'mux_scans': data[2]}
			else:
				ALL_RUNS[flowcell_id] = {}
				ALL_RUNS[flowcell_id][run_id] = {'flowcell': data[0],
												 'run_data': data[1],
												 'mux_scans': data[2]}
		except:
			logger.info("ERROR: could not save report of channel GA{}0000".format(self.channel+1))

	def start_watchnchop(self):
		logger.info("STARTING WATCHNCHOP")
		if self.channel_status.run_data['user_filename_input']:
			#cmd = " ".join([self.perl_path, self.watchnchop_path, '-b', os.path.join(self.basecalled_basedir, self.channel_status.run_data['user_filename_input'], self.channel_status.minion_id)])
			cmd = [self.perl_path, self.watchnchop_path, '-b', os.path.join(self.basecalled_basedir, self.channel_status.run_data['user_filename_input'], self.channel_status.minion_id)]
			try:
				#subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			except:
				logger.info("ERROR: FAILED to start watchnchop, popen failed")
			logger.info("STARTED WATCHNCHOP with arguments:")
			print(cmd)
		else:
			logger.info("ERROR: FAILED to start watchnchop, no user_filename_input")




class OpenedFilesHandler():
	'''manages a set of opened files, reads their contents and 
	processes them lineby line. Incomplete lines are stored until
	they are "completed" by a newline character.'''
	open_files = {}

	def open_new_file(self, path):
		logger.info("Opening file {}".format(path))
		self.open_files[path] = [open(path, 'r'), ""]

	def close_file(self, path):
		if VERBOSE: logger.info("Attempting to close file {}".format(path))
		try:
			self.open_files[path][0].close()
		except:
			if VERBOSE: logger.info("File handle of file {} couldn't be closed".format(path))
		if path in self.open_files:
			del self.open_files[path]
		if VERBOSE: logger.info("Deleted entry in open_files for file {}".format(path))

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


class StatsFilesEventHandler(FileSystemEventHandler):
	file_handler = OpenedFilesHandler()
	control_server_log = None
	bream_log = None

	def __init__(self, q, modified_as_created):
		super(StatsFilesEventHandler, self).__init__()
		self.q = q
		self.modified_as_created = modified_as_created

	def on_moved(self, event):
		pass

	def on_created(self, event):
		if not event.is_directory:
			if VERBOSE: logger.info("File {} was created".format(event.src_path))
			basename = os.path.basename(event.src_path)
			if basename.startswith("control_server_log"):
				if self.control_server_log:
					self.file_handler.close_file(event.src_path)
					logger.info("Replacing current control_server_log file {} with {}".format(self.control_server_log, event.src_path))
				self.control_server_log = event.src_path
				logger.info("New control_server_log file {}".format(self.control_server_log))
				process_function = self.parse_server_log_line
			elif basename.startswith("bream"):
				if self.bream_log:
					self.file_handler.close_file(event.src_path)
					logger.info("Replacing current bream_log file {} with {}".format(self.bream_log, event.src_path))
					#TODO: Find out if more than one bream log file can belong to a running experiment (probably not)
				self.bream_log = event.src_path
				logger.info("New bream_log file {}".format(self.bream_log))
				process_function = self.parse_bream_log_line
				self.q.put( ("", "new bream_log file") )
			else:
				if VERBOSE: logger.info("File {} is not of concern for this tool".format(event.src_path))
				return
			self.file_handler.open_new_file(event.src_path)
			#self.file_handler.process_lines_until_EOF(self, event.src_path)
			self.file_handler.process_lines_until_EOF(process_function, event.src_path)

	def on_deleted(self, event):
		if not event.is_directory:
			if VERBOSE: logger.info("File {} was deleted".format(event.src_path))
			#self.file_handler.close_file(event.src_path)
			if self.control_server_log == event.src_path:
				control_server_log = None
				logger.info("WARNING: Current control_server_log file {} was deleted!".format(event.src_path))
			elif self.bream_log == event.src_path:
				self.bream_log = None
				logger.info("EARNING: Current bream_log file {} was deleted".format(event.src_path))
			else:
				if VERBOSE: logger.info("File {} is not opened and is therefore not closed.".format(event.src_path))
				#return 
			self.file_handler.close_file(event.src_path)

	def on_modified(self, event):
		if not event.is_directory:
			if VERBOSE: logger.info("File {} was modified".format(event.src_path))
			if event.src_path in self.file_handler.open_files:
				if self.control_server_log == event.src_path:
					process_function = self.parse_server_log_line
				elif self.bream_log == event.src_path:
					process_function = self.parse_bream_log_line
				else:
					logger.info("WARNING: case not handled")
					return
				self.file_handler.process_lines_until_EOF(process_function, event.src_path)
			else:
				if self.modified_as_created:
					self.on_created(event)
				else:
					if VERBOSE: logger.info("File {} existed before this script was started".format(event.src_path))

	def parse_server_log_line(self, line):
		dict_content = {}
		send_after = None
		overwrite = False

		#if 		"[mgmt/info]: : active_device_set" 						in line or \
		if   		"protocol_started"									in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True
			self.q.put( (line[:23], "protocol started") )

		elif		"protocol_finished" 								in line:
			self.q.put( (line[:23], "protocol finished") )

		elif	"[engine/info]: : flowcell_discovered" 					in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
				overwrite = True
			self.q.put( (line[:23], "flowcell discovered") )
			send_after = (line[:23], "flowcell lookup")

		#elif 	"asic_id_changed"										in line:
		#	for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):

		elif   	"[engine/info]: : data_acquisition_started"				in line:# or \
				#"[saturation_control/info]: : saturation_mode_changed" 	in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
				overwrite = True

		elif	"flowcell_disconnected"									in line:
			self.q.put( (line[:23], "flowcell disconnected") )

		if dict_content:
			self.q.put( (dict_content, overwrite) )
		if send_after:
			self.q.put( send_after )


	def parse_bream_log_line(self, line):
		dict_content = {}
		overwrite = False

		if 		"root - INFO - argument"								in line:
			for m in re.finditer("([^\s,]+) was set to ([^\s,]+)", line): 
				dict_content[m.group(1)] = m.group(2)

		elif 	"INFO - Adding the following context_tags:" 			in line or \
				"INFO - Context tags set to"							in line:
			for m in re.finditer("'([^\s,]+)'[:,] u?'([^\s,]+)'", line):
				dict_content[m.group(1)] = m.group(2)
			if 'filename' in dict_content:
				dict_content['flowcell_id'] = dict_content['filename'].split("_")[2]

		elif	"bream.core.base.database - INFO - group"				in line:
			for m in re.finditer("group ([0-9]+) has ([0-9]+) channels in mux ([0-9]+)", line):
				self.q.put( (line[:23], (m.group(1), m.group(2), m.group(3))) )

		elif	"[user message]--> group "								in line.lower():
			for m in re.finditer("roup ([0-9]+) has ([0-9]+) active", line):
				self.q.put( (line[:23], (m.group(1), m.group(2))) )

		elif	"[user message]--> A total of"							in line:
			for m in re.finditer("total of ([0-9]+) single pores", line):
				self.q.put( (line[:23], (m.group(1),) ) )

		elif	"INFO - [user message]--> Finished Mux Scan"			in line:
			self.q.put( (line[:23], "Finished Mux Scan") )

		elif	"platform_qc.PlatformQCExperiment'> finished"			in line:
			self.q.put( (line[:23], "Finished QC") )

		elif	"INFO - STARTING MAIN LOOP"								in line:
			dict_content["sequencing_start_time"] = line[:23]
			self.q.put( (line[:23], "sequencing start") )

		if dict_content:
			self.q.put( (dict_content, overwrite) )

if __name__ == "__main__":
	#logging.basicConfig(level=logging.INFO,
	#					format='%(threadName)s: %(asctime)s - %(message)s',
	#					datefmt='%Y-%m-%d %H:%M:%S')
	#logger.info("basic info called")
	main_and_args()
