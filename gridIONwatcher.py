import sys
import time
import logging
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
from watchdog.events import FileSystemEventHandler

class OpenedFilesHandler():
	'''manages a set of opened files, reads their contents and 
	processes them lineby line. Incomplete lines are stored until
	they are "completed" by a newline character.'''
	open_files = {}

	def open_new_file(self, path):
		logging.info("Opening file {}".format(path))
		self.open_files[path] = [open(path, 'r'), ""]

	def close_file(self, path):
		logging.info("Attempting to close file {}".format(path))
		try:
			self.open_files[path][0].close()
		except:
			logging.info("File handle of file {} couldn't be closed".format(path))
		del open_files[path]
		logging.info("Deleted entry in open_files for file {}".format(path))

	def process_lines_until_EOF(self, parent, path):
		file = self.open_files[path][0]
		while 1:
			line = file.readline()
			if line == "":
				break
			elif line.endswith("\n"):
				line = (self.open_files[path][1] + line).strip()
				if line:
					parent.process(line)
				self.open_files[path][1] = ""
			else:
				#line potentially incomplete
				self.open_files[path][1] = self.open_files[path][1] + line


class ManagerEventHandler(FileSystemEventHandler):
	file_handler = OpenedFilesHandler()

	def on_moved(self, event):
	    pass

	def on_created(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was created".format(event.src_path))
			logging.info(type(event.src_path))
			self.file_handler.open_new_file(event.src_path)
			self.file_handler.process_lines_until_EOF(self, event.src_path)

	def on_deleted(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was deleted".format(event.src_path))
			self.file_handler.close_file(event.src_path)

	def on_modified(self, event):
		if not event.is_directory:
			if VERBOSE: logging.info("File {} was modified".format(event.src_path))
			if event.src_path in self.file_handler.open_files:
				self.file_handler.process_lines_until_EOF(self, event.src_path)
			else:
				if VERBOSE: logging.info("File {} existed before this script was started".format(event.src_path))

	def process(self, line):
		logging.info(line)
		

def main_and_args():
	return



if __name__ == "__main__":
	VERBOSE = True
	logging.basicConfig(level=logging.INFO,
					    format='%(threadName)s: %(asctime)s - %(message)s',
					    datefmt='%Y-%m-%d %H:%M:%S')
	path = sys.argv[1] if len(sys.argv) > 1 else '.'
	#logging_event_handler = LoggingEventHandler()
	manager_event_handler = ManagerEventHandler()
	manager_observer = Observer()
	manager_observer.schedule(manager_event_handler, path, recursive=False)
	manager_observer.start()
	logging.info("started")
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		manager_observer.stop()
	manager_observer.join()