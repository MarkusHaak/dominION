# GridIONwatcher

GridIONwatcher is a tool for monitoring and protocoling sequencing runs performed on the Oxford Nanopore Technologies GridION sequencer and for automated post processing and transmission of generated data. Listening for changes to MinKNOW log files, it collects information on QC and sequencing experiments and displays summaries of mounted flow cells as well as comprehensive reports about currently running and previously performed experiments.

## Dependencies

The following external python modules are required:

* dateutil
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
usage: gridionwatcher.py [-h] [-l LOG_BASEDIR] [-d DATABASE_DIR] [-m]
                         [--no_watchnchop] [-b BASECALLED_BASEDIR]
                         [-u UPDATE_INTERVAL]
                         [--statsparser_args STATSPARSER_ARGS]
                         [--html_bricks_dir HTML_BRICKS_DIR]
                         [--status_page_dir STATUS_PAGE_DIR]
                         [--watchnchop_path WATCHNCHOP_PATH]
                         [--statsparser_path STATSPARSER_PATH]
                         [--python3_path PYTHON3_PATH] [--perl_path PERL_PATH]
                         [-v] [-q]

Parses a stats file containing information about a nanopore sequencing run and
creates an in-depth report file including informative plots.

optional arguments:
  -h, --help            show this help message and exit
  -l LOG_BASEDIR, --log_basedir LOG_BASEDIR
                        Path to the base directory of GridIONs log files,
                        contains the manager log files. (default:
                        /var/log/MinKNOW)
  -d DATABASE_DIR, --database_dir DATABASE_DIR
                        Path to the base directory where reports will be
                        safed. (default: ./reports)
  -m, --modified_as_created
                        Handle file modifications as if the file was created,
                        meaning that the latest changed file is seen as the
                        current log file.
  --no_watchnchop       if specified, watchnchop is not executed
  -b BASECALLED_BASEDIR, --basecalled_basedir BASECALLED_BASEDIR
                        Path to the directory where basecalled data is saved.
                        (default: /data/basecalled)
  -u UPDATE_INTERVAL, --update_interval UPDATE_INTERVAL
                        inverval time in seconds for updating the stats
                        webpage contents. (default: 600)
  --statsparser_args STATSPARSER_ARGS
                        Arguments that are passed to the statsparser. See a
                        full list of possible options with --statsparser_args
                        " -h"
  --html_bricks_dir HTML_BRICKS_DIR
                        Path to the directory containing template files and
                        resources for the html pages. (default: ./html_bricks
  --status_page_dir STATUS_PAGE_DIR
                        Path to the directory where all files for the GridION
                        status page will be stored. (default: ./GridIONstatus)
  --watchnchop_path WATCHNCHOP_PATH
                        Path to the watchnchop executable (default:
                        ./watchnchop.pl)
  --statsparser_path STATSPARSER_PATH
                        Path to statsparser.py (default: ./statsparser.py)
  --python3_path PYTHON3_PATH
                        Path to the python3 executable (default:
                        /usr/bin/python3)
  --perl_path PERL_PATH
                        Path to the perl executable (default: /usr/bin/perl)
  -v, --verbose         Additional status information is printed to stdout.
  -q, --quiet           No prints to stdout.
```

### statsparser (standalone)

```
usage: statsparser.py [-h] [-o OUTDIR] [-q] [--max_bins MAX_BINS]
                      [--time_intervals TIME_INTERVALS]
                      [--kb_intervals KB_INTERVALS]
                      [--gc_interval GC_INTERVAL]
                      [--matplotlib_style MATPLOTLIB_STYLE]
                      [--result_page_refresh_rate RESULT_PAGE_REFRESH_RATE]
                      [--html_bricks_dir HTML_BRICKS_DIR]
                      [--user_filename_input USER_FILENAME_INPUT]
                      [--minion_id MINION_ID] [--flowcell_id FLOWCELL_ID]
                      [--protocol_start PROTOCOL_START]
                      statsfile

Parses a stats file containing information about a nanopore sequencing run and
creates an in-depth report file including informative plots.

positional arguments:
  statsfile             Path to the stats file containing all necessary
                        information about the sequencing run. Requires a CSV
                        file with " " as seperator, no header and the
                        following columns in given order: read_id, length,
                        qscore, mean_gc, Passed/tooShort, read_number,
                        pore_index, timestamp, barcode

optional arguments:
  -h, --help            show this help message and exit
  -o OUTDIR, --outdir OUTDIR
                        Path to a directory in which the report files and
                        folders will be saved. (default: directory of
                        statsfile)
  -q, --quiet           No status information is printed to stdout.
  --max_bins MAX_BINS   maximum number of bins for box plots (default: 24)
  --time_intervals TIME_INTERVALS
                        time intervals in minutes available for binning.
                        (default: 1,2,5,10,20,30,60,90,120,240)
  --kb_intervals KB_INTERVALS
                        kb intervals available for binning. (default:
                        .5,1.,2.,5.)
  --gc_interval GC_INTERVAL
                        gc interval for binning reads based on mean gc
                        content. (default: 0.05)
  --matplotlib_style MATPLOTLIB_STYLE
                        matplotlib style string that influences all colors and
                        plot appearances. (default: default)
  --result_page_refresh_rate RESULT_PAGE_REFRESH_RATE
                        refresh rate in seconds. (default: 120)
  --html_bricks_dir HTML_BRICKS_DIR
                        directory containing template files for creating the
                        results html page. (default: ./html_bricks)
  --user_filename_input USER_FILENAME_INPUT
  --minion_id MINION_ID
  --flowcell_id FLOWCELL_ID
  --protocol_start PROTOCOL_START
```