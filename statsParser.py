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
import re
from shutil import copyfile

import warnings
warnings.filterwarnings("ignore")

QUIET = False
TICKLBLS = 6
SECS_TO_HOURS = 3600.
VERSION = "v2.0"

class readable_file(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isfile(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a file'.format(to_test))
		if not os.access(to_test, os.R_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not readable'.format(to_test))
		setattr(namespace,self.dest,to_test)

class readable_dir(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		to_test=values
		if not os.path.isdir(to_test):
			raise argparse.ArgumentTypeError('ERR: {} is not a directory'.format(to_test))
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

def get_argument_parser():
	argument_parser = argparse.ArgumentParser(description='''Parses a stats file containing information
													 about a nanopore sequencing run and creates
													 an in-depth report file including informative plots.''')

	if __name__ == '__main__':
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
						default=[1,2,5,10,20,30,60,90,120,240],
						help='time intervals in minutes available for binning. (default: 1,2,5,10,20,30,60,90,120,240)')

	argument_parser.add_argument('--kb_intervals',
						action=parse_kb_intervals,
						default=[.5,1.,2.,5.],
						help='kb intervals available for binning. (default: .5,1.,2.,5.)')

	argument_parser.add_argument('--gc_intervals',
						action=parse_kb_intervals,
						default=[.2,.5,1.,2.,5.],
						help='kb intervals available for binning. (default: .2,.5,1.,2.,5.)')

	argument_parser.add_argument('--matplotlib_style',
						default='default',
						help='matplotlib style string that influences all colors and plot appearances. (default: default)')

	argument_parser.add_argument('--website_refresh_rate',
						type=int,
						default=60,
						help='refresh rate in seconds. (default: 60)')

	argument_parser.add_argument('--html_bricks_dir',
						action=readable_dir,
						default='html_bricks')

	# the following should only be set if statsParser is called directly:
	if __name__ == '__main__':
		argument_parser.add_argument('--user_filename_input',
							default='Run#####_MIN###_KIT###')

		argument_parser.add_argument('--minion_id',
							default='GA#0000')

		argument_parser.add_argument('--flowcell_id',
							default='FAK#####')

		argument_parser.add_argument('--protocol_start',
							default='YYYY-MM-DD hh:mm:ss.ms')

	return argument_parser

def parse_args(argument_parser, ext_args=None):

	if ext_args:
		args = argument_parser.parse_args(ext_args)
	else:
		args = argument_parser.parse_args()

	if not args.outdir:
		args.outdir = os.path.abspath(os.path.dirname(args.statsfile))
		if not os.path.isdir(args.outdir):
			raise argparse.ArgumentTypeError('ERR: {} is not a valid directory'.format(args.outdir))
		if not os.access(args.outdir, os.W_OK):
			raise argparse.ArgumentTypeError('ERR: {} is not writeable'.format(to_test))

	if not os.path.isdir(os.path.join(args.outdir, 'res', 'plots')):
		os.makedirs(os.path.join(args.outdir, 'res', 'plots'))

	if not os.path.exists('html_bricks') or not os.path.isdir('html_bricks'):
		raise argparse.ArgumentTypeError('ERR: directory "html_bricks" does not exist'.format(args.outdir))
		for brick in ["barcode_brick.html",
					  "bottom_brick.html",
					  "overview_brick.html",
					  "top_brick.html"]:
			if not os.path.isfile(os.path.join('html_bricks', 'html_bricks')):
				raise argparse.ArgumentTypeError('ERR: file {} does not exist'.format(os.path.join('html_bricks', 'html_bricks')))

	args.time_intervals = [i*60 for i in args.time_intervals]

	try:
		matplotlib.style.use(args.matplotlib_style)
	except:
		raise argparse.ArgumentTypeError('ERR: {} is not a valid matplotlib style'.format(args.matplotlib_style))

	#args.kb_intervals = list(np.array(args.kb_intervals)*1000)

	return args

def main(args):
	#### main #####
	global QUIET
	QUIET = args.quiet

	if not QUIET: print("#######################################")
	if not QUIET: print("#########   statsParser {}  #########".format(VERSION))
	if not QUIET: print("#######################################")
	if not QUIET: print("")

	tprint("Parsing stats file")
	df = parse_stats(args.statsfile)

	tprint("Creating stats table")
	stats_df = stats_table(df)

	#with open(os.path.join(args.outdir, "results.html"), 'w') as outfile:
	#	print(html_stats_df, file=outfile)

	subgrouped = df.groupby(['barcode', 'subset'])
	indexes = list(pd.DataFrame(subgrouped['bases'].count()).index)

	#######

	tprint("Creating boxplots")
	#interval, offset, num_bins = get_lowest_possible_interval(args.time_intervals,
	#											 args.max_bins, 
	#											 df['time'].min(), 
	#											 df['time'].max())
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('time', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval(args.time_intervals,
																  args.max_bins, 
																  sub_df['time'].min(), 
																  sub_df['time'].max())
		bin_edges, offsetti = get_bin_edges(sub_df['time'], interval)
		for col in sub_df:
			if col != 'time':
				tprint("...plotting {}, {}: {}".format(bc, subset, col))
				bins = get_bins(sub_df[col], bin_edges)
				intervals = [(offset+i)*interval for i in range(len(bins))]
				boxplot(bins, intervals, interval, col, os.path.join(args.outdir, 'res', "plots", "boxplot_{}_{}_{}".format(bc, subset, col)))
	
	#######
	
	tprint("Creating kb-bins barplots")
	#interval, offset, num_bins = get_lowest_possible_interval(list(np.array(args.kb_intervals)*1000),
	#											 args.max_bins, 
	#											 df['bases'].min(), 
	#											 df['bases'].max())
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('bases', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval(list(np.array(args.kb_intervals)*1000),
																  args.max_bins, 
																  sub_df['bases'].min(), 
																  sub_df['bases'].max())
		bin_edges, offsetti = get_bin_edges(sub_df['bases'], interval)
		tprint("...plotting {}, {}".format(bc, subset))
		bins = get_bins(sub_df['bases']/1000000., bin_edges)
		intervals = [((offset+i)*interval)/1000. for i in range(len(bins))]
		barplot(bins, intervals, interval/1000., 'kb', 'Mb', os.path.join(args.outdir, 'res', "plots", "barplot_kb-bins_{}_{}".format(bc, subset)))

	tprint("Creating qc-bins barplots")

	#######

	#interval, offset, num_bins = get_lowest_possible_interval(args.gc_intervals,
	#											 args.max_bins, 
	#											 df['gc'].min(), 
	#											 df['gc'].max())
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('gc', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval(args.gc_intervals,
												 				  args.max_bins, 
												 				  sub_df['gc'].min(), 
												 				  sub_df['gc'].max())
		bin_edges, offsetti = get_bin_edges(sub_df['gc'], interval)
		tprint("...plotting {}, {}".format(bc, subset))
		bins = get_bins(sub_df['bases']/1000000., bin_edges)
		intervals = [(offset+i)*interval for i in range(len(bins))]
		barplot(bins, intervals, interval, '%', 'Mb', os.path.join(args.outdir, 'res', "plots", "barplot_gc-bins_{}_{}".format(bc, subset)))
	
	#######
	
	#tprint("Creating lineplots with two y-axes")
	#subset_grouped = df.groupby(['subset'])
	#
	#tprint("...plotting {}".format('all'))
	#sorted_df = df.sort_values('time', axis=0, ascending=True)
	#lineplot_2y(sorted_df['time']/SECS_TO_HOURS, sorted_df['bases']/1000000., os.path.join(args.outdir, 'res', "plots", "lineplot_{}".format('all')))
	#
	#for subset in set([j for i,j in indexes]):
	#	tprint("...plotting {}".format(subset))
	#	sorted_df = subset_grouped.get_group(subset).sort_values('time', axis=0, ascending=True)
	#	lineplot_2y(sorted_df['time']/SECS_TO_HOURS, sorted_df['bases']/1000000., os.path.join(args.outdir, 'res', "plots", "lineplot_{}".format(subset)) )
	
	#######
	
	tprint("Creating multi lineplots with one y-axis")
	subset_grouped = df.groupby(['subset'])
	
	reads_dfs = []
	bases_dfs = []
	
	sorted_df = df.sort_values('time', axis=0, ascending=True)
	reads_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
					  pd.DataFrame({'count':range(1,sorted_df['time'].size+1)}),
					  'all') )
	bases_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
					  (sorted_df['bases']/1000000000.).expanding(1).sum(),
					  'all') )
	for subset in set([j for i,j in indexes]):
		sorted_df = subset_grouped.get_group(subset).sort_values('time', axis=0, ascending=True)
		reads_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
						  pd.DataFrame({'count':range(1,sorted_df['time'].size+1)}),
						  subset) )
		bases_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
						  (sorted_df['bases']/1000000000.).expanding(1).sum(),
						  subset) )
	tprint("...plotting {}".format('reads'))
	lineplot_multi(reads_dfs, "reads", os.path.join(args.outdir, 'res', "plots", "multi_lineplot_{}".format('reads')))
	tprint("...plotting {}".format('bases'))
	lineplot_multi(bases_dfs, "bases [Gb]", os.path.join(args.outdir, 'res', "plots", "multi_lineplot_{}".format('bases')))

	######
	
	#tprint("Creating pore heatmap")
	#pore_grouped = df.groupby(['pore'])
	##pore_indexes = list(pd.DataFrame(pore_grouped['bases'].count()).index)
	#pore_bases = pore_grouped['bases'].sum()
	#pore_indexes = list(pore_bases.index)
	##print(pore_bases)
	##print(pore_bases.index)
	##print(pore_indexes)
	#max_pore_index = max(pore_indexes)

	tprint("Creating html file")

	subset_grouped = df.groupby(['subset'])
	subsets = list(pd.DataFrame(subset_grouped['bases'].count()).index)
	tprint(subsets)

	barcode_grouped = df.groupby(['barcode'])
	barcodes = list(pd.DataFrame(barcode_grouped['bases'].count()).index)
	tprint(barcodes)

	create_html(args.outdir, 
				stats_df, 
				args.user_filename_input, 
				args.minion_id, 
				args.flowcell_id, 
				args.protocol_start, 
				args.website_refresh_rate, 
				barcodes, 
				subsets, 
				args.html_bricks_dir)

def create_html(outdir, 
				stats_df, 
				user_filename_input, 
				minion_id, 
				flowcell_id, 
				protocol_start, 
				website_refresh_rate, 
				barcodes, 
				subsets, 
				html_bricks_dir):
	#def dashrepl(matchobj):
	#	return '<a href="#{0}">{0}</a>'.format(matchobj.group(1))
	#	#if matchobj.group(0) == '-': return ' '
	#	#else: return '-'
	tprint("Parsing stats table to html")
	html_stats_df = make_html_table(stats_df).replace('valign="top"', 'valign="center"')
	#for m in re.finditer(">(BC[0-9][0-9])<", html_stats_df):
	#	print("x")
	for bc in barcodes:
		tprint(bc)
		html_stats_df = html_stats_df.replace(bc, '<a href="#{0}">{0}</a>'.format(bc))
	#html_stats_df = html_stats_df.replace("BC01", '<a href="BC01">BC01</a>')


	with open(os.path.join(html_bricks_dir, 'barcode_brick.html'), 'r') as f:
		barcode_brick = f.read()
	with open(os.path.join(html_bricks_dir, 'bottom_brick.html'), 'r') as f:
		bottom_brick = f.read()
	with open(os.path.join(html_bricks_dir, 'overview_brick.html'), 'r') as f:
		overview_brick = f.read()
	with open(os.path.join(html_bricks_dir, 'top_brick.html'), 'r') as f:
		top_brick = f.read()

	minion_id_to_css = {"GA10000":"one",
						"GA20000":"two",
						"GA30000":"three",
						"GA40000":"four",
						"GA50000":"five"}

	html_content = top_brick.format(user_filename_input, minion_id, flowcell_id, protocol_start, website_refresh_rate, minion_id_to_css[minion_id]) + \
				   overview_brick.format(html_stats_df)

	for barcode in barcodes:
		html_content = html_content + barcode_brick.format(barcode, subsets[0], subsets[2], subsets[1])

	html_content = html_content + bottom_brick

	with open(os.path.join(outdir, "results.html"), 'w') as outfile:
		print(html_content, file=outfile)

	copyfile(os.path.join(html_bricks_dir, 'style.css'), os.path.join(outdir, 'res', 'style.css'))






def pore_heatmap(max_pore_index, pore_bases, pore_indexes, dest):
	f = plt.figure()
	fig = plt.gcf()
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])

	x_dim = 32
	data = []
	#for 



def lineplot_multi(time_dfs_lbls, y_label, dest):
	f = plt.figure()
	fig = plt.gcf()

	gs0 = gridspec.GridSpec(1, 1)

	ax1 = plt.subplot(gs0[0, 0])

	ax1.set_ylabel(y_label)

	for i, (time, df, lbl) in enumerate(time_dfs_lbls):
		ax1.plot(time, df, color='C{}'.format(i), label=lbl)

	ax1.legend(loc=2)

	ax1.yaxis.grid(color="black", alpha=0.1)

	ax1.set_xlabel('sequencing time [h]')

	fig.tight_layout()
	#plt.show()
	plt.savefig(dest)

def lineplot_2y(time, bases, dest):

	#y_bases = [bases[0]]
	#for i in range(1,len(bases)):
	#	y_bases.append(y_bases[i-1] + bases[i])
	y_bases = bases.expanding(1).sum()

	y_reads = pd.DataFrame({'count':range(1,bases.size+1)})

	f = plt.figure()
	fig = plt.gcf()

	gs0 = gridspec.GridSpec(1, 1)

	ax1 = plt.subplot(gs0[0, 0])
	ax2 = ax1.twinx()

	ax1.set_ylabel('reads')
	ax2.set_ylabel('bases [Mb]')

	line1 = ax1.plot(time, y_reads, color='C1', label='reads')
	line2 = ax2.plot(time, y_bases, color='C2', label='bases')

	ax1.legend(loc=2, bbox_to_anchor=(0., 1.))
	ax2.legend(loc=2, bbox_to_anchor=(0., 0.92))

	#ax1.set_xticks()
	ax1.set_xlabel('sequencing time [h]')

	fig.tight_layout()
	#plt.show()
	plt.savefig(dest)

def barplot(bins, intervals, interval, x_unit, y_unit, dest):
	f = plt.figure()
	fig = plt.gcf()

	gs0 = gridspec.GridSpec(1, 1)#, width_ratios=[1], height_ratios=[0.3,1])
	#gs0.update(wspace=0.01, hspace=0.01)

	ax1 = plt.subplot(gs0[0, 0])
	ax2 = ax1.twinx()

	ax1.set_ylabel('reads')
	ax2.set_ylabel('bases [{}]'.format(y_unit))
	#ax1 = plt.subplot(gs0[1, 0])

	reads = [len(i) for i in bins]
	bases = [sum(i) for i in bins]

	x = np.array(list(range(len(intervals)))) + 0.5

	bar1 = ax1.bar(x-0.15, reads, width=0.3, color='C1', align='center', label = 'reads')
	bar2 = ax2.bar(x+0.15, bases, width=0.3, color='C2', align='center', label = 'bases')

	bars = [b for b in bar1+bar2]
	ax1.legend(loc=1, bbox_to_anchor=(1., 1.))
	ax2.legend(loc=1, bbox_to_anchor=(1., 0.92))

	ax1.set_xticks(list(range(len(intervals)+1)))
	xticklabels = ["" for i in intervals]
	xticklabels.append("{0:.1f}".format(intervals[-1]+interval))
	tickspace = len(intervals)//TICKLBLS
	for i in range(0,len(xticklabels)-tickspace, max(tickspace,1)):
		try: # fails if only one bin
			xticklabels[i] = "{0:.1f}".format(intervals[i])
		except:
			pass
	ax1.set_xticklabels(xticklabels)
	ax1.set_xlabel("{} {} bins".format(interval, x_unit))

	fig.tight_layout()
	#plt.show()
	plt.savefig(dest)



def boxplot(bins, intervals, interval, ylabel, dest):
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
	ax1.set_xticks([i+0.5 for i in range(len(intervals)+1)])
	#print([i+0.5 for i in range(len(intervals)+1)])
	xticklabels = ["" for i in intervals]
	xticklabels.append("{0:.1f}".format((intervals[-1]+interval)/SECS_TO_HOURS))
	tickspace = len(intervals)//TICKLBLS
	for i in range(0,len(xticklabels)-tickspace, max(tickspace,1)):
		try: # fails if only one bin
			xticklabels[i] = "{0:.1f}".format(intervals[i]/SECS_TO_HOURS)
		except:
			pass
	ax1.set_xticklabels(xticklabels)
	ax1.set_xlim([0.5, len(bins)+0.5])
	ax1.tick_params(top=False, bottom=True, left=True, right=False,
				   labeltop=False, labelbottom=True)
	ax1.yaxis.grid(color="black", alpha=0.1)
	ax1.set_axisbelow(True)




	ax0.bar([i for i in range(len(bins))], [len(i) for i in bins], align='center', color='grey', width=0.4)
	ax0.set_xlim([-0.5, len(bins)-0.5])
	ax0.set_ylim([0,max([len(i) for i in bins])*1.2])
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

def avgN50longest(series):
	#return series.sort_values(0, ascending=False)[:int(series.size/2)].mean()
	return series.nlargest(int(series.size/2)).mean()

def tprint(*args, **kwargs):
	if not QUIET:
		print("["+strftime("%H:%M:%S", gmtime())+"] "+" ".join(map(str,args)), **kwargs)

def stats_table(df):
	subgrouped = df.groupby(['barcode', 'subset'])

	#groups = list(pd.DataFrame(subgrouped['bases'].count()).index)
	grouped = df.groupby(['barcode'])

	# keys equal headers in html
	subgrouped_output_df = pd.DataFrame(OrderedDict((('reads' ,							subgrouped['bases'].count()), 
							 			 			 ('Mb' ,							subgrouped['bases'].sum()/1000000.), 
							 			 			 ('mean quality' ,					subgrouped['qual'].mean()), 
							 			 			 ('mean GC [%]' ,					subgrouped['gc'].mean()),
							 			 			 ('avg length [kb]' ,				subgrouped['bases'].mean()/1000.),
							 			 			 ('median length [kb]' ,			subgrouped['bases'].median()/1000.),
							 			 			 ('mean length longest N50 [kb]',	subgrouped['bases'].agg(avgN50longest)/1000.),
							 			 			 ('longest [kb]' ,					subgrouped['bases'].max()/1000.)
							 			 			 )))
	grouped_output_df = pd.DataFrame(OrderedDict((('reads' ,							grouped['bases'].count()), 
							 			 		  ('Mb' ,								grouped['bases'].sum()/1000000.), 
							 			 		  ('mean quality' ,						grouped['qual'].mean()), 
							 			 		  ('mean GC [%]' ,						grouped['gc'].mean()),
							 			 		  ('avg length [kb]' ,					grouped['bases'].mean()/1000.),
							 			 		  ('median length [kb]' ,				grouped['bases'].median()/1000.),
							 			 		  ('mean length longest N50 [kb]',		grouped['bases'].agg(avgN50longest)/1000.),
							 			 		  ('longest [kb]' ,						grouped['bases'].max()/1000.)
							 			 		  )))

	# concat both to one DataFrame, sorted by the indexes
	index = pd.MultiIndex.from_tuples(list(zip(list(grouped_output_df.index), ['all' for i in grouped_output_df.index])), names=['barcode', 'subset'])
	grouped_output_df.index = index
	concat_res = pd.concat([subgrouped_output_df,grouped_output_df])
	concat_res = concat_res.sort_index(level=['barcode', 'subset'])
	#concat_res = concat_res.reindex(['Passed','tooShort','BadQual','all'], level='subset') #TODO

	return concat_res

def make_html_table(df):
	df = df.round(2)
	#df = df.reindex(['Passed','tooShort','BadQual','all'], level='subset')
	return df.to_html()

def parse_stats(fp):
	df = pd.read_csv(fp, 
					 sep='\t', 
					 header=None, 
					 names="id bases qual gc subset pore_num pore time barcode".split(" "), 
					 usecols=[1,2,3,4,5,6,7,8],
					 index_col=[7,3,5], # referes to usecols
					 #converters={'time':(lambda x: pd.Timestamp(x)), 'bases':(lambda x: float(x)/1000000)}, 
					 converters={'time':(lambda x: pd.Timestamp(x))},
					 dtype={'qual':float, 'gc':float, 'bases':float})
	#print(df)
	#df['bases'] = df['bases']/1000000
	#print(df)
	#exit()

	#tprint(df.sort_values('time', axis=0, ascending=True))

	start_time = df['time'].min(axis=1)
	df['time'] = (df['time'] - start_time).dt.total_seconds()
	
	#exit()
	#print(df.groupby(['pore'])['pore_num'].count().sort_values(ascending=True))
	#print(df.groupby(['pore'])['pore_num'].count().sort_index(ascending=True))
	return df

def get_lowest_possible_interval(intervals, max_bins, min_value, max_value):
	interval = None
	num_bins = None
	for interval in intervals:
		offset = min_value // interval
		num_bins = ((max_value-(offset*interval)) // interval)+1
		if num_bins <= max_bins:
			interval = interval
			break
	if not interval:
		interval = intervals[-1]
	return interval, offset, int(num_bins)

def get_bin_edges(sorted_df, interval):
	offset = sorted_df[0] // interval
	edge = sorted_df[0] + interval
	edges = [0]
	for i,val in enumerate(sorted_df):
		if val > edge:
			edges.append( i )
			edge += interval
	edges.append(sorted_df.size)
	return edges, offset

def get_bins(df, bin_edges):
	bins = []
	for i in range(1,len(bin_edges)):
		bins.append(list(df[bin_edges[i-1]:bin_edges[i]]))
	return bins

if __name__ == '__main__':
	argument_parser = get_argument_parser()
	args = parse_args(argument_parser)
	main(args)
