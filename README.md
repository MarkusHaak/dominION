# GridIONwatcher

GridIONwatcher is a tool for monitoring and protocoling sequencing runs performed on the Oxford Nanopore Technologies GridION sequencer and for automated post processing and transmission of generated data. Listening for changes to MinKNOW log files, it collects information on QC and sequencing experiments and displays summaries of mounted flow cells as well as comprehensive reports about currently running and previously performed experiments.

## Dependencies

The following external python modules are required:

* watchdog
* numpy
* pandas
* matplotlib

GridIONwatcher requires python3 and is currently not backwards compatible with python2. 

## Installation

```bash
git clone https://github.com/MarkusHaak/GridIONwatcher.git
cd GridIONwatcher
python3 setup.py install
```
Alternatively, install with GridIONwatcher with pip from GitHub:

```bash
pip3 install git+https://github.com/MarkusHaak/GridIONwatcher.git
```
As this software is intended to be run on the GridION sequencer, I highly recommend using [virtualenv](https://pypi.org/project/virtualenv/) to set up a virtual python environment for your installation. 

## Full usage

### gridionwatcher

```
usage: gridionwatcher [-d DATABASE_DIR] [--status_page_dir STATUS_PAGE_DIR]
                      [--statsparser_args STATSPARSER_ARGS]
                      [-b BASECALLED_BASEDIR] [-l MINKNOW_LOG_BASEDIR]
                      [-r RESOURCES_DIR] [--watchnchop_path WATCHNCHOP_PATH]
                      [--statsparser_path STATSPARSER_PATH]
                      [--python3_path PYTHON3_PATH] [--perl_path PERL_PATH]
                      [-u UPDATE_INTERVAL] [-m] [--no_watchnchop] [-h]
                      [--version] [-v] [-q]

A tool for monitoring and protocoling sequencing runs performed on the Oxford
Nanopore Technologies GridION sequencer and for automated post processing and
transmission of generated data. It collects information on QC and sequencing
experiments and displays summaries of mounted flow cells as well as
comprehensive reports about currently running and previously performed
experiments.

Main options:
  -d DATABASE_DIR, --database_dir DATABASE_DIR
                        Path to the base directory where experiment reports
                        shall be saved (default: reports)
  --status_page_dir STATUS_PAGE_DIR
                        Path to the directory where all files for the GridION
                        status page will be stored (default: GridIONstatus)

Statsparser arguments:
  Arguments passed to statsparser for formatting html pages

  --statsparser_args STATSPARSER_ARGS
                        Arguments that are passed to the statsparser. See a
                        full list of possible options with --statsparser_args
                        " -h" (default: [])

I/O options:
  Further input/output options. Only for special use cases

  -b BASECALLED_BASEDIR, --basecalled_basedir BASECALLED_BASEDIR
                        Path to the directory where basecalled data is saved
                        (default: /data/basecalled)
  -l MINKNOW_LOG_BASEDIR, --minknow_log_basedir MINKNOW_LOG_BASEDIR
                        Path to the base directory of GridIONs log files
                        (default: /var/log/MinKNOW)
  -r RESOURCES_DIR, --resources_dir RESOURCES_DIR
                        Path to the directory containing template files and
                        resources for the html pages (default:
                        PACKAGE_DIR/resources)

Executables paths:
  Paths to mandatory executables

  --watchnchop_path WATCHNCHOP_PATH
                        Path to the watchnchop executable (default:
                        watchnchop.pl)
  --statsparser_path STATSPARSER_PATH
                        Path to statsparser.py (default:
                        PACKAGE_DIR/statsparser.py)
  --python3_path PYTHON3_PATH
                        Path to the python3 executable (default:
                        /usr/bin/python3)
  --perl_path PERL_PATH
                        Path to the perl executable (default: /usr/bin/perl)

General options:
  Advanced options influencing the program execution

  -u UPDATE_INTERVAL, --update_interval UPDATE_INTERVAL
                        Time inverval (in seconds) for updating the stats
                        webpage contents (default: 600)
  -m, --ignore_file_modifications
                        Ignore file modifications and only consider file
                        creations regarding determination of the latest log
                        files (default: True)
  --no_watchnchop       If specified, watchnchop is not executed (default:
                        False)

Help:
  -h, --help            Show this help message and exit
  --version             Show program's version number and exit
  -v, --verbose         Additional status information is printed to stdout
                        (default: False)
  -q, --quiet           No prints to stdout (default: False)
```

### statsparser (standalone)

```
usage: statsparser [-o OUTDIR]
                   [--result_page_refresh_rate RESULT_PAGE_REFRESH_RATE]
                   [--resources_dir RESOURCES_DIR] [--max_bins MAX_BINS]
                   [--time_intervals TIME_INTERVALS]
                   [--kb_intervals KB_INTERVALS] [--gc_interval GC_INTERVAL]
                   [--matplotlib_style MATPLOTLIB_STYLE]
                   [--user_filename_input USER_FILENAME_INPUT]
                   [--minion_id MINION_ID] [--flowcell_id FLOWCELL_ID]
                   [--protocol_start PROTOCOL_START] [-h] [--version] [-q]
                   statsfile

Parses a csv file containing statistics about a nanopore sequencing run and
creates an in-depth report file including informative plots.

Main options:
  statsfile             Path to the stats file containing all necessary
                        information about the sequencing run. Requires a CSV
                        file with " " as seperator, no header and the
                        following columns in given order: read_id, length,
                        qscore, mean_gc, Passed/tooShort, read_number,
                        pore_index, timestamp, barcode
  -o OUTDIR, --outdir OUTDIR
                        Path to a directory in which the report files and
                        folders will be saved (default: directory of
                        statsfile)
  --result_page_refresh_rate RESULT_PAGE_REFRESH_RATE
                        refresh rate in seconds. (default: 120)
  --resources_dir RESOURCES_DIR
                        directory containing template files for creating the
                        results html page. (default: PACKAGE_DIR/resources)

Plotting options:
  Arguments changing the appearance of plots

  --max_bins MAX_BINS   maximum number of bins for box plots (default: 24)
  --time_intervals TIME_INTERVALS
                        time intervals in minutes available for binning
                        (default: [1, 2, 5, 10, 20, 30, 60, 90, 120, 240])
  --kb_intervals KB_INTERVALS
                        kb intervals available for binning (default: [0.5,
                        1.0, 2.0, 5.0])
  --gc_interval GC_INTERVAL
                        gc interval for binning reads based on mean gc content
                        (default: 0.5)
  --matplotlib_style MATPLOTLIB_STYLE
                        matplotlib style string that influences all colors and
                        plot appearances (default: default)

Experiment options:
  Arguments concerning the experiment

  --user_filename_input USER_FILENAME_INPUT
                        (default: Run#####_MIN###_KIT###)
  --minion_id MINION_ID
                        (default: GA#0000)
  --flowcell_id FLOWCELL_ID
                        (default: FAK#####)
  --protocol_start PROTOCOL_START
                        (default: YYYY-MM-DD hh:mm:ss.ms)

Help:
  -h, --help            Show this help message and exit
  --version             Show program's version number and exit
  -q, --quiet           No prints to stdout (default: False)
```
