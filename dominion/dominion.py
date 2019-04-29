"""
Copyright 2018 Markus Haak (markus.haak@posteo.net)
https://github.com/MarkusHaak/dominION

This file is part of dominION. dominION is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version. dominION is distributed in
the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details. You should have received a copy of the GNU General Public License along with dominION. If
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
from shutil import copyfile, which
import dateutil
from datetime import datetime
from operator import itemgetter
from .version import __version__
from .statsparser import get_argument_parser as sp_get_argument_parser
from .statsparser import parse_args as sp_parse_args
from .helper import initLogger, resources_dir, get_script_dir, hostname, ArgHelpFormatter, r_file, r_dir, rw_dir, defaults, jinja_env
import threading
import logging
import queue
from pathlib import Path
from jinja2 import Environment, PackageLoader, select_autoescape

ALL_RUNS = {}
ALL_RUNS_LOCK = threading.RLock()
UPDATE_OVERVIEW = False
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

	general_group = parser.add_argument_group('General arguments', 
											  "arguments for advanced control of the program's behavior")

	general_group.add_argument('-n', '--no_transfer',
							   action='store_true',
							   help='''no data transfer to the remote host''')
	general_group.add_argument('-a', '--all_fast5',
							   action='store_true',
							   help='''also put fast5 files of reads removed by length and quality 
							           filtering into barcode bins''')
	general_group.add_argument('-p', '--pass_only',
							   action='store_true',
							   help='''use data from fastq_pass only''')
	general_group.add_argument('-l', '--min_length',
							   type=int,
							   default=1000,
							   help='''minimal length to pass filter''')
	general_group.add_argument('-q', '--min_quality',
							   type=int,
							   default=5,
							   help='''minimal quality to pass filter''')
	general_group.add_argument('-d', '--rsync_dest',
							   default="{}@{}:{}".format(defaults()["user"], defaults()["host"], defaults()["dest"]),
							   help='''destination for data transfer with rsync, format USER@HOST[:DEST].
							           Key authentication for the specified destination must be set up (see option -i),
							           otherwise data transfer will fail. Default value is parsed from setting
							           file {}'''.format(os.path.join(resources_dir, "defaults.ini")))
	general_group.add_argument('-i', '--identity_file',
							   default="{}".format(defaults()["identity"]),
							   help='''file from which the identity (private key) for public key authentication is read.
							           Default value is parsed from setting file {}'''.format(os.path.join(resources_dir, "defaults.ini")))
	general_group.add_argument('--bc_kws',
							   nargs='*',
							   default=['RBK', 'NBD', 'RAB', 'LWB', 'PBK', 'RPB', 'arcod'],
							   help='''if at least one of these key words is a substring of the run name,
									   porechop is used to demultiplex the fastq data''')
	general_group.add_argument('-u', '--update_interval',
							   type=int,
							   default=300,
							   help='minimum time interval in seconds for updating the content of a report page')
	general_group.add_argument('-m', '--ignore_file_modifications',
							   action='store_true',
							   help='''Ignore file modifications and only consider file creations regarding 
							           determination of the latest log files''')

	io_group = parser.add_argument_group('I/O arguments', 
										 'Further input/output arguments. Only for special use cases')
	io_group.add_argument('-o', '--output_dir',
						  action=rw_dir,
						  default="/data/dominION/",
						  help='Path to the base directory where experiment reports shall be saved')
	arg_data_basedir = \
	io_group.add_argument('--data_basedir',
						  action=rw_dir,
						  default='/data',
						  help='Path to the directory where basecalled data is saved')
	io_group.add_argument('--minknow_log_basedir',
						  action=r_dir,
						  default='/var/log/MinKNOW',
						  help='''Path to the base directory of GridIONs log files''')

	io_group.add_argument('--logfile',
						  help='''File in which logs will be safed 
						  (default: OUTPUTDIR/logs/YYYY-MM-DD_hh:mm_HOSTNAME_LOGLVL.log''')

	sp_arguments = parser.add_argument_group('Statsparser arguments',
										   'Arguments passed to statsparser for formatting html reports')
	sp_arguments.add_argument('--statsparser_args',
							action=parse_statsparser_args,
							default=[],
							help='''Arguments that are passed to the statsparser script.
								   See a full list of available arguments with --statsparser_args " -h" ''')

	help_group = parser.add_argument_group('Help')
	help_group.add_argument('-h', '--help', 
							action='help', 
							default=argparse.SUPPRESS,
							help='Show this help message and exit')
	help_group.add_argument('--version', 
							action='version', 
							version=__version__,
							help="Show program's version string and exit")
	help_group.add_argument('-v', '--verbose',
							action='store_true',
							help='Additional debug messages are printed to stdout')
	help_group.add_argument('--quiet',
							action='store_true',
							help='Only errors and warnings are printed to stdout')

	args = parser.parse_args()


	ns = argparse.Namespace()
	arg_data_basedir(parser, ns, args.data_basedir, '')

	if not os.path.exists(args.identity_file):
		print("Identity file {} does not exists. Please check key authentication settings or specify a different key with option -i.".format(args.identity_file))

	watchnchop_args = []
	if args.no_transfer:
		watchnchop_args.append('-n')
	if args.all_fast5:
		watchnchop_args.append('-a')
	if args.pass_only:
		watchnchop_args.append('-p')
	watchnchop_args.extend(['-l', str(args.min_length)])
	watchnchop_args.extend(['-q', str(args.min_quality)])
	watchnchop_args.extend(['-d', args.rsync_dest])
	watchnchop_args.extend(['-i', args.identity_file])

	#### main #####

	for p in [args.output_dir,
			  os.path.join(args.output_dir, 'runs'),
			  os.path.join(args.output_dir, 'qc'),
			  os.path.join(args.output_dir, 'logs')]:
		if not os.path.exists(p):
			os.makedirs(p)

	global logger
	if args.verbose:
		loglvl = logging.DEBUG
	elif args.quiet:
		loglvl = logging.WARNING
	else:
		loglvl = logging.INFO
	if not args.logfile:
		args.logfile = os.path.join(args.output_dir, 
									'logs', 
									"{}_{}_{}.log".format(datetime.now().strftime("%Y-%m-%d_%H:%M"),
														  hostname,
														  loglvl))
	initLogger(logfile=args.logfile, level=loglvl)

	logger = logging.getLogger(name='gw')

	logger.info("##### starting dominION {} #####\n".format(__version__))

	global UPDATE_OVERVIEW
	logger.info("setting up dominION status page environment")
	if not os.path.exists(os.path.join(args.output_dir, 'res')):
		os.makedirs(os.path.join(args.output_dir, 'res'))
	for res_file in ['style.css', 'flowcell.png', 'no_flowcell.png']:
		copyfile(os.path.join(resources_dir, res_file), 
				 os.path.join(args.output_dir, 'res', res_file))

	global ALL_RUNS
	global ALL_RUNS_LOCK
	global UPDATE_OVERVIEW
	#logger.info("loading previous runs from database:")
	#load_runs_from_database(args.database_dir)
	import_qcs(os.path.join(args.output_dir, "qc"))
	import_runs(os.path.join(args.output_dir, "runs"))

	logger.info("starting to observe runs directory for changes to directory names")
	observed_dir = os.path.join(args.output_dir, 'runs')
	event_handler = RunsDirsEventHandler(observed_dir)
	observer = Observer()
	observer.schedule(event_handler, 
					  observed_dir, 
					  recursive=True)
	observer.start()

	logger.info("starting channel watchers:")
	watchers = []
	for channel in range(5):
		watchers.append(Watcher(args.minknow_log_basedir, 
								channel, 
								args.ignore_file_modifications, 
								args.output_dir, 
								args.data_basedir, 
								args.statsparser_args,
								args.update_interval,
								watchnchop_args,
								args.bc_kws))

	logger.info("initiating dominION overview page")
	update_overview(watchers, args.output_dir)
	webbrowser.open('file://' + os.path.realpath(os.path.join(args.output_dir, "{}_overview.html".format(hostname))))

	logger.info("entering main loop")
	try:
		n = 0
		while True:
			for watcher in watchers:
				watcher.check_q()
			if UPDATE_OVERVIEW:
				update_overview(watchers, args.output_dir)
				UPDATE_OVERVIEW = False
			time.sleep(0.2)
			n += 1
			if n == 100:
				n = 0
				UPDATE_OVERVIEW = True
	except KeyboardInterrupt:
		for watcher in watchers:
			watcher.observer.stop()
			if watcher.spScheduler.is_alive() if watcher.spScheduler else None:
				watcher.spScheduler.join(timeout=0.05)
			for wcScheduler in watcher.wcScheduler:
				if wcScheduler.is_alive() if wcScheduler else None:
					wcScheduler.join(timeout=0.05)
	for watcher in watchers:
		logger.info("joining GA{}0000's observer".format(watcher.channel))
		watcher.observer.join()
		if watcher.spScheduler.is_alive() if watcher.spScheduler else None:
			logger.info("joining GA{}0000's statsparser scheduler".format(watcher.channel))
			watcher.spScheduler.join()
		for wcScheduler in watcher.wcScheduler:
			if wcScheduler.is_alive() if wcScheduler else None:
				logger.info("joining GA{}0000's watchnchop scheduler".format(watcher.channel))
				wcScheduler.join()

def add_database_entry(flowcell, run_data, mux_scans):
	ALL_RUNS_LOCK.acquire()
	#TODO: check for all mandatory entries
	asic_id_eeprom = flowcell['asic_id_eeprom']
	run_id = run_data['run_id']
	if asic_id_eeprom in ALL_RUNS:
		if run_id in ALL_RUNS[asic_id_eeprom]:
			logger.warning("{} exists multiple times in database!".format(run_id))
			logger.warning("conflicting runs: {}, {}".format(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['user_filename_input'],
															 run_data['user_filename_input']))
			logger.warning("conflict generating report file: {}".format(fn))
			ALL_RUNS_LOCK.release()
			return False
	else:
		ALL_RUNS[asic_id_eeprom] = {}
	
	ALL_RUNS[asic_id_eeprom][run_id] = {'flowcell'	: flowcell,
										'run_data'	: run_data,
										'mux_scans'	: mux_scans}
	logger.info('{} - added experiment "{}" performed on flowcell "{}" on "{}"'.format(asic_id_eeprom, 
																					   run_data['experiment_type'], 
																					   flowcell['flowcell_id'], 
																					   run_data['protocol_start']))
	ALL_RUNS_LOCK.release()
	return True

def import_qcs(qc_dir):
	logger.info("importing platform qc entries from files in directory {}".format(qc_dir))
	for fp in [os.path.join(qc_dir, fn) for fn in os.listdir(qc_dir) if fn.endswith('.json')]:
		if os.path.isfile(fp):
			with open(fp, "r") as f:
				try:
					flowcell, run_data, mux_scans = json.loads(f.read(), object_pairs_hook=OrderedDict)
				except:
					logger.warning("failed to parse {}, json format or data structure corrupt".format(fn))
					continue
			if not add_database_entry(flowcell, run_data, mux_scans):
				logger.error("failed to add content from {} to the database".format(fp))
				continue

def import_runs(base_dir, refactor=False):
	logger.info("importing sequencing run entries from files in directory {}".format(base_dir))
	for user_filename_input in [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]:
		run_dir = os.path.join(base_dir, user_filename_input)
		for sample in [d for d in os.listdir(run_dir) if os.path.isdir(os.path.join(run_dir, d))]:
			sample_dir = os.path.join(run_dir, sample)
			for fp in [os.path.join(sample_dir, fn) for fn in os.listdir(sample_dir) if fn.endswith('.json')]:
				if os.path.isfile(fp):
					with open(fp, "r") as f:
						try:
							flowcell, run_data, mux_scans = json.loads(f.read(), object_pairs_hook=OrderedDict)
						except:
							logger.warning("failed to parse {}, json format or data structure corrupt".format(fn))
							continue
					# temporarily change attributes user_filename_input and sample according to directory names
					prev = (run_data['user_filename_input'] if 'user_filename_input' in run_data else None, 
							run_data['sample'] if 'sample' in run_data else None)
					changed = prev == (user_filename_input, sample)
					run_data['user_filename_input'] = user_filename_input
					run_data['sample'] = sample
					if refactor and changed:
						# make changes permanent
						logging.info("writing changes to attributes 'user_filename_input' and 'sample' to file")
						data = (flowcell, run_data, mux_scans)
						with open( fp, 'w') as f:
							print(json.dumps(data, indent=4), file=f)
					
					if not add_database_entry(flowcell, run_data, mux_scans):
						logger.error("failed to add content from {} to the database".format(fp))
						continue

def get_runs_by_flowcell(asic_id_eeprom):
	ALL_RUNS_LOCK.acquire()
	runs = {}
	if asic_id_eeprom:
		if asic_id_eeprom in ALL_RUNS:
			for run_id in ALL_RUNS[asic_id_eeprom]:
				if 'seq' in ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type'].lower():
					runs[run_id] = ALL_RUNS[asic_id_eeprom][run_id]
	ALL_RUNS_LOCK.release()
	return runs

def get_qcs_by_flowcell(asic_id_eeprom):
	ALL_RUNS_LOCK.acquire()
	qcs = {}
	if asic_id_eeprom:
		if asic_id_eeprom in ALL_RUNS:
			for run_id in ALL_RUNS[asic_id_eeprom]:
				if 'seq' not in ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type'].lower():
					qcs[run_id] = ALL_RUNS[asic_id_eeprom][run_id]
	ALL_RUNS_LOCK.release()
	return qcs

def get_latest(runs):
	latest_qc = None
	for run_id in runs:
		if latest_qc:
			_protocol_start = dateutil.parser.parse(runs[latest_qc]['run_data']['protocol_start'])
			if protocol_start > _protocol_start:
				latest_qc = run_id
		else:
			latest_qc = run_id
			protocol_start = dateutil.parser.parse(runs[run_id]['run_data']['protocol_start'])
	return latest_qc

def update_overview(watchers, output_dir):
	channel_to_css = {0:"GA10000", 1:"GA20000", 2:"GA30000", 3:"GA40000", 4:"GA50000"}
	render_dict = {"version"		:	__version__,
				   "dateTimeNow"	:	datetime.now().strftime("%Y-%m-%d_%H:%M"),
				   "channels"		: 	[],
				   "all_exp" 		:	[]
				   }
	for watcher in watchers:
		channel = watcher.channel
		render_dict["channels"].append({})
		asic_id_eeprom = None
		try:
			asic_id_eeprom = watcher.channel_status.flowcell['asic_id_eeprom']
		except:
			pass

		runs = get_runs_by_flowcell(asic_id_eeprom)
		qcs  = get_qcs_by_flowcell(asic_id_eeprom)

		render_dict["channels"][channel]['latest_qc'] = {}
		latest_qc = get_latest(qcs)
		if latest_qc:
			render_dict["channels"][channel]['latest_qc']['timestamp'] 	= dateutil.parser.parse(qcs[latest_qc]['run_data']['protocol_start']).date()
			render_dict["channels"][channel]['latest_qc']['group_all'] 	= qcs[latest_qc]['mux_scans'][0]['group * total']
			render_dict["channels"][channel]['latest_qc']['group_1'] 	= qcs[latest_qc]['mux_scans'][0]['group 1 total']
			render_dict["channels"][channel]['latest_qc']['group_2'] 	= qcs[latest_qc]['mux_scans'][0]['group 2 total']
			render_dict["channels"][channel]['latest_qc']['group_3'] 	= qcs[latest_qc]['mux_scans'][0]['group 3 total']
			render_dict["channels"][channel]['latest_qc']['group_4'] 	= qcs[latest_qc]['mux_scans'][0]['group 4 total']

		render_dict["channels"][channel]['runs'] = []
		for run_id in runs:
			user_filename_input = runs[run_id]['run_data']['user_filename_input']
			sample = runs[run_id]['run_data']['sample']
			if not sample:
				sample = user_filename_input
			link = os.path.abspath(os.path.join(output_dir,'runs',user_filename_input,sample,'report.html'))
			render_dict["channels"][channel]['runs'].append({'user_filename_input':user_filename_input,
															 'link':link})

		render_dict["channels"][channel]['channel'] = channel_to_css[watcher.channel]
		render_dict["channels"][channel]['asic_id_eeprom'] = asic_id_eeprom
		if asic_id_eeprom:
			if latest_qc == None and runs == {}:
				render_dict["channels"][channel]['flowcell_id'] = "NO RECORDS"
			elif latest_qc:
				render_dict["channels"][channel]['flowcell_id'] = qcs[latest_qc]['flowcell']['flowcell_id']
			else:
				render_dict["channels"][channel]['flowcell_id'] = runs[list(runs.keys())[0]]['flowcell']['flowcell_id']
		else:	
			render_dict["channels"][channel]['flowcell_id'] = '-'

	ALL_RUNS_LOCK.acquire()
	all_runs_info = []
	for asic_id_eeprom in ALL_RUNS:
		for run_id in ALL_RUNS[asic_id_eeprom]:
			experiment_type = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type']
			if 'seq' in experiment_type.lower(): # to increase compatibility in future
				protocol_start = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_start'])
				duration = "N/A"
				if 'protocol_end' in ALL_RUNS[asic_id_eeprom][run_id]['run_data']:
					if ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_end']:
						protocol_end = dateutil.parser.parse(ALL_RUNS[asic_id_eeprom][run_id]['run_data']['protocol_end'])
						duration = "{}".format(protocol_end - protocol_start).split('.')[0]
				sequencing_kit = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['sequencing_kit']
				user_filename_input = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['user_filename_input']
				sample = ALL_RUNS[asic_id_eeprom][run_id]['run_data']['sample']
				if not sample:
					sample = user_filename_input
				link = os.path.abspath(os.path.join(output_dir,'runs',user_filename_input,sample,'report.html'))
				all_runs_info.append({'link':link,
									  'user_filename_input':user_filename_input,
									  'sample': sample,
									  'sequencing_kit': sequencing_kit,
									  'protocol_start': protocol_start,
									  'duration': duration})
	ALL_RUNS_LOCK.release()

	if all_runs_info:
		all_runs_info = sorted(all_runs_info, key=lambda k: k['protocol_start'], reverse=True)

		run = 0
		sample = 0
		grouped = [[[all_runs_info[0]]]] if all_runs_info else [[[]]]
		for run_info in all_runs_info[1:]:
			if grouped[run][sample][0]['user_filename_input'] == run_info['user_filename_input']:
				if grouped[run][sample][0]['sample'] == run_info['sample']:
					grouped[run][sample].append(run_info)
				else:
					grouped[run].append( [run_info] )
					sample += 1
			else:
				grouped.append( [[run_info]] )
				run += 1
				sample = 0


		for exp in grouped:
			render_dict['all_exp'].append(
				{'num_samples':str(sum([len(sample) for sample in exp])),
				 'user_filename_input':exp[0][0]['user_filename_input'],
				 'samples':[]})
			for sample in exp:
				render_dict['all_exp'][-1]['samples'].append(
					{'num_runs':str(len(sample)),
					 'link':sample[0]['link'],
					 'sample_name':sample[0]['sample'],
					 'runs':[]})
				for run in sample:
					render_dict['all_exp'][-1]['samples'][-1]['runs'].append(run)

	template = jinja_env.get_template('overview.template')
	with open(os.path.join(output_dir, "{}_overview.html".format(hostname)), 'w') as f:
		print(template.render(render_dict), file=f)

class ChannelStatus():
	empty_run_data = OrderedDict([
		('run_id', None),
		('user_filename_input', None), # user Run title
		('minion_id', None),
		('sequencing_kit', None),
		('protocol_start', None),
		('protocol_end', None),
		('relative_path', None),
		('sample', None)
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
		self.logger.info("resetting flowcell and run data")
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []

	def reset_channel(self):
		self.logger.info("resetting run data")
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

	def __init__(self, data_basedir, relative_path, user_filename_input, fastq_reads_per_file, bc_kws, stats_fp, channel, watchnchop_args):
		threading.Thread.__init__(self)
		if getattr(self, 'daemon', None) is None:
			self.daemon = True
		else:
			self.setDaemon(True)
		self.stoprequest = threading.Event()	# set when joined without timeout (eg if terminated with ctr-c)
		self.exp_end = threading.Event()			# set when joined with timeout (eg if experiment ended)
		self.logger = logging.getLogger(name='gw.w{}.wcs'.format(channel+1))

		self.observed_dir = os.path.join(data_basedir, relative_path, 'fastq_pass')
		# define the command that is to be executed
		self.cmd = [which('perl'),
					which('watchnchop'),
					'-o', stats_fp,
					'-f', str(fastq_reads_per_file)]
		if watchnchop_args:
			self.cmd.extend(watchnchop_args)
		if len([kw for kw in bc_kws if kw in user_filename_input]) > 0:
			self.cmd.append('-b')
		self.cmd.append(os.path.join(data_basedir, relative_path, ''))
		#self.cmd = " ".join(self.cmd)
		self.process = None

	def run(self):
		self.logger.info("STARTED watchnchop scheduler")
		while not (self.stoprequest.is_set() or self.exp_end.is_set()):
			if self.conditions_met():
				self.process = subprocess.Popen(self.cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				self.logger.info("STARTED WATCHNCHOP with arguments: {}".format(self.cmd))
				break
			time.sleep(1)
		while not (self.stoprequest.is_set() or self.exp_end.is_set()):
			time.sleep(1)
		if self.process:
			try:
				self.process.terminate()
				self.logger.info("TERMINATED watchnchop process")
			except:
				self.logger.error("TERMINATING watchnchop process failed")
		else:
			if self.stoprequest.is_set():
				self.logger.error("watchnchop was NEVER STARTED: this thread was ordered to kill the watchnchop subprocess before it was started")
				return
			
			# try one last time to start watchnchop (necessary for runs with extremly low output, where all reads are buffered)
			self.logger.info("starting watchnchop in one minutes, then kill it after another 5 minutes")
			for i in range(60):
				if self.stoprequest.is_set():
					self.logger.error("watchnchop was NEVER STARTED: this thread was ordered to kill the watchnchop subprocess before it was started")
					return
				time.sleep(1)
			if self.conditions_met():
				self.process = subprocess.Popen(self.cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				self.logger.info("STARTED WATCHNCHOP with arguments: {}".format(self.cmd))
			else:
				self.logger.error("watchnchop NOT STARTED: directory {} still does not exist or contains no fastq files".format(self.observed_dir))
				return
			for i in range(300):
				if self.stoprequest.is_set():
					break
				time.sleep(1)
			self.process.terminate()
			self.logger.info("TERMINATED watchnchop process")

	def conditions_met(self):
		if os.path.exists(self.observed_dir):
			if [fn for fn in os.listdir(self.observed_dir) if fn.endswith('.fastq')]:
				return True
		return False

	def join(self, timeout=None):
		if timeout:
			self.exp_end.set()
		else:
			self.stoprequest.set()
		super(WatchnchopScheduler, self).join(timeout)


class StatsparserScheduler(threading.Thread):

	def __init__(self, update_interval, sample_dir, statsparser_args, channel):
		threading.Thread.__init__(self)
		if getattr(self, 'daemon', None) is None:
			self.daemon = True
		else:
			self.setDaemon(True)
		self.stoprequest = threading.Event()	# set when joined without timeout (eg if terminated with ctr-c)
		self.exp_end = threading.Event()		# set when joined with timeout (eg if experiment ended)
		self.logger = logging.getLogger(name='gw.w{}.sps'.format(channel+1))

		self.update_interval = update_interval
		self.sample_dir = sample_dir
		self.statsparser_args = statsparser_args
		self.page_opened = False

	def run(self):
		while not self.stoprequest.is_set() or self.exp_end.is_set():
			last_time = time.time()

			#stats_fns = [fn for fn in os.listdir(os.path.abspath(self.sample_dir)) if fn.endswith('stats.csv')] if os.path.exists(os.path.abspath(self.sample_dir)) else []
			#if stats_fns:
			#	cmd = [os.path.join(get_script_dir(),'statsparser'),
			#		   self.sample_dir,
			#		   '-q']
			#	cmd.extend(self.statsparser_args)
			#	cp = subprocess.run(cmd) # waits for process to complete
			#	if cp.returncode == 0:
			#		#self.logger.info("STATSPARSING COMPLETED")
			#		if not page_opened:
			#			basedir = os.path.abspath(self.sample_dir)
			#			fp = os.path.join(basedir, 'report.html')
			#			self.logger.info("OPENING " + fp)
			#			webbrowser.open('file://' + os.path.realpath(fp))
			#			page_opened = True
			#	else:
			#		self.logger.error("ERROR while running statsparser")
			#else:
			#	self.logger.warning("statsfile does not exist (yet?)")
			if self.conditions_met():
				self.update_report()
			else:
				self.logger.warning("no stats file in {} (yet), statsparser was not started".format(self.sample_dir))

			this_time = time.time()
			while (this_time - last_time < self.update_interval) and not self.stoprequest.is_set() or self.exp_end.is_set():
				time.sleep(1)
				this_time = time.time()
		# start statsparser a last time if the experiment ended
		if not self.stoprequest.is_set() and self.conditions_met():
			self.update_report()

	def conditions_met(self):
		stats_fns = [fn for fn in os.listdir(os.path.abspath(self.sample_dir)) if fn.endswith('stats.csv')] if os.path.exists(os.path.abspath(self.sample_dir)) else []
		if stats_fns:
			return True
		return False


	def update_report(self):
		self.logger.info("updating report...")
		cmd = [os.path.join(get_script_dir(),'statsparser'), #TODO: change to which() ?
			   self.sample_dir,
			   '-q']
		cmd.extend(self.statsparser_args)
		cp = subprocess.run(cmd) # waits for process to complete
		if cp.returncode == 0:
			#self.logger.info("STATSPARSING COMPLETED")
			if not self.page_opened:
				basedir = os.path.abspath(self.sample_dir)
				fp = os.path.join(basedir, 'report.html')
				self.logger.info("OPENING " + fp)
				webbrowser.open('file://' + os.path.realpath(fp))
				self.page_opened = True
		else:
			self.logger.error("ERROR while running statsparser")


	def join(self, timeout=None):
		#self.stoprequest.set()
		#super(StatsparserScheduler, self).join(timeout)
		if timeout:
			self.exp_end.set()
		else:
			self.stoprequest.set()
		super(StatsparserScheduler, self).join(timeout)


class Watcher():

	def __init__(self, minknow_log_basedir, channel, ignore_file_modifications, output_dir, data_basedir, 
				 statsparser_args, update_interval, watchnchop_args, bc_kws):
		self.q = queue.PriorityQueue()
		#self.watchnchop = not no_watchnchop
		self.watchnchop_args = watchnchop_args
		self.channel = channel
		self.output_dir = output_dir
		self.data_basedir = data_basedir
		self.statsparser_args = statsparser_args
		self.update_interval = update_interval
		#self.watchnchop_path = watchnchop_path
		self.bc_kws = bc_kws

		self.observed_dir = os.path.join(minknow_log_basedir, "GA{}0000".format(channel+1))
		self.event_handler = LogFilesEventHandler(self.q, ignore_file_modifications, channel)
		self.observer = Observer()

		self.observer.schedule(self.event_handler, 
							   self.observed_dir, 
							   recursive=False)
		self.observer.start()
		#self.logfile = open(os.path.join(os.path.abspath(os.path.dirname(self.watchnchop_path)),
		#								 "GA{}0000_watchnchop_log.txt".format(channel+1)), 'w')
		self.channel_status = ChannelStatus("GA{}0000".format(channel+1), channel)
		self.spScheduler = None
		self.wcScheduler = []
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
		global UPDATE_OVERVIEW
		dict_content = {}
		overwrite = False

		if   	"protocol_started"										in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True
			self.logger.info("PROTOCOL START")
			UPDATE_OVERVIEW = True
			self.channel_status.run_data['protocol_start'] = line[:23]

		elif	"protocol_finished" 									in line:
			self.logger.info("PROTOCOL END")
			UPDATE_OVERVIEW = True
			self.channel_status.run_data['protocol_end'] = line[:23]
			if self.channel_status.mux_scans:
				self.save_logdata()
			self.channel_status.reset_channel()
			if self.spScheduler.is_alive() if self.spScheduler else None:
				self.spScheduler.join(1.2)
			self.spScheduler = None
			if self.wcScheduler[-1].is_alive() if self.wcScheduler else None:
				self.wcScheduler[-1].join(1.2)
			#self.wcScheduler = None

		elif	"[engine/info]: : flowcell_discovered" 					in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True
			self.logger.info("FLOWCELL DISCOVERED")
			UPDATE_OVERVIEW = True
			self.channel_status.flowcell_disconnected()
			if self.spScheduler.is_alive() if self.spScheduler else None:
				self.spScheduler.join(1.2)
			self.spScheduler = None
			if self.wcScheduler[-1].is_alive() if self.wcScheduler else None:
				self.wcScheduler[-1].join(1.2)
			#self.wcScheduler = None

		elif   	"[engine/info]: : data_acquisition_started"				in line:# or \
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
			overwrite = True

		elif	"flowcell_disconnected"									in line:
			self.logger.info("FLOWCELL DISCONNECTED")
			UPDATE_OVERVIEW = True
			self.channel_status.flowcell_disconnected()


		if dict_content:
			self.channel_status.update(dict_content, overwrite)

	def parse_bream_log_line(self, line):
		global UPDATE_OVERVIEW
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
				UPDATE_OVERVIEW = True

		elif	"[user message]--> group "								in line.lower():
			for m in re.finditer("roup ([0-9]+) has ([0-9]+) active", line):
				self.channel_status.update_mux_group_totals(m.group(1), m.group(2), line[:23])
				UPDATE_OVERVIEW = True

		elif	"[user message]--> A total of"							in line:
			for m in re.finditer("total of ([0-9]+) single pores", line):
				self.channel_status.update_mux_group_totals("*", m.group(1), line[:23])
				UPDATE_OVERVIEW = True

		elif	"INFO - [user message]--> Finished Mux Scan"			in line:
			self.logger.info("MUX SCAN FINISHED")
			UPDATE_OVERVIEW = True
			self.channel_status.new_mux(line[:23])
			self.save_logdata()

		elif	"platform_qc.PlatformQCExperiment'> finished"			in line:
			self.logger.info("QC FINISHED")
			UPDATE_OVERVIEW = True

		elif	"INFO - STARTING MAIN LOOP"								in line:
			dict_content["sequencing_start_time"] = line[:23]
			self.logger.info("SEQUENCING STARTS")
			UPDATE_OVERVIEW = True

			#try to identify the path in which the experiment data is saved, relative to data_basedir
			self.channel_status.find_relative_path(self.data_basedir)

			#start watchnchop (porechop & filter & rsync)
			self.start_watchnchop()

			#start creation of plots at regular time intervals
			if self.spScheduler.is_alive() if self.spScheduler else None:
				self.spScheduler.join(1.1)
			sample_dir = os.path.join(self.output_dir,
									  'runs',
									  self.channel_status.run_data['user_filename_input'],
									  self.channel_status.run_data['user_filename_input'])#, #TODO: change to sample
									  #self.channel_status.run_data['run_id'] + '_stats.csv')
			self.logger.info('SCHEDULING update of stats-webpage every {0:.1f} minutes for sample dir {1}'.format(self.update_interval/1000, sample_dir))
			self.spScheduler = StatsparserScheduler(self.update_interval, 
													sample_dir, 
													self.statsparser_args, 
													self.channel)
			self.spScheduler.start()

		if dict_content:
			self.channel_status.update(dict_content, overwrite)

	def save_logdata(self):
		for key in ['experiment_type', 'run_id']:
			if not self.channel_status.run_data[key]:
				self.logger.warning("NOT SAVING REPORT for channel GA{}0000 because run_data is missing crucial attribute '{}'".format(self.channel+1, key))
				return
		for key in ['flowcell_id', 'asic_id_eeprom']:
			if not self.channel_status.flowcell[key]:
				self.logger.warning("NOT SAVING REPORT for channel GA{}0000 because flowcell is missing crucial attribute '{}'".format(self.channel+1, key))
				return

		fn = []
		if "qc" in self.channel_status.run_data['experiment_type'].lower():
			if self.channel_status.run_data['user_filename_input']:
				self.logger.warning("NOT SAVING REPORT for {} because it is not absolutely clear if it a qc or sequencing run".format(self.channel_status.run_data['run_id']))
				return
			fn.append("QC")
			fn.append(self.channel_status.flowcell['flowcell_id'])
			fn.append(self.channel_status.run_data['run_id'])
			target_dir = os.path.join(self.output_dir, 
									  'qc')
		else:
			if not self.channel_status.run_data['user_filename_input']:
				self.logger.warning("NOT SAVING REPORT because sequencing run is missing crucial attribute 'user_filename_input'")
				return
			#fn.append("SEQ")
			#fn.append(self.channel_status.run_data['user_filename_input'])
			#fn.append(self.channel_status.flowcell['flowcell_id'])
			fn.append(self.channel_status.run_data['run_id'])
			fn.append('logdata')
			target_dir = os.path.join(self.output_dir,
									  'runs', 
									  self.channel_status.run_data['user_filename_input'], 
									  self.channel_status.run_data['user_filename_input']) # TODO: change to sample
		fn = "_".join(fn) + ".json"

		self.logger.info("saving log data to file {}".format(os.path.join(target_dir, fn)))
		data = (self.channel_status.flowcell, self.channel_status.run_data, self.channel_status.mux_scans)
		if not os.path.exists(target_dir):
			os.makedirs(target_dir)
		with open( os.path.join(target_dir, fn), 'w') as f:
			print(json.dumps(data, indent=4), file=f)

		ALL_RUNS_LOCK.acquire()
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
		ALL_RUNS_LOCK.release()

	def start_watchnchop(self):
		for key in ['user_filename_input', 'relative_path', 'run_id', 'fastq_reads_per_file']:
			if not self.channel_status.run_data[key]:
				self.logger.warning("NOT executing watchnchop for channel GA{}0000 because run_data is missing crucial attribute '{}'".format(self.channel+1, key))
				return

		#if self.wcScheduler:
		#	if self.wcScheduler.is_alive():
		#		#self.logger.error("watchnchop was not started successfully for previous run!")
		#		self.wcScheduler.join(1.2)
		if self.wcScheduler[-1].is_alive() if self.wcScheduler else None:
			self.wcScheduler[-1].join(1.2)

		stats_fp = os.path.join(self.output_dir,
								'runs',
								self.channel_status.run_data['user_filename_input'],
								self.channel_status.run_data['user_filename_input'], #TODO: change to sample name
								"{}_stats.csv".format(self.channel_status.run_data['run_id']))
		self.wcScheduler.append(WatchnchopScheduler(self.data_basedir,
													self.channel_status.run_data['relative_path'],
													self.channel_status.run_data['user_filename_input'],
													self.channel_status.run_data['fastq_reads_per_file'],
													self.bc_kws,
													stats_fp,
													self.channel,
													self.watchnchop_args))
		self.wcScheduler[-1].start()
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


class RunsDirsEventHandler(FileSystemEventHandler):

	def __init__(self, observed_dir):
		super(RunsDirsEventHandler, self).__init__()
		self.observed_dir = os.path.abspath(observed_dir)
		self.logger = logging.getLogger(name='gw.reh')

	def on_moved(self, event):
		if event.is_directory or (self.depth(event.src_path) == 3 and event.src_path.endswith('.json')):
			self.logger.debug("moved {}, depth {}, \ndest {}".format(event.src_path, self.depth(event.src_path), event.dest_path))
			if self.observed_dir in event.dest_path and self.depth(event.dest_path) == self.depth(event.src_path):
				#self.logger.info("affected runs: {}".format(self.affected_runs(event.src_path)))
				self.reload_runs()
			else:
				self.on_deleted(event)

	def on_created(self, event):
		if event.is_directory:
			self.logger.debug("created directory {}, depth {}".format(event.src_path, self.depth(event.src_path)))
			if 1 <= self.depth(event.src_path) <= 2:
				self.reload_runs()
		elif self.depth(event.src_path) == 3 and event.src_path.endswith('.json'):
			self.logger.debug("created file {}, depth {}".format(event.src_path, self.depth(event.src_path)))
			self.reload_runs()

	def on_modified(self, event):
		if event.is_directory:
			self.logger.debug("modified directory {}, depth {}".format(event.src_path, self.depth(event.src_path)))

	def on_deleted(self, event):
		if event.is_directory:
			self.logger.debug("deleted directory {}, depth {}".format(event.src_path, self.depth(event.src_path)))
			if 1 <= self.depth(event.src_path) <= 2:
				self.reload_runs()
		elif self.depth(event.src_path) == 3 and event.src_path.endswith('.json'):
			self.logger.debug("deleted file {}, depth {}".format(event.src_path, self.depth(event.src_path)))
			self.reload_runs()

	def depth(self, src_path):
		src_path = os.path.abspath(src_path)
		return len(src_path.replace(self.observed_dir, '').strip('/').split('/'))

	def reload_runs(self):
		ALL_RUNS_LOCK.acquire()
		self.logger.info('deleting and re-importing all runs due to changes in the run directory')
		# delete sequencing runs
		to_delete = []
		for asic_id_eeprom in ALL_RUNS:
			for run_id in ALL_RUNS[asic_id_eeprom]:
				if 'equenc' in ALL_RUNS[asic_id_eeprom][run_id]['run_data']['experiment_type']:
					to_delete.append( (asic_id_eeprom, run_id) )
		for asic_id_eeprom, run_id in to_delete:
			del ALL_RUNS[asic_id_eeprom][run_id]
		#reload runs
		import_runs(self.observed_dir)
		UPDATE_OVERVIEW = True
		ALL_RUNS_LOCK.release()
		return

if __name__ == "__main__":
	main_and_args()
