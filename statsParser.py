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

	html_stats_df = make_html_table(stats_df)

	with open("test.html", 'w') as outfile:
		print(html_stats_df, file=outfile)


def avgN50longest(series):
	#return series.sort_values(0, ascending=False)[:int(series.size/2)].mean()
	return series.nlargest(int(series.size/2)).mean()

def tprint(*args, **kwargs):
	if not QUIET:
		print("["+strftime("%H:%M:%S", gmtime())+"]"+" ".join(map(str,args)), **kwargs)

def stats_table(df):
	subgrouped = df.groupby(['barcode', 'subset'])

	#groups = list(pd.DataFrame(subgrouped['kb'].count()).index)
	#df_reindexed = df.reindex()
	grouped = df.groupby(['barcode'])

	data = OrderedDict()
	# keys equal headers in html
	subgrouped_output_df = pd.DataFrame(OrderedDict((('reads' ,					subgrouped['kb'].count()), 
							 			 			 ('kbs' ,					subgrouped['kb'].sum()), 
							 			 			 ('mean quality' ,			subgrouped['qual'].mean()), 
							 			 			 ('mean GC' ,				subgrouped['gc'].mean()),
							 			 			 ('avg length' ,			subgrouped['kb'].mean()),
							 			 			 ('median length' ,			subgrouped['kb'].median()),
							 			 			 ('mean length longest N50',subgrouped['kb'].agg(avgN50longest)),
							 			 			 ('longest' ,				subgrouped['kb'].max())
							 			 			 )))
	grouped_output_df = pd.DataFrame(OrderedDict((('reads' ,					grouped['kb'].count()), 
							 			 		  ('kbs' ,						grouped['kb'].sum()), 
							 			 		  ('mean quality' ,				grouped['qual'].mean()), 
							 			 		  ('mean GC' ,					grouped['gc'].mean()),
							 			 		  ('avg length' ,				grouped['kb'].mean()),
							 			 		  ('median length' ,			grouped['kb'].median()),
							 			 		  ('mean length longest N50',	grouped['kb'].agg(avgN50longest)),
							 			 		  ('longest' ,					grouped['kb'].max())
							 			 		  )))
	#print(pd.concat([subgrouped_output_df,grouped_output_df]))
	#print(grouped_output_df)
	#print(grouped_output_df.reindex([(index, 'all') for index in list(grouped_output_df.index)]))
	#grouped_output_df = grouped_output_df.reindex([(index, 'all') for index in list(grouped_output_df.index)])
	#print(pd.concat([subgrouped_output_df,grouped_output_df]))

	#print(list(zip(list(grouped_output_df.index), ['all' for i in grouped_output_df.index])))
	index = pd.MultiIndex.from_tuples(list(zip(list(grouped_output_df.index), ['all' for i in grouped_output_df.index])), names=['barcode', 'subset'])
	#print(index)
	#mod_grouped_output_df = pd.Series(grouped_output_df, index=index)
	grouped_output_df.index = index
	#print(grouped_output_df)
	concat_res = pd.concat([subgrouped_output_df,grouped_output_df])
	#print(concat_res)
	#index = pd.MultiIndex.from_tuples(list(concat_res.index))
	#concat_res = concat_res.reindex(['Passed','tooShort','BadQual','all'], level='subset')
	concat_res = concat_res.sort_index(level=['barcode', 'subset'])
	concat_res = concat_res.reindex(['Passed','tooShort','BadQual','all'], level='subset')
	#print(concat_res)


	return concat_res

def make_html_table(df):
	df = df.round(2)
	#df = df.reindex(['Passed','tooShort','BadQual','all'], level='subset')
	
	return df.to_html()

def parse_stats(fp):
	df = pd.read_csv(fp, 
					 sep='\t', 
					 header=None, 
					 names="id kb qual gc subset pore_num pore time barcode".split(" "), 
					 index_col=[5,3], 
					 usecols=[1,2,3,4,7,8],
					 converters={'time':(lambda x: pd.Timestamp(x)), 'kb':(lambda x: float(x)/1000)}, 
					 dtype={'qual':float, 'gc':float})
	start_time = df['time'].min(axis=1)
	df['time'] = (df['time'] - start_time).dt.total_seconds()
	return df

if __name__ == '__main__':
	QUIET = False
	main_and_args()