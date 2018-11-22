import itertools, argparse, os
from time import gmtime, strftime
import numpy as np
import dateutil.parser
from datetime import datetime
import sys
import pandas as pd
from collections import OrderedDict
import functools

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.lines as mlines
import copy
from mpl_toolkits import axes_grid1
import matplotlib.gridspec as gridspec

import warnings
warnings.filterwarnings("ignore")

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

class parse_kb_intervals(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		try:
			intervals = [float(i) for i in values.strip().strip(',').split(',')]
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

	argument_parser.add_argument('--time_intervals',
						action=parse_time_intervals,
						default=[30,60,90,120,240],
						help='time intervals in minutes available for binning. (default: 30,60,90,120,240)')

	argument_parser.add_argument('--kb_intervals',
						action=parse_kb_intervals,
						default=[0.1,0.5,1.0,2.0],
						help='kb intervals in minutes available for binning. (default: 0.1,0.5,1.0,2.0)')

	args = argument_parser.parse_args()

	if not args.outdir:
		args.outdir = os.path.abspath(os.path.dirname(args.statsfile))
		if not os.path.isdir(args.outdir):
			raise argparse.ArgumentTypeError('ERR: {} is not a valid directory'.format(args.outdir))
		if not os.access(args.outdir, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))

	if not os.path.isdir(os.path.join(args.outdir, 'plots')):
		os.makedirs(os.path.join(args.outdir, 'plots'))

	global QUIET
	QUIET = args.quiet

	#### main #####

	tprint("Parsing stats file")
	df = parse_stats(args.statsfile)

	tprint("Creating stats table")
	stats_df = stats_table(df)

	tprint("Parsing stats table to html")
	html_stats_df = make_html_table(stats_df)

	#with open("test.html", 'w') as outfile:
	#	print(html_stats_df, file=outfile)

	tprint("Creating boxplots")
	interval, num_bins = get_lowest_possible_interval(args.time_intervals,
												 args.max_bins, 
												 df['time'].max())
	tprint(interval, num_bins)
	subgrouped = df.groupby(['barcode', 'subset'])
	indexes = list(pd.DataFrame(subgrouped['kb'].count()).index)
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('time', axis=0, ascending=True)
		#print(sub_df)
		bin_edges = get_bin_edges(sub_df['time'], interval)
		#time_bins = get_bins(sub_df['time'], bin_edges)
		for col in sub_df:
			if col != 'time':
				tprint("plotting {}, {}: {}".format(bc, subset, col))
				bins = get_bins(sub_df[col], bin_edges)
				#print([len(bin) for bin in bins])
				intervals = [i*interval for i in range(num_bins)]
				#print(bins)
				#print(intervals)
				boxplot(bins, intervals, col, os.path.join(args.outdir, "plots", "{}_{}_{}_boxplot".format(bc, subset, col)))

	


def boxplot(bins, intervals, ylabel, dest):
	f = plt.figure()
	fig = plt.gcf()

	gs0 = gridspec.GridSpec(2, 1, width_ratios=[1], height_ratios=[0.3,1])
	gs0.update(wspace=0.01, hspace=0.01)

	ax0 = plt.subplot(gs0[0, 0])
	ax1 = plt.subplot(gs0[1, 0])

	#fig1, ax1 = plt.subplots()
	#ax1.set_title('mean qscore over time')
	ax1.boxplot(bins, showfliers=False)
	ax1.set_xlabel("sequencing time [h]")
	ax1.set_ylabel(ylabel)
	ax1.set_xticks([i+0.5 for i in range(len(intervals))])
	xticklabels = ["{0:.1f}".format(i/3600) for i in intervals]
	for i in range(1,len(xticklabels), 2):
		xticklabels[i] = ""
	ax1.set_xticklabels(xticklabels)
	ax1.tick_params(top=False, bottom=True, left=True, right=False,
				   labeltop=False, labelbottom=True)
	ax1.yaxis.grid(color="black", alpha=0.1)
	ax1.set_axisbelow(True)

	ax0.bar([i for i in range(len(bins))], [len(i) for i in bins], align='center', color='grey')
	ax0.set_xlim([0.5, len(bins)+0.5])
	ax0.set_ylim([0,max([len(i) for i in bins])])
	ax0.tick_params(top=False, bottom=False, left=True, right=False,
				   labeltop=False, labelbottom=False)
	#for edge, spine in ax0.spines.items():
	#	spine.set_visible(False)
	#ax0.spines['left'].set_visible(True)
	#ax0.spines['right'].set_visible(True)
	ax0.set_ylabel("reads")
	ax0.set_xticklabels([])
	ax0.yaxis.grid(color="black", alpha=0.1)
	ax0.set_axisbelow(True)

	fig.tight_layout()
	plt.savefig(dest)


def get_lowest_possible_interval(time_intervals, max_bins, max_seconds):
	time_interval = None
	num_bins = None
	for interval in time_intervals:
		num_bins = (max_seconds // (interval*60))+1
		if num_bins <= max_bins:
			time_interval = interval*60
			break
	if not time_interval:
		time_interval = time_intervals[-1]
	return time_interval, int(num_bins)

def avgN50longest(series):
	#return series.sort_values(0, ascending=False)[:int(series.size/2)].mean()
	return series.nlargest(int(series.size/2)).mean()

def tprint(*args, **kwargs):
	if not QUIET:
		print("["+strftime("%H:%M:%S", gmtime())+"] "+" ".join(map(str,args)), **kwargs)

def stats_table(df):
	subgrouped = df.groupby(['barcode', 'subset'])

	#groups = list(pd.DataFrame(subgrouped['kb'].count()).index)
	grouped = df.groupby(['barcode'])

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

	# concat both to one DataFrame, sorted by the indexes
	index = pd.MultiIndex.from_tuples(list(zip(list(grouped_output_df.index), ['all' for i in grouped_output_df.index])), names=['barcode', 'subset'])
	grouped_output_df.index = index
	concat_res = pd.concat([subgrouped_output_df,grouped_output_df])
	concat_res = concat_res.sort_index(level=['barcode', 'subset'])
	concat_res = concat_res.reindex(['Passed','tooShort','BadQual','all'], level='subset')

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

def get_bin_edges(sorted_df, interval):
	edge = interval
	edges = [0]
	for i,val in enumerate(sorted_df):
		if val > edge:
			edges.append( i )
			edge += interval
	edges.append(sorted_df.size)
	return edges

def get_bins(df, bin_edges):
	bins = []
	for i in range(1,len(bin_edges)):
		bins.append(list(df[bin_edges[i-1]:bin_edges[i]]))
	return bins

if __name__ == '__main__':
	QUIET = False
	main_and_args()