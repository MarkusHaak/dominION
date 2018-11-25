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

class readable_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

def main_and_args():
	
	#### args #####
	argument_parser = argparse.ArgumentParser(description='''Parses a stats file containing information
													 about a nanopore sequencing run and creates
													 an in-depth report file including informative plots.''')

	argument_parser.add_argument('-l', '--log_basedir',
						action=readable_dir,
						default='/var/log/MinKNOW',
						help='Path to the base directory of GridIONs log files, contains the manager log files. (default: /var/log/MinKNOW)')

	argument_parser.add_argument('-v', '--verbose',
						action='store_true',
						help='No status information is printed to stdout.')

	argument_parser.add_argument('-q', '--quiet',
						action='store_true',
						help='No status information is printed to stdout.')


	args = argument_parser.parse_args()

	global QUIET
	QUIET = args.quiet
	global VERBOSE
	VERBOSE = args.verbose

	#### main #####
	path = sys.argv[1] if len(sys.argv) > 1 else '.'

	global SEQUENCING_RUNS
	watchers = []

	logging.info("starting watchers")
	for channel in range(5):
		watchers.append(Watcher(args.log_basedir, channel))

	logging.info("entering endless loop")
	try:
		while True:
			for watcher in watchers:
				watcher.check_q()
			time.sleep(1)
	except KeyboardInterrupt:
		for watcher in watchers:
			watcher.observer.stop()
			print('')
			print('')
			for key in watcher.channel_report.run_data:
				if watcher.channel_report.run_data[key]:
					print(key, ":\t\t", watcher.channel_report.run_data[key])
	for watcher in watchers:
		watcher.observer.join()


class ChannelReport():
	run_data = OrderedDict([
		('run_id', None),
		('user_filename_input', None), # user Run title
		('protocol_id', None),
		('minion_id', None),
		('start time', None),
		('stop time', None),
		('asic_id_eeprom', None),
		('asic_id', None),
		('flowcell_id', None),
		('acquisition_run_id', None),
		])

	empty_mux = OrderedDict([('1',[]), ('2',[]), ('3',[]), ('4',[])])

	def __init__(self, minion_id):
		self.run_data = copy.deepcopy(self.run_data)
		self.mux_scans = []
		self.run_data['minion_id'] = minion_id

	def update(self, content, overwrite=False):
		for key in content:
			if key in self.run_data:
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
			if len(self.mux_scans[-1][group]) < 4:
				self.mux_scans[-1][group].append(int(channels))
				if VERBOSE: logging.info("update mux: group {} has {} active channels in mux {}".format(group, channels, mux))
		#if group == "4" and mux == "4":
		#	self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234"])
		#	logging.info("calculated mux total")
		#	self.mux_scans[-1]['timestamp'] = timestamp
		#	self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234"])
		#	self.mux_scans.append(copy.deepcopy(empty_mux))

	def new_mux(self, timestamp):
		if self.mux_scans:
			self.mux_scans[-1]['total'] = sum([sum(self.mux_scans[-1][i]) for i in "1234"])
			logging.info("calculated mux total to {}".format(self.mux_scans[-1]['total']))
		self.mux_scans.append(copy.deepcopy(self.empty_mux))
		self.mux_scans[-1]['timestamp'] = timestamp
		if VERBOSE: logging.info("added new mux result")





class Watcher():

	def __init__(self, log_basedir, channel):
		self.q = mp.SimpleQueue()
		self.channel = channel
		self.observed_dir = os.path.join(log_basedir, "GA{}0000".format(channel+1))
		self.event_handler = StatsFilesEventHandler(self.q)
		self.observer = Observer()
		self.observer.schedule(self.event_handler, 
							   self.observed_dir, 
							   recursive=False)
		self.observer.start()
		logging.info("...watcher for {} ready".format(self.observed_dir))

		self.channel_report = ChannelReport("GA{}0000".format(channel+1))

	def check_q(self):
		if not self.q.empty:
			if VERBOSE: logging.info("Queue content for {}:".format(self.observed_dir))
		while not self.q.empty():
			content = self.q.get()
			#logging.info(content)
			if VERBOSE: print("received:", content)

			# case content is new data for channel report
			if isinstance(content[0], dict):
				self.channel_report.update(content[0], content[1])

			# case timestamped information
			else:
				timestamp = content[0]
				# case content is mux information
				if isinstance(content[1], tuple):
					self.channel_report.update_mux(content[1][0], content[1][1], content[1][2], timestamp)
				elif content[1] == "Finished Mux Scan":
					self.channel_report.new_mux(timestamp)
				elif content[1] == "sequencing start":
					#TODO: start porechop & filter & rsync
					logging.info("SEQUENCING STARTS")
					pass
				elif content[1] == "flowcell discovered":
					logging.info("FLOWCELL DISCOVERED")


			#print(self.channel_report.data)



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
		del open_files[path]
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

	def __init__(self, q):
		super(StatsFilesEventHandler, self).__init__()
		self.q = q

	def on_moved(self, event):
	    pass

	def on_created(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was created".format(event.src_path))
			basename = os.path.basename(event.src_path)
			if basename.startswith("control_server_log"):
				if self.control_server_log:
					self.file_handler.close_file(event.src_path)
					if VERBOSE: logging.info("Replacing current control_server_log file {} with {}".format(self.control_server_log, event.src_path))
					#TODO: sent report
				self.control_server_log = event.src_path
				if VERBOSE: logging.info("New control_server_log file {}".format(self.control_server_log))
				process_function = self.parse_server_log_line
			elif basename.startswith("bream"):
				#TODO: handle new Experiment?
				if self.bream_log:
					self.file_handler.close_file(event.src_path)
					if VERBOSE: logging.info("Replacing current bream_log file {} with {}".format(self.bream_log, event.src_path))
				self.bream_log = event.src_path
				if VERBOSE: logging.info("New bream_log file {}".format(self.bream_log))
				process_function = self.parse_bream_log_line
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
				if VERBOSE: logging.info("File {} existed before this script was started".format(event.src_path))

	def parse_server_log_line(self, line):
		dict_content = {}
		overwrite = False

		if 		"[mgmt/info]: : active_device_set" 						in line or \
		   		"[script/info]: : protocol_started"						in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)

		elif	"[engine/info]: : flowcell_discovered" 					in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
				overwrite = True
			self.q.put( (line[:23], "flowcell discovered") )

		elif   	"[engine/info]: : data_acquisition_started"				in line or \
		   		"[saturation_control/info]: : saturation_mode_changed" 	in line:
			for m in re.finditer('([^\s,]+) = ([^\s,]+)', line):
				dict_content[m.group(1)] = m.group(2)
				overwrite = True
		if dict_content:
			self.q.put( (dict_content, overwrite) )


	def parse_bream_log_line(self, line):
		dict_content = {}
		overwrite = False

		if 		"root - INFO - argument"								in line:
			for m in re.finditer("([^\s,]+) was set to ([^\s,]+)", line): 
				dict_content[m.group(1)] = m.group(2)

		elif 	"INFO - Adding the following context_tags:" 			in line or \
				"INFO - Context tags set to"							in line:
			for m in re.finditer("'([^\s,]+)': u?'([^\s,]+)'", line):
				dict_content[m.group(1)] = m.group(2)
			if 'filename' in dict_content:
				dict_content['flowcell_id'] = dict_content['filename'].split("_")[2]

		elif	"bream.core.base.database - INFO - group"				in line:
			for m in re.finditer("group ([0-9]+) has ([0-9]+) channels in mux ([0-9]+)", line):
				self.q.put( (line[:23], (m.group(1), m.group(2), m.group(3))) )

		elif	"INFO - [user message]--> Finished Mux Scan"			in line:
			self.q.put( (line[:23], "Finished Mux Scan") )

		elif	"INFO - STARTING MAIN LOOP"								in line:
			dict_content["sequencing_start_time"] = line[:23]
			self.q.put( (line[:23], "sequencing start") )

		if dict_content:
			self.q.put( (dict_content, overwrite) )



if __name__ == "__main__":
	VERBOSE = False
	QUIET = False
	logging.basicConfig(level=logging.INFO,
					    format='%(threadName)s: %(asctime)s - %(message)s',
					    datefmt='%Y-%m-%d %H:%M:%S')
	#q = mp.SimpleQueue()
	SEQUENCING_RUNS = {}
	main_and_args()
