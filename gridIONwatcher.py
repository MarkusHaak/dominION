import argparse, os
import sys
import time
import logging
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
from watchdog.events import FileSystemEventHandler
import multiprocessing as mp
from collections import OrderedDict
import re
import copy
import json

class readable_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class readable_writeable_dir(argparse.Action):
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

def main_and_args():
	
	#### args #####
	parser = argparse.ArgumentParser(description='''Parses a stats file containing information
													 about a nanopore sequencing run and creates
													 an in-depth report file including informative plots.''')

	parser.add_argument('-l', '--log_basedir',
						action=readable_dir,
						default='/var/log/MinKNOW',
						help='Path to the base directory of GridIONs log files, contains the manager log files. (default: /var/log/MinKNOW)')

	a_d = parser.add_argument('-d', '--database_dir',
						action=readable_writeable_dir,
						default='reports',
						help='Path to the base directory where reports will be safed. (default: reports)')

	parser.add_argument('-m', '--modified_as_created',
						action='store_true',
						help='''Handle file modifications as if the file was created, meaning that the latest changed file is seen as the current 
								log file.''')

	parser.add_argument('-v', '--verbose',
						action='store_true',
						help='Additional status information is printed to stdout.')

	parser.add_argument('-q', '--quiet', #TODO: implement
						action='store_true',
						help='No prints to stdout.')

	args = parser.parse_args()

	ns = argparse.Namespace()
	a_d(parser, ns, args.database_dir, 'no string') # call action

	global QUIET
	QUIET = args.quiet
	global VERBOSE
	VERBOSE = args.verbose

	#### main #####
	if not QUIET: print("#######################################")
	if not QUIET: print("######### grinIONwatcher {} #########".format(VERSION))
	if not QUIET: print("#######################################")
	if not QUIET: print("")

	watchers = []

	global ALL_RUNS

	logging.info("loading previous runs from database:")
	load_runs_from_database(args.database_dir)
	print()

	logging.info("starting watchers:")
	for channel in range(5):
		watchers.append(Watcher(args.log_basedir, channel, args.modified_as_created, args.database_dir))
	print()

	logging.info("entering main loop")
	try:
		while True:
			for watcher in watchers:
				watcher.check_q()
			time.sleep(1)
	except KeyboardInterrupt:
		logging.info("### Collected information ###")
		for watcher in watchers:
			watcher.observer.stop()
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
	for watcher in watchers:
		watcher.observer.join()

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
					print("ERROR: {} exists multiple times in database entry for flowcell {}!".format(run_id, flowcell_id))
					continue
			else:
				ALL_RUNS[flowcell_id] = {}
			
			ALL_RUNS[flowcell_id][run_id] = {'flowcell': flowcell,
											 'run_data': run_data,
											 'mux_scans': mux_scans}

			try:
				print('- loaded experiment "{}" performed on flowcell "{}" on "{}"'.format(run_data['experiment_type'], flowcell['flowcell_id'], run_data['protocol_start']))
			except:
				pass


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
						logging.info("changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
						self.flowcell[key] = content[key]
					else:
						if VERBOSE: logging.info("not changing the current value of {} ({}) to {}".format(key, self.flowcell[key], content[key]))
					continue
				else:
					self.flowcell[key] = content[key]
					logging.info("new value for {} : {}".format(key, content[key]))
					continue
			elif key in self.run_data:
				if self.run_data[key]:
					if overwrite:
						logging.info("changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
						self.run_data[key] = content[key]
					else:
						if VERBOSE: logging.info("not changing the current value of {} ({}) to {}".format(key, self.run_data[key], content[key]))
					continue
			self.run_data[key] = content[key]
			logging.info("new value for {} : {}".format(key, content[key]))

	def update_mux(self, group, channels, mux, timestamp):
		if self.mux_scans:
			if not group in self.mux_scans[-1]:
				self.mux_scans[-1][group] = []
			if len(self.mux_scans[-1][group]) < 4:
				self.mux_scans[-1][group].append(int(channels))
				if VERBOSE: logging.info("update mux: group {} has {} active channels in mux {}".format(group, channels, mux))

	def update_mux_group_totals(self, group, channels, timestamp):
		if not self.mux_scans:
			self.new_mux(timestamp)
		self.mux_scans[-1]['group {} total'.format(group)] = channels
		if VERBOSE: logging.info("update mux group totals: group {} has a total of {} active channels".format(group, channels))

	def new_mux(self, timestamp):
		if self.mux_scans:
			self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234" if i in self.mux_scans[-1]])
			logging.info("calculated mux total to {}".format(self.mux_scans[-1]['total']))
		self.mux_scans.append(copy.deepcopy(self.empty_mux))
		self.mux_scans[-1]['timestamp'] = timestamp
		if VERBOSE: logging.info("added new mux result")

	def flowcell_disconnected(self):
		self.flowcell = copy.deepcopy(self.empty_flowcell)
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []

	def run_finished(self):
		self.run_data = copy.deepcopy(self.empty_run_data)
		self.run_data['minion_id'] = self.minion_id
		self.mux_scans = []


class Watcher():

	def __init__(self, log_basedir, channel, modified_as_created, database_dir):
		self.q = mp.SimpleQueue()
		self.channel = channel
		self.database_dir = database_dir
		self.observed_dir = os.path.join(log_basedir, "GA{}0000".format(channel+1))
		self.event_handler = StatsFilesEventHandler(self.q, modified_as_created)
		self.observer = Observer()
		self.observer.schedule(self.event_handler, 
							   self.observed_dir, 
							   recursive=False)
		self.observer.start()
		print("...watcher for {} ready".format(self.observed_dir))

		self.channel_status = ChannelStatus("GA{}0000".format(channel+1))

	def check_q(self):
		if not self.q.empty:
			if VERBOSE: logging.info("Queue content for {}:".format(self.observed_dir))
		while not self.q.empty():
			content = self.q.get()
			#logging.info(content)
			if VERBOSE: print("received:", content)

			# case content is new data for channel report
			if isinstance(content[0], dict):
				self.channel_status.update(content[0], content[1])

			# case timestamped information
			else:
				timestamp = content[0]
				# case content is mux information
				if isinstance(content[1], tuple):
					if len(content[1]) == 3:
						self.channel_status.update_mux(content[1][0], content[1][1], content[1][2], timestamp)
					elif len(content[1]) == 2:
						self.channel_status.update_mux_group_totals(content[1][0], content[1][1], timestamp)
					elif len(content[1]) == 1:
						self.channel_status.update_mux_group_totals("*", content[1][0], timestamp)
				elif content[1] == "Finished Mux Scan":
					logging.info("MUXSCAN FINISHED")
					self.channel_status.new_mux(timestamp)
					self.save_report()
				elif content[1] == "sequencing start":
					#TODO: start porechop & filter & rsync
					#TODO: start regular creation of plots
					logging.info("SEQUENCING STARTS")
					pass
				elif content[1] == "flowcell discovered":
					logging.info("FLOWCELL DISCOVERED")
					self.channel_status.flowcell_disconnected()

				elif content[1] == "Finished QC":
					logging.info("QC FINISHED")
					#self.save_report()
					#self.channel_status.run_finished()
				elif content[1] == "new bream_log file":
					logging.info("NEW EXPERIMENT RUN")
					#self.channel_status.run_finished()
				elif content[1] == "flowcell disconnected":
					logging.info("FLOWCELL DISCONNECTED")
					self.channel_status.flowcell_disconnected()
				elif content[1] == "protocol started":
					logging.info("PROTOCOL STARTED")
					self.channel_status.run_data['protocol_start'] = content[0]
				elif content[1] == "protocol finished":
					logging.info("PROTOCOL FINISHED")
					self.channel_status.run_data['protocol_end'] = content[0]
					if self.channel_status.mux_scans:
						self.save_report()
					self.channel_status.run_finished()
				elif content[1] == "flowcell lookup":
					logging.info("LOADING PREVIOUS FLOWCELL RUNS")
					self.lookup_flowcell()

	def lookup_flowcell(self):
		try:
			flowcell_id = self.channel_status.flowcell['asic_id'] + self.channel_status.flowcell['asic_id_eeprom']
		except:
			logging.info("ERROR: flowcell lookup failed")
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
			logging.info("no entrys for this flowcell in the database")


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
			logging.info("ERROR: could not save report of channel GA{}0000".format(self.channel+1))




class OpenedFilesHandler():
	'''manages a set of opened files, reads their contents and 
	processes them lineby line. Incomplete lines are stored until
	they are "completed" by a newline character.'''
	open_files = {}

	def open_new_file(self, path):
		logging.info("Opening file {}".format(path))
		self.open_files[path] = [open(path, 'r'), ""]

	def close_file(self, path):
		if VERBOSE: logging.info("Attempting to close file {}".format(path))
		try:
			self.open_files[path][0].close()
		except:
			if VERBOSE: logging.info("File handle of file {} couldn't be closed".format(path))
		if path in self.open_files:
			del self.open_files[path]
		if VERBOSE: logging.info("Deleted entry in open_files for file {}".format(path))

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
			if VERBOSE: logging.info("File {} was created".format(event.src_path))
			basename = os.path.basename(event.src_path)
			if basename.startswith("control_server_log"):
				if self.control_server_log:
					self.file_handler.close_file(event.src_path)
					logging.info("Replacing current control_server_log file {} with {}".format(self.control_server_log, event.src_path))
					#TODO: sent report, ( and reset all opened files ? )
				self.control_server_log = event.src_path
				logging.info("New control_server_log file {}".format(self.control_server_log))
				process_function = self.parse_server_log_line
			elif basename.startswith("bream"):
				if self.bream_log:
					self.file_handler.close_file(event.src_path)
					logging.info("Replacing current bream_log file {} with {}".format(self.bream_log, event.src_path))
					#TODO: Find out if more than one bream log file can belong to a running experiment (probably not)
				self.bream_log = event.src_path
				logging.info("New bream_log file {}".format(self.bream_log))
				process_function = self.parse_bream_log_line
				self.q.put( ("", "new bream_log file") )
			else:
				if VERBOSE: logging.info("File {} is not of concern for this tool".format(event.src_path))
				return
			self.file_handler.open_new_file(event.src_path)
			#self.file_handler.process_lines_until_EOF(self, event.src_path)
			self.file_handler.process_lines_until_EOF(process_function, event.src_path)

	def on_deleted(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was deleted".format(event.src_path))
			#self.file_handler.close_file(event.src_path)
			if self.control_server_log == event.src_path:
				control_server_log = None
				logging.info("WARNING: Current control_server_log file {} was deleted!".format(event.src_path))
			elif self.bream_log == event.src_path:
				self.bream_log = None
				logging.info("EARNING: Current bream_log file {} was deleted".format(event.src_path))
			else:
				if VERBOSE: logging.info("File {} is not opened and is therefore not closed.".format(event.src_path))
				#return 
			self.file_handler.close_file(event.src_path)

	def on_modified(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was modified".format(event.src_path))
			if event.src_path in self.file_handler.open_files:
				if self.control_server_log == event.src_path:
					process_function = self.parse_server_log_line
				elif self.bream_log == event.src_path:
					process_function = self.parse_bream_log_line
				else:
					logging.info("WARNING: case not handled")
					return
				self.file_handler.process_lines_until_EOF(process_function, event.src_path)
			else:
				if self.modified_as_created:
					self.on_created(event)
				else:
					if VERBOSE: logging.info("File {} existed before this script was started".format(event.src_path))

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

		elif 	"asic_id_changed"										in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):

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
	VERBOSE = False
	QUIET = False
	VERSION = "v1.2"
	ALL_RUNS = {}
	logging.basicConfig(level=logging.INFO,
					    format='%(threadName)s: %(asctime)s - %(message)s',
					    datefmt='%Y-%m-%d %H:%M:%S')
	#q = mp.SimpleQueue()
	main_and_args()
