import itertools, argparse, os
from time import gmtime, strftime
import numpy as np
import dateutil.parser
from datetime import datetime
import sys
import pandas as pd
from collections import OrderedDict
import functools

class readable_file(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isfile(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a file'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class writeable_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
		if not os.access(to_test, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class parse_time_intervals(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		try:
			intervals = [int(i) for i in values.strip().strip(',').split(',')]
		except:
			raise argparse.ArgumentTypeError('ERR: {} is not in a valid format for a time interval'.format(intervals))
		setattr(namespace,self.dest,intervals)



def main_and_args():
	
	#### args #####
	argument_parser = argparse.ArgumentParser(description='''Parses a stats file containing information
													 about a nanopore sequencing run and creates
													 an in-depth report file including informative plots.''')

	argument_parser.add_argument('statsfile',
						action=readable_file,
						help='''Path to the stats file containing all necessary information
								 about the sequencing run. Requires a CSV file with "\t" as 
								 seperator, no header and the following columns in given order:
								 read_id, length, qscore, mean_gc, Passed/tooShort, 
								 read_number, pore_index, timestamp, barcode''')

	argument_parser.add_argument('-o', '--outdir',
						action=writeable_dir,
						default=None,
						help='Path to a directory in which the report files and folders will be saved.')

	argument_parser.add_argument('-q', '--quiet',
						action='store_true',
						help='No status information is printed to stdout.')

	argument_parser.add_argument('--max_bins', 
						type=int,
						default=24,
						help='maximum number of bins for box plots (default: 24)')

	argument_parser.add_argument('--min_bins', 
						type=int,
						default=10,
						help='minimum number of bins for box plots (default: 10)')

	argument_parser.add_argument('--time_intervals',
						action=parse_time_intervals,
						default=[30,60,90,120,240],
						help='time intervals in minutes available for box plots. (default: 30,60,90,120,240)')

	args = argument_parser.parse_args()

	if not args.outdir:
		args.outdir = os.path.abspath(os.path.dirname(args.statsfile))
		if not os.path.isdir(args.outdir):
			raise argparse.ArgumentTypeError('ERR: {} is not a valid directory'.format(args.outdir))
		if not os.access(args.outdir, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))

	global QUIET
	QUIET = args.quiet
	#### main #####

	tprint("Parsing stats file")
	df = parse_stats(args.statsfile)

	tprint("Creating stats table")
	stats_df = stats_table(df)

	tprint("Parsing stats table to html")
	html_stats_df = stats_df.to_html()

	with open("test.html", 'w') as outfile:
		print(html_stats_df, file=outfile)


def avgN50longest(series):
	#return series.sort_values(0, ascending=False)[:int(series.size/2)].mean()
	return series.nlargest(int(series.size/2)).mean()

def tprint(*args, **kwargs):
	if not QUIET:
		print("["+strftime("%H:%M:%S", gmtime())+"]"+" ".join(map(str,args)), **kwargs)

def stats_table(df):
	grouped = df.groupby(['barcode', 'filter'])

	#groups = list(pd.DataFrame(grouped['kb'].count()).index)

	data = OrderedDict()
	# keys equal headers in html
	output_df = pd.DataFrame(OrderedDict((('reads' ,				grouped['kb'].count()), 
							 			 ('kbs' ,					grouped['kb'].sum()), 
							 			 ('mean quality' ,			grouped['qual'].mean()), 
							 			 ('mean GC' ,				grouped['gc'].mean()),
							 			 ('avg length' ,			grouped['kb'].mean()),
							 			 ('median length' ,			grouped['kb'].median()),
							 			 ('mean length longest N50',grouped['kb'].agg(avgN50longest)),
							 			 ('longest' ,				grouped['kb'].max())
							 			 )))
	#tprint("\n",output_df.round(2))
	return output_df.round(2)

def parse_stats(fp):
	df = pd.read_csv(fp, 
					 sep='\t', 
					 header=None, 
					 names="id kb qual gc filter pore_num pore time barcode".split(" "), 
					 index_col=[5,3], 
					 usecols=[1,2,3,4,7,8],
					 converters={'time':(lambda x: pd.Timestamp(x)), 'kb':(lambda x: float(x)/1000)}, 
					 dtype={'qual':np.float32, 'gc':np.float32})
	start_time = df['time'].min(axis=1)
	df['time'] = (df['time'] - start_time).dt.total_seconds()
	#tprint(df) 
	return df

#def parse_stats(fp, quiet):
#	start_time = None
#	stop_time = None
#
#	data = {}
#	tot_reads = 0
#	with open(fp, 'rU') as statsf:
#		for line in statsf.readlines():
#			r_id, r_len, r_q, r_gc, r_pass, r_num, p_ind, r_time, r_bar = line.strip().split('\t')
#			#       ok    ok   ok     ok                    ok     ok 
#
#			r_len = int(r_len)
#			r_q = float(r_q)
#			r_gc = float(r_gc)
#			#r_num = int(r_num)
#			#p_ind = int(p_ind)
#			r_time = dateutil.parser.parse(r_time)
#
#			# find first and last read
#			if not start_time:
#				start_time = r_time
#				stop_time = r_time
#			if start_time > r_time:
#				start_time = r_time
#			if stop_time < r_time:
#				stop_time = r_time
#
#			if r_bar not in data:
#				data[r_bar] = {'pass' : [], 'fail' : []}
#			if (r_pass == "Passed" or r_pass == "passed"):
#				data[r_bar]['pass'].append( [r_time, r_len, r_q, r_gc] )
#			else:
#				data[r_bar]['fail'].append( [r_time, r_len, r_q, r_gc] )
#
#			tot_reads += 1
#			if not quiet:
#				if tot_reads % 50000 == 0:
#					print("|", end="")
#					sys.stdout.flush()
#
#	tprint("\nParsed data of {} reads".format(tot_reads))
#	tprint("Converting time to seconds since run started")
#	
#	tot_reads = 0
#	for bc in data:
#		for tag in ['pass', 'fail']:
#			for i,read in enumerate(data[bc][tag]):
#				read[0]	= int((r_time - start_time).total_seconds())
#				data[bc][tag][i] = tuple(read)
#
#				tot_reads += 1
#				if not quiet:
#					if tot_reads % 50000 == 0:
#						print("|", end="")
#						sys.stdout.flush()
#
#			dt = np.dtype=[('seconds', 'u8'), ('length', 'u4'), ('quality', 'f4'), ('gc', 'f4')]
#			data[bc][tag] = np.array(data[bc][tag],
#									 dtype=dt)
#			tprint(np.shape(data[bc][tag]))
#
#
#
#	return data




if __name__ == '__main__':
	QUIET = False
	main_and_args()