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

import itertools
import argparse
import os
from time import gmtime, strftime
import numpy as np
import dateutil.parser
from datetime import datetime
import sys
import math
import pandas as pd
from collections import OrderedDict
import functools
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.lines as mlines
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
import copy
from mpl_toolkits import axes_grid1
import re
from shutil import copyfile
import warnings
from .version import __version__
from .helper import initLogger, package_dir, ArgHelpFormatter, r_file, r_dir, w_dir, resources_dir, jinja_env
import json
import logging
from jinja2 import Environment, PackageLoader, select_autoescape

warnings.filterwarnings("ignore")
TICKLBLS = 6
SECS_TO_HOURS = 3600.
logger = None

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
	argument_parser = argparse.ArgumentParser(description='''Parses a csv file containing statistics
														  about a nanopore sequencing run and creates
														  an in-depth report file including informative plots.''',
											  formatter_class=ArgHelpFormatter, 
											  add_help=False)

	main_options = argument_parser.add_argument_group('Main options')
	if __name__ == '__main__':
		main_options.add_argument('input',
								  help='''Stats file containing read information or a directory containing several such files. 
								  	   Requires CSV files with "\t" as seperator, no header and the following columns in given order:
								  	   read_id, length, qscore, mean_gc, Passed/tooShort, read_number, pore_index, timestamp, barcode''')
		main_options.add_argument('-r', '--recursive',
								  action='store_true',
								  help='''recursively search for directories containing stats files and corresponding logdata files''')

	main_options.add_argument('--html_refresh_rate',
							  type=int,
							  default=120,
							  help='refresh rate of the html page in seconds')

	plot_options = argument_parser.add_argument_group('Plotting options',
													  'Arguments changing the appearance of plots')
	plot_options.add_argument('--max_bins', 
							  type=int,
							  default=24,
							  help='maximum number of bins for box plots')
	plot_options.add_argument('--time_intervals',
							  action=parse_time_intervals,
							  default=[1,2,5,10,20,30,60,90,120,240],
							  help='time intervals in minutes available for binning')
	plot_options.add_argument('--kb_intervals',
							  action=parse_kb_intervals,
							  default=[.5,1.,2.,5.],
							  help='kb intervals available for binning')
	plot_options.add_argument('--gc_interval',
							  type=float,
							  default=0.5,
							  help='gc interval for binning reads based on mean G+C content')
	plot_options.add_argument('--matplotlib_style',
							  default='default',
							  help='matplotlib style string that influences all colors and plot appearances')
	plot_options.add_argument('--dpi',
							  type=int,
							  default=150)
	plot_options.add_argument('--width',
							  type=float,
							  default=6.4,
							  help='width of figure in inches')
	plot_options.add_argument('--height',
							  type=float,
							  default=4.8,
							  help='height of figure in inches')

	help_group = argument_parser.add_argument_group('Help')
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
	help_group.add_argument('-q', '--quiet',
							action='store_true',
							help='No prints to stdout')

	return argument_parser

def contains_stats_and_logdata(directory):
	files = [i for i in os.listdir(directory) if os.path.isfile(os.path.join(directory,i))]
	run_ids = [f.split("_")[0] for f in files if f.endswith("_stats.csv")]
	for run_id in run_ids:
		if "{}_logdata.json".format(run_id) in files:
			return True
	return False

def get_dir_list(input_path, recursive):
	input_dirs = []
	if not os.path.exists(input_path):
		logger.error('path {} does not exist'.format(input_path))
		exit(1)
	elif os.path.isfile(input_path):
		if contains_stats_and_logdata(os.path.dirname(input_path)):
			input_dirs.append(os.path.dirname(input_path))
	elif os.path.isdir(input_path):
		if contains_stats_and_logdata(input_path):
			input_dirs.append(input_path)
		if recursive:
			for root, dirs, _ in os.walk(input_path):
				for subdir in dirs:
					dir_path = os.path.join(root, subdir)
					if contains_stats_and_logdata(dir_path):
						input_dirs.append(dir_path)
	return input_dirs

def parse_args(argument_parser, ext_args=None):
	if ext_args:
		args = argument_parser.parse_args(ext_args)
	else:
		args = argument_parser.parse_args()

	global logger
	if args.verbose:
		loglvl = logging.DEBUG
	elif args.quiet:
		loglvl = logging.WARNING
	else:
		loglvl = logging.INFO

	initLogger(level=loglvl)
	logger = logging.getLogger(name='sp')

	args.time_intervals = [i*60 for i in args.time_intervals]

	input_dirs = get_dir_list(args.input, args.recursive)
	for input_dir in list(input_dirs):
		if not os.access(input_dir, os.W_OK):
			logger.warning("excluding directory {} due to missing write permissions".format(input_dir))
			input_dirs.remove(input_dir)
	args.input = input_dirs

	global fig_dpi, fig_width, fig_height
	fig_height = args.height
	fig_width = args.width
	fig_dpi = args.dpi

	return args

def get_input_files(input_dir):
	files = [i for i in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, i))]
	stats_ids = set([f.split("_")[0] for f in files if f.endswith("_stats.csv")])
	logdata_ids = set([f.split("_")[0] for f in files if f.endswith("_logdata.json")])
	for run_id in stats_ids.difference(logdata_ids):
		logger.warning("skipping run with run_id {}, missing logdata file for stats file {}".format(run_id, os.path.join(input_dir, run_id + "_stats.csv")))
	for run_id in stats_ids.difference(logdata_ids):
		logger.warning("skipping run with run_id {}, missing stats file for logdata file {}".format(run_id, os.path.join(input_dir, run_id + "_logdata.json")))
	stats_files, logdata_files = [], []

	for run_id in stats_ids.intersection(logdata_ids):
		stats_files.append(os.path.join(input_dir, run_id + "_stats.csv"))
		logdata_files.append(os.path.join(input_dir, run_id + "_logdata.json"))
	return stats_files, logdata_files

def parse_logdata_files(logdata_files):
	logdata = {'experiment':[], 'sample':[], 'minion_id':[], 'flowcell_id':[], 'protocol_start':[], 'run_id':[]}
	for fp in logdata_files:
		with open(fp, "r") as f:
			flowcell, run_data, mux_scans = json.loads(f.read(), object_pairs_hook=OrderedDict)
		for key in ['minion_id', 'protocol_start', 'run_id', 'experiment', 'sample']:
			if key in run_data:
				if run_data[key]:
					logdata[key].append(run_data[key])
				elif key != 'protocol_start':
					logdata[key].append('unknown')
			elif key != 'protocol_start':
				logdata[key].append('unknown')
		if 'flowcell_id' in flowcell:
			if flowcell['flowcell_id']:
				logdata['flowcell_id'].append(flowcell['flowcell_id'])
			else:
				logdata['flowcell_id'].append('unknown')
		else:
			logdata['flowcell_id'].append('unknown')

	if logdata['protocol_start']:
		logdata['protocol_start'] = min([dateutil.parser.parse(ts) for ts in logdata['protocol_start']]).strftime("%Y-%m-%d %H:%M:%S")
	else:
		logdata['protocol_start'] = 'unknown'
	logger.debug("- {}: {}".format('protocol_start', logdata['protocol_start']))
	for key in ['minion_id', 'flowcell_id', 'experiment', 'sample', 'run_id']:
		logdata[key] = " / ".join(set(logdata[key]))
		logger.debug("- {}: {}".format(key, logdata[key]))

	return logdata

def main(args, input_dir):
	logger.info("##### starting statsparser {} #####\n".format(__version__))

	if not os.path.isdir(os.path.join(input_dir, 'res', 'plots')):
		os.makedirs(os.path.join(input_dir, 'res', 'plots'))

	logger.info("Parsing stats files from directory {}".format(input_dir))
	stats_files, logdata_files = get_input_files(input_dir)

	df = parse_stats(stats_files)

	logger.info("Creating stats table")
	stats_df = stats_table(df)

	subgrouped = df.groupby(['barcode', 'subset'])
	indexes = list(pd.DataFrame(subgrouped['bases'].count()).index)

	#######

	logger.info("Creating boxplots")
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('time', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval(args.time_intervals,
																  args.max_bins, 
																  sub_df['time'].min(), 
																  sub_df['time'].max())
		bin_edges = get_bin_edges(sub_df['time'], interval)
		for col in sub_df:
			if col.lower() in ['bases','gc','qual']:
				ylbl = get_label(col)
				logger.debug("...plotting {}, {}: {}".format(bc, subset, ylbl))
				bins = get_bins(sub_df[col], bin_edges)
				intervals = [(offset+i)*interval for i in range(len(bins))]
				boxplot(bins, 
						intervals, 
						interval, 
						ylbl, 
						os.path.join(input_dir, 'res', "plots", "boxplot_{}_{}_{}".format(bc, subset, col)))

	#######
	
	logger.info("Creating kb-bins barplots")
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('bases', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval(list(np.array(args.kb_intervals)*1000),
																  args.max_bins, 
																  sub_df['bases'].min(), 
																  sub_df['bases'].max())
		bin_edges = get_bin_edges(sub_df['bases'], interval)
		logger.debug("...plotting {}, {}".format(bc, subset))
		#bins = get_bins(sub_df['bases']/1000000., bin_edges)
		bins = get_bins(sub_df['bases'], bin_edges)
		intervals = [((offset+i)*interval)/1000. for i in range(len(bins))]
		barplot(bins, 
				intervals, 
				interval/1000.,
				os.path.join(input_dir, 'res', "plots", "barplot_kb-bins_{}_{}".format(bc, subset)))
	
	#######
	
	logger.info("Creating gc-bins barplots")
	for bc, subset in indexes:
		sub_df = subgrouped.get_group( (bc, subset) ).sort_values('gc', axis=0, ascending=True)
		interval, offset, num_bins = get_lowest_possible_interval([args.gc_interval],
																  args.max_bins, 
																  sub_df['gc'].min(), 
																  sub_df['gc'].max())
		bin_edges = get_bin_edges(sub_df['gc'], interval)
		logger.debug("...plotting {}, {}".format(bc, subset))
		#bins = get_bins(sub_df['bases']/1000000., bin_edges)
		bins = get_bins(sub_df['bases'], bin_edges)
		intervals = [(offset+i)*interval for i in range(len(bins))]
		gc_lineplot(bins, 
					intervals, 
					interval,  
					os.path.join(input_dir, 'res', "plots", "barplot_gc-bins_{}_{}".format(bc, subset)))

	#######
	
	logger.info("Creating adapter-bin barplots")

	subset_l, subset_q, subset_p, _ = get_subset_names(indexes)
	bcs = list(set([bc for bc,_ in indexes]))
	bcs.sort()
	adapter_bin_barplots(stats_df, bcs, subset_l, subset_q, subset_p, os.path.join(input_dir, 'res', "plots", "adapter_bin_barplot.png"))

	#######
	
	logger.info("Creating multi lineplots with one y-axis")
	grouped = df.groupby(['barcode'])
	
	reads_dfs = []
	bases_dfs = []
	
	sorted_df = grouped.get_group( 'All' ).sort_values('time', axis=0, ascending=True)

	sorted_reads_df = pd.DataFrame({'count':range(1,sorted_df['time'].size+1)})
	reads_scaling_factor, reads_unit = choose_scaling_factor(sorted_reads_df.iat[-1,-1], [10**6 ,10**3, 1], ['M', 'k', '-'])
	sorted_bases_df = (sorted_df['bases']).expanding(1).sum()
	bases_scaling_factor, bases_unit = choose_scaling_factor(sorted_bases_df.iat[-1], [10**9, 10**6, 10**3], ['Gb', 'Mb', 'kb'])

	reads_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
					  sorted_reads_df,
					  'all') )
	bases_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
					  sorted_bases_df,
					  'all') )

	ordered_subsets = get_ordered_subsets(indexes)
	for subset in ordered_subsets:
		sorted_df = subgrouped.get_group( ('All',subset) ).sort_values('time', axis=0, ascending=True)
		reads_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
						  pd.DataFrame({'count':range(1,sorted_df['time'].size+1)}),
						  subset) )
		bases_dfs.append( (sorted_df['time']/SECS_TO_HOURS, 
						  (sorted_df['bases']).expanding(1).sum(),
						  subset) )
	logger.debug("...plotting {}".format('reads'))
	lineplot_multi(reads_dfs, 
				   "reads [{}]",
				   os.path.join(input_dir, 'res', "plots", "multi_lineplot_{}".format('reads')),
				   reads_scaling_factor,
				   reads_unit)
	logger.debug("...plotting {}".format('bases'))
	lineplot_multi(bases_dfs, 
				   "bases [{}]",
				   os.path.join(input_dir, 'res', "plots", "multi_lineplot_{}".format('bases')),
				   bases_scaling_factor,
				   bases_unit)

	#######

	logger.info("Parsing logdata files")
	logdata = parse_logdata_files(logdata_files)
	# if possible overwrite experiment name and sample name with directory names
	try:
		experiment, sample = os.path.abspath(input_dir).strip('/').split('/')[-2:]
		if experiment != logdata['experiment']:
			logger.warning("replacing experiment name {} with directory name {}".format(logdata['experiment'], experiment))
			logdata['experiment'] = experiment
		if sample != logdata['sample']:
			logger.warning("replacing sample name {} with directory name {}".format(logdata['sample'], sample))
			logdata['sample'] = sample
	except:
		pass

	logger.info("Creating html file")
	subset_grouped = df.groupby(['subset'])
	subsets = list(pd.DataFrame(subset_grouped['bases'].count()).index)
	
	barcode_grouped = df.groupby(['barcode'])
	barcodes = list(pd.DataFrame(barcode_grouped['bases'].count()).index)
	
	create_html(input_dir, stats_df, logdata, args.html_refresh_rate, barcodes, subsets)

	logger.info("Everything done")

def get_ordered_subsets(indexes):
	subsets = set([j for i,j in indexes])
	ordered_subsets = []
	for substring in ['all', 'length', 'pass', 'qual']:
		for subset in set(subsets):
			if substring in subset.lower():
				subsets.remove(subset)
				ordered_subsets.append(subset)
				break
	ordered_subsets.extend(list(subsets))
	return ordered_subsets

def create_html(outdir, stats_df, logdata, html_refresh_rate, barcodes, subsets):
	
	minion_id_to_css = {"GA10000":"one",
						"GA20000":"two",
						"GA30000":"three",
						"GA40000":"four",
						"GA50000":"five",
						"GA#0000":"unknown"}

	logger.debug("creating html stats table")
	html_stats_df = make_html_table(stats_df).replace('valign="top"', 'valign="center"')

	for bc in barcodes:
		#logger.info(bc)
		html_stats_df = html_stats_df.replace(bc, '<a href="#{0}">{0}</a>'.format(bc))

	channel_css = minion_id_to_css[logdata['minion_id']] if logdata['minion_id'] in minion_id_to_css else "unknown"
	render_dict = {'channel_css'			:	channel_css,
				   'html_refresh_rate'		:	html_refresh_rate,
				   'version'				:	__version__,
				   'dateTimeNow'			:	datetime.now().strftime("%Y-%m-%d_%H:%M"),
				   'html_stats_df'			:	html_stats_df,
				   'subsets'				:	subsets,
				   'barcodes'				:	barcodes}
	render_dict.update(logdata)

	template = jinja_env.get_template('report.template')
	with open(os.path.join(outdir, "report.html"), 'w') as outfile:
		print(template.render(render_dict), file=outfile)
	copyfile(os.path.join(resources_dir, 'style.css'), os.path.join(outdir, 'res', 'style.css'))

def lineplot_multi(time_dfs_lbls, y_label, dest, y_scaling_factor, y_unit):
	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])

	for i, (time, df, lbl) in enumerate(time_dfs_lbls):
		ax1.plot(time, df/y_scaling_factor, color='C{}'.format(i), label=lbl)

	ax1.set_xlabel('sequencing time [h]')
	ax1.set_ylabel(y_label.format(y_unit))
	ax1.legend(loc=2)
	ax1.yaxis.grid(color="black", alpha=0.1)

	plt.savefig(dest)
	plt.close()

def lineplot_2y(time, bases, dest):
	y_bases = bases.expanding(1).sum()
	y_reads = pd.DataFrame({'count':range(1,bases.size+1)})

	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])
	ax2 = ax1.twinx()

	ax1.set_ylabel('reads')
	ax2.set_ylabel('bases [Mb]')

	line1 = ax1.plot(time, y_reads, color='C1', label='reads')
	line2 = ax2.plot(time, y_bases, color='C2', label='bases')

	ax1.legend(loc=2, bbox_to_anchor=(0., 1.))
	ax2.legend(loc=2, bbox_to_anchor=(0., 0.92))

	ax1.set_xlabel('sequencing time [h]')

	#fig.tight_layout()
	plt.savefig(dest)
	plt.close()

def adapter_bin_barplots(stats_df, bcs, subset_l, subset_q, subset_p, dest):
	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])

	x = np.array(list(range(len(bcs)-1)))
	max_val = float(stats_df.drop(['All'], axis=0)[['Mb']].max())
	bases_scaling_factor, bases_unit = choose_scaling_factor(max_val, [10**3, 1], ['Gb', 'Mb'])

	data = {}
	for subset in [subset_p, subset_l, subset_q]:
		if subset:
			df = stats_df.xs(subset, level='subset')[['Mb']]
			df = df.reindex(bcs).drop(['All'], axis=0).fillna(0)
			data[subset] = np.array(df['Mb'])/bases_scaling_factor

	ax1.yaxis.grid(color="black", alpha=0.1)
	ax1.set_ylabel('bases [{}]'.format(bases_unit))

	for i, subset in enumerate([subset_l, subset_p, subset_q]):
		if subset:
			ax1.bar(x+(-0.2+i*0.2), data[subset], width=0.2, color='C{}'.format(i+1), align='center', label=subset)
	ax1.legend()

	ax1.set_xticks(list(range(len(df))))
	ax1.set_xticklabels(list(df.index), rotation=45)

	plt.savefig(dest)
	plt.close()

def barplot(bins, intervals, interval, dest):
	reads = np.array([len(i) for i in bins])
	bases = np.array([sum(i) for i in bins])
	reads_scaling_factor, reads_unit = choose_scaling_factor(np.max(reads), [10**6 ,10**3, 1], ['M', 'k', '-'])
	bases_scaling_factor, bases_unit = choose_scaling_factor(np.max(bases), [10**9, 10**6, 10**3], ['Gb', 'Mb', 'kb'])
	reads = reads/reads_scaling_factor
	bases = bases/bases_scaling_factor
	x = np.array(list(range(len(intervals)))) + 0.5

	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])
	ax2 = ax1.twinx()

	ax1.set_ylim([0, ceil_msp(max(reads))])
	ax2.set_ylim([0, ceil_msp(max(bases))])
	ax1.set_yticks(get_yticks(max(reads)))
	ax2.set_yticks(get_yticks(max(bases)))
	ax1.yaxis.grid(color="black", alpha=0.1)
	ax2.yaxis.grid(color="black", alpha=0.1)
	ax1.set_ylabel('reads [{}]'.format(reads_unit))
	if max(reads) >= 1000.:
		ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
	ax2.set_ylabel('bases [{}]'.format(bases_unit))

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
	ax1.set_xlabel("{} kb bins".format(interval))

	ax1.bar(x-0.15, reads, width=0.3, color='C1', align='center', label = 'reads')
	ax1.legend(loc=1, bbox_to_anchor=(1., 1.))
	ax2.bar(x+0.15, bases, width=0.3, color='C2', align='center', label = 'bases')
	ax2.legend(loc=1, bbox_to_anchor=(1., 0.92))

	#fig.tight_layout()
	plt.savefig(dest)
	plt.close()


def gc_lineplot(bins, intervals, interval, dest):
	reads = np.array([len(i) for i in bins])
	bases = np.array([sum(i) for i in bins])
	reads_scaling_factor, reads_unit = choose_scaling_factor(np.max(reads), [10**6 ,10**3, 1], ['M', 'k', '-'])
	bases_scaling_factor, bases_unit = choose_scaling_factor(np.max(bases), [10**9, 10**6, 10**3], ['Gb', 'Mb', 'kb'])
	reads = reads/reads_scaling_factor
	bases = bases/bases_scaling_factor
	#x = np.array(list(range(len(intervals)))) + 0.5

	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(1, 1)
	ax1 = plt.subplot(gs0[0, 0])
	ax2 = ax1.twinx()

	ax1.plot([i+interval/2 for i in intervals], reads, color='C1', label='reads', linewidth=0.5)
	ax2.plot([i+interval/2 for i in intervals], bases, color='C2', label='bases', linewidth=0.5)

	ax1.set_ylabel('reads [{}]'.format(reads_unit))
	ax2.set_ylabel('bases [{}]'.format(bases_unit))
	ax1.legend(loc=1, bbox_to_anchor=(1., 1.))
	ax2.legend(loc=1, bbox_to_anchor=(1., 0.92))

	ax1.set_xlabel("G+C content ({} % bins)".format(interval))
	if max(reads) >= 1000.:
		ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))

	#fig.tight_layout()
	plt.savefig(dest)
	plt.close()

def boxplot(bins, intervals, interval, ylabel, dest):
	f = plt.figure()
	fig = plt.gcf()
	fig.set_size_inches(fig_width, fig_height)
	fig.set_dpi(fig_dpi)
	gs0 = gridspec.GridSpec(2, 1, width_ratios=[1], height_ratios=[0.3,1])
	gs0.update(wspace=0.05, hspace=0.05)
	ax0 = plt.subplot(gs0[0, 0])
	ax1 = plt.subplot(gs0[1, 0])

	ax1.boxplot(bins, showfliers=False)

	ax1.set_xlabel("sequencing time [h]")
	ax1.set_ylabel(ylabel)
	ax1.set_xticks([i+0.5 for i in range(len(intervals)+1)])
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
	if max([max(_bin) for _bin in bins if _bin]) >= 1000.:
		ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
	ax1.set_axisbelow(True)

	#reads = [len(i) for i in bins]
	reads = np.array([len(i) for i in bins])
	reads_scaling_factor, reads_unit = choose_scaling_factor(np.max(reads), [10**6 ,10**3, 1], ['M', 'k', '-'])
	reads = reads/reads_scaling_factor
	ax0.bar([i for i in range(len(bins))], reads, align='center', color='grey', width=0.4)

	ax0.set_xlim([-0.5, len(bins)-0.5])
	ax0.set_ylim([0,np.max(reads)*1.2])
	#ax0.set_ylim([0,max(reads)*1.2])
	ax0.tick_params(top=False, bottom=False, left=True, right=False,
				   labeltop=False, labelbottom=False)
	#ax0.set_ylabel("reads")
	ax0.set_ylabel('reads [{}]'.format(reads_unit))
	if max(reads) >= 1000.:
		ax0.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
	ax0.set_xticklabels([])
	ax0.yaxis.grid(color="black", alpha=0.1)
	ax0.set_axisbelow(True)

	#fig.tight_layout()
	plt.savefig(dest)
	plt.close()

def avgN50longest(series):
	return series.nlargest(int(series.size/2)).mean()

def stats_table(df):
	subgrouped = df.groupby(['barcode', 'subset'])
	grouped = df.groupby(['barcode'])

	# keys equal headers in html
	subgrouped_output_df = pd.DataFrame(
		OrderedDict((('reads',							subgrouped['bases'].count()), 
					 ('Mb',								subgrouped['bases'].sum()/1000000.), 
					 ('mean quality',					subgrouped['qual'].mean()), 
					 ('mean G+C content [%]',			subgrouped['gc'].mean()),
					 ('mean length [kb]',				subgrouped['bases'].mean()/1000.),
					 ('median length [kb]' ,			subgrouped['bases'].median()/1000.),
					 ('mean length longest N50 [kb]',	subgrouped['bases'].agg(avgN50longest)/1000.),
					 ('longest [kb]',					subgrouped['bases'].max()/1000.)
					 )))
	grouped_output_df = pd.DataFrame(
		OrderedDict((('reads',							grouped['bases'].count()), 
					 ('Mb',								grouped['bases'].sum()/1000000.), 
					 ('mean quality',					grouped['qual'].mean()), 
					 ('mean G+C content [%]',			grouped['gc'].mean()),
					 ('mean length [kb]',				grouped['bases'].mean()/1000.),
					 ('median length [kb]',				grouped['bases'].median()/1000.),
					 ('mean length longest N50 [kb]',	grouped['bases'].agg(avgN50longest)/1000.),
					 ('longest [kb]',					grouped['bases'].max()/1000.)
					 )))

	# concat both to one DataFrame, sorted by the indexes
	index = pd.MultiIndex.from_tuples(list(zip(list(grouped_output_df.index), 
											   ['all' for i in grouped_output_df.index])), 
									  names=['barcode', 'subset'])
	grouped_output_df.index = index
	concat_res = pd.concat([subgrouped_output_df,grouped_output_df])
	concat_res = concat_res.sort_index(level=['barcode', 'subset'])
	return concat_res

def make_html_table(df):
	df = df.round(2)
	#df = df.reindex(['Passed','tooShort','BadQual','all'], level='subset')
	html_table =  df.to_html(formatters={'reads':(lambda x: "{:,}".format(x))},
							 float_format=(lambda x: "{0:,.2f}".format(x)),
							 sparsify=True)
	m = re.search('<tr>[\s]+<th rowspan', html_table)
	html_table = html_table.replace(m.group(0), '<tr class="trhighlight"' + m.group(0)[3:])
	return html_table

def parse_stats(fps):
	dfs = []
	for fp in fps:
		df = pd.read_csv(fp, 
						 sep='\t', 
						 header=None, 
						 names="id bases qual gc subset pore_num pore time barcode".split(" "), 
						 usecols=[1,2,3,4,5,6,7,8],
						 index_col=[7,3,5], # referes to usecols
						 converters={'time':(lambda x: pd.Timestamp(x))},
						 dtype={'qual':float, 'gc':float, 'bases':float})
		dfs.append(df)
	df = pd.concat(dfs)

	if df.empty:
		logger.error("no data in csv file{} {}".format('s' if len(fps)>1 else '', fps))
		exit(1)

	start_time = df['time'].min()
	df['time'] = (df['time'] - start_time).dt.total_seconds()

	index_all = pd.MultiIndex.from_tuples([('All',subset,pore) for barcode,subset,pore in df.index],
										  names=['barcode', 'subset', 'pore'])
	df_copy = df.copy()
	df_copy.index = index_all
	concat_df = pd.concat([df,df_copy])

	return concat_df

def choose_scaling_factor(max_value, scaling_factors, units):
	for i,scaling_factor in enumerate(scaling_factors):
		if max_value > scaling_factor:
			return scaling_factor, units[i]
	return scaling_factors[-1], units[-1]

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
		while val > edge:
			edges.append( i )
			edge += interval
	edges.append(sorted_df.size)
	return edges

def get_label(colomn_lbl):
	if colomn_lbl.lower() == 'gc':
		return 'G+C content'
	elif colomn_lbl.lower() == 'qual':
		return 'quality'
	elif colomn_lbl.lower() == 'bases':
		return 'read length'
	return colomn_lbl

def get_bins(df, bin_edges):
	bins = []
	for i in range(1,len(bin_edges)):
		bins.append(list(df[bin_edges[i-1]:bin_edges[i]]))
	return bins
 
def get_subset_names(indexes):
	subset_l, subset_q, subset_p, subset_a = None, None, None, None
	for bc, subset in indexes:
		if 'len' in subset.lower():
			subset_l = subset
		elif 'qual' in subset.lower():
			subset_q = subset
		elif 'pass' in subset.lower():
			subset_p = subset
		elif 'all' in subset:
			subset_a = subset
	return subset_l, subset_q, subset_p, subset_a

def ceil_msp(x):
	factor = 10**math.floor(math.log10(abs(x)))
	return math.ceil(x/factor)*factor

def get_yticks(max_val, nticks=11):
	vmax = ceil_msp(max_val)
	tickspace = vmax/10
	return np.arange(0, vmax+tickspace, tickspace)

def standalone():
	global __name__
	__name__ = '__main__'
	argument_parser = get_argument_parser()
	args = parse_args(argument_parser)
	logger.info("Start processing the following directories:")
	logger.info("\n".join(args.input))
	if args.recursive:
		# use exception ahndling in case of recursive
		for input_dir in args.input:
			try:
				main(args, input_dir)
			except:
				logger.warning("failed to create report for {}".format(input_dir))
	else:
		for input_dir in args.input:
			main(args, input_dir)

if __name__ == '__main__':
	standalone()