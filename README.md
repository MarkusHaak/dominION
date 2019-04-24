# dominION

Automated monitoring and logging of sequencing runs performed on the Oxford Nanopore Technologies GridION sequencer.

## About

The dominION agent supervises all channels of a GridION simultaneously, performing demultiplexing for barcoded libraries, data transfer to a remote server, as well as logging of experiment parameters, QC results and read statistics. For each experiment, dominION produces and updates comprehensive reports in printer-friendly html format, comprising tabular information and data plots about G+C content, read length, read quality, and throughput for the complete run as well as every barcode adapter group. In addition, it enables to detect long-term trends of monitored features over the course of all documented sequencing runs and to detect regularities and interrelations of results between different samples and across different GridION sequencers.

## Quick Setup

The easiest way to setup dominion and all its dependencies is to clone the repository and run the bash script setup. 

First, open a console and make sure that git is installed:

```bash
sudo apt-get -y install git
```

Next, clone the git repository of dominION with option *--recurse-submodules*. If you have no access to the github servers from your local machine, you can clone the directory on a different machine, transfer the cloned directory *dominION* and proceed with the installation.

```bash
git clone --recurse-submodules https://github.com/MarkusHaak/dominION.git
```

Finally, run script/setup to install dominION in a new virtual environment, setup key authentication and defaults for sequence data transfer to a remote server. Unless the option `-m` for *minimal* is set, a cron job for the dominion agent script is installed, the Firefox startup page is set to the overview page of dominION and .bash_aliases is modified to source the python virtual environment when opening a new console.

Please **replace USER, HOST and DEST** with your server specific information. You will be prompted to enter the administrator password of your local machine (the GridION) and the password for the specified user on the remote host to setup key authentication.

```bash
/bin/bash dominION/script/setup -u USER -H HOST -d DEST
```

After **restarting the machine**, the gridION agent script should be running in a screen terminal in the background. If you open Firefox, you should see the overview page of dominION as the startup page.

## Setup

The steps in this section are not necessary if the **Quick Setup** was performed.

### Setup Environment

On a brand new gridION, the software is not up-to-date. In any case, consider running apt update and apt upgrade as admin first:

```bash
sudo apt update
sudo apt upgrade
```

For file transfer from the GridION to a remote server, it is required to configure SSH key-based authentication. On the GridION, generate a SSH key pair for dominion.

```bash
ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa_dominion
```

Adapt the public key in order to restricted key authentication to the rsync command needed for file transfer. Please change USER, HOST and DEST/ON/SERVER/ according to your needs. These parameters specify the destination of file transfers with rsync, as in USER@HOST:/DEST/ON/SERVER/.

```bash
user="USER"
host="HOST"
dest="/DEST/ON/SERVER/"
localip=$(ifconfig | sed -En 's/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p')
echo 'command="rsync --server -Rruve.iLsfx . '"$dest"'",from="'"$localip"'",restrict '"$(cat ~/.ssh/id_rsa_dominion.pub)" > ~/.ssh/id_rsa_dominion.pub
```

Then transfer the public key to the server using ssh-copy-id. You will be prompted to type in the password for the specified user on the remote host.

```bash
ssh-copy-id -i ~/.ssh/id_rsa_dominion.pub "${user}@${host}"
```

On some GridIONs, the Python3 installation is missing the Python package installer pip and git. You can install both with apt-get.

```bash
sudo apt-get -y install python3-pip git
```

As this software is intended to be run on the GridION sequencer, I highly recommend using [virtualenv](https://pypi.org/project/virtualenv/) to set up a virtual python environment prior to the installation:

```bash
sudo apt-get -y install virtualenv
virtualenv -p python3 ~/.dominION
```

Don't forget to **activate** your virtual environment: 

```bash
source ~/.dominION/bin/activate
```

This needs to be done every time you open a new console in which you want to execute dominION commands. I therefore recommend to add the source command to your .bash_aliases file. This way, the virtual environment is sourced automatically when opening a new console. 

```bash
touch ~/.bash_aliases
echo "if [ -f ~/.dominION/bin/activate ]; then . ~/.dominION/bin/activate; fi" >> ~/.bash_aliases
```

### Dependencies

dominION requires an adapted version of ont_fast5_api, which contains a script multi_to_multi_fast5 that splits Multi-Fast5 files into files containing reads belonging to the same adapter group. The same applies to Porechop, where I fixed a bug regarding the identification of adapter orientation. Both are included as submodules in the dominION repository on github. To install these dependencies, clone the dominION repository with option *--recurse-submodules* and install them separately:

```bash
git clone --recurse-submodules https://github.com/MarkusHaak/dominION.git
cd dominION/ont_fast5_api
python3 setup.py install 
cd ../Porechop
python3 setup.py install
cd ..
```

In addition, the following external python modules are required, but they are automatically installed if you follow the instructions given under **Installation**.

* watchdog
* numpy
* pandas
* matplotlib

Please be aware that dominION requires python3.5 or greater and is not backwards compatible with python2. 

### Installation

At last, clone and install dominION. If you followed the steps above in the same console, dominION will be configured to use the user, host and destination as specified for setting up key authentication. Otherwise, you will be prompted to give these information when executing `python3 setup.py install`.

```bash
INIFILE="dominion/resources/defaults.ini"
perl -pi -e "s|user.*|user = ${user}|" "$INIFILE"
perl -pi -e "s|host.*|host = ${host}|" "$INIFILE"
perl -pi -e "s|dest.*|dest = ${dest}|" "$INIFILE"
python3 setup.py install 
```

### Recommended Configuration

As dominION is intended to run in the background as a software agent, i recommend adding a new cron job to your crontab that runs dominion in a screen shell.

```bash
newjob="@reboot screen -dm bash -c '. ${HOME}/.dominION/bin/activate ; dominion'"
(crontab -l ; echo "$newjob") | crontab -
```

To prevent the need to activate the virtual environment each time a subscript of dominION is needed, modify the .bash_aliases file to source it whenever a new console is opened.

```bash
touch ~/.bash_aliases
echo "if [ -f ~/.dominION/bin/activate ]; then . ~/.dominION/bin/activate; fi" >> ~/.bash_aliases
```

Optionally, you can change the startup page of Firefox to the dominION overview html file /data/dominION/HOSTNAME_overview.html .

## Basic Usage


## Advanced Usage

### dominion

```
usage: dominion [-o OUTPUT_DIR] [--data_basedir DATA_BASEDIR]
                [--minknow_log_basedir MINKNOW_LOG_BASEDIR]
                [--logfile LOGFILE] [--bc_kws [BC_KWS [BC_KWS ...]]] [-n] [-a]
                [-p] [-l MIN_LENGTH] [-q MIN_QUALITY] [-d RSYNC_DEST]
                [-u UPDATE_INTERVAL] [-m]
                [--statsparser_args STATSPARSER_ARGS] [-h] [--version] [-v]
                [--quiet]

A tool for monitoring and protocoling sequencing runs performed on the Oxford
Nanopore Technologies GridION sequencer and for automated post processing and
transmission of generated data. It collects information on QC and sequencing
experiments and displays summaries of mounted flow cells as well as
comprehensive reports about currently running and previously performed
experiments.

General arguments:
  arguments for advanced control of the program's behavior

  --bc_kws [BC_KWS [BC_KWS ...]]
                        if at least one of these key words is a substring of
                        the run name, porechop is used to demultiplex the
                        fastq data (default: ['RBK', 'NBD', 'RAB', 'LWB',
                        'PBK', 'RPB', 'arcod'])
  -n, --no_transfer     no data transfer to the remote host (default: False)
  -a, --all_fast5       also put fast5 files of reads removed by length and
                        quality filtering into barcode bins (default: False)
  -p, --pass_only       use data from fastq_pass only (default: False)
  -l MIN_LENGTH, --min_length MIN_LENGTH
                        minimal length to pass filter (default: 1000)
  -q MIN_QUALITY, --min_quality MIN_QUALITY
                        minimal quality to pass filter (default: 5)
  -d RSYNC_DEST, --rsync_dest RSYNC_DEST
                        destination for data transfer with rsync, format
                        USER@HOST[:DEST]. Key authentication for the specified
                        destination must be set up, otherwise data transfer
                        will fail. Default value is parsed from setting file
                        /home/grid/.dominION/lib/python3.5/site-packages/domin
                        ion-0.3.9-py3.5.egg/dominion/resources/defaults.ini
  -u UPDATE_INTERVAL, --update_interval UPDATE_INTERVAL
                        minimum time interval in seconds for updating the
                        content of a report page (default: 300)
  -m, --ignore_file_modifications
                        Ignore file modifications and only consider file
                        creations regarding determination of the latest log
                        files (default: False)

I/O arguments:
  Further input/output arguments. Only for special use cases

  -o OUTPUT_DIR, --output_dir OUTPUT_DIR
                        Path to the base directory where experiment reports
                        shall be saved (default: /data/dominION/)
  --data_basedir DATA_BASEDIR
                        Path to the directory where basecalled data is saved
                        (default: /data)
  --minknow_log_basedir MINKNOW_LOG_BASEDIR
                        Path to the base directory of GridIONs log files
                        (default: /var/log/MinKNOW)
  --logfile LOGFILE     File in which logs will be safed (default:
                        OUTPUTDIR/logs/YYYY-MM-DD_hh:mm_HOSTNAME_LOGLVL.log

Statsparser arguments:
  Arguments passed to statsparser for formatting html reports

  --statsparser_args STATSPARSER_ARGS
                        Arguments that are passed to the statsparser script.
                        See a full list of available arguments with
                        --statsparser_args " -h" (default: [])

Help:
  -h, --help            Show this help message and exit
  --version             Show program's version string and exit
  -v, --verbose         Additional debug messages are printed to stdout
                        (default: False)
  --quiet               Only errors and warnings are printed to stdout
                        (default: False)
```

### statsparser (standalone)

```
usage: statsparser [-o OUTDIR] [--html_refresh_rate HTML_REFRESH_RATE]
                   [--max_bins MAX_BINS] [--time_intervals TIME_INTERVALS]
                   [--kb_intervals KB_INTERVALS] [--gc_interval GC_INTERVAL]
                   [--matplotlib_style MATPLOTLIB_STYLE]
                   [--logdata_file LOGDATA_FILE]
                   [--user_filename_input USER_FILENAME_INPUT]
                   [--sample SAMPLE] [--minion_id MINION_ID]
                   [--flowcell_id FLOWCELL_ID]
                   [--protocol_start PROTOCOL_START] [-h] [--version] [-v]
                   [-q]
                   input

Parses a csv file containing statistics about a nanopore sequencing run and
creates an in-depth report file including informative plots.

Main options:
  input                 Stats file containing read information, or
                        a directory containing several such files. Requires
                        CSV files with " " as seperator, no header and the
                        following columns in given order: read_id, length,
                        qscore, mean_gc, Passed/tooShort, read_number,
                        pore_index, timestamp, barcode
  -o OUTDIR, --outdir OUTDIR
                        Path to a directory in which the report files and
                        folders will be saved (default: directory of input)
  --html_refresh_rate HTML_REFRESH_RATE
                        refresh rate of the html page in seconds (default:
                        120)

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
  Arguments concerning the experiment. Either specify a logdata file or all
  arguments individually.

  --logdata_file LOGDATA_FILE
                        path to the report file of this sequencing run
                        (default: <run_id>_stats.json)
  --user_filename_input USER_FILENAME_INPUT
                        run title (default: Run#####_MIN###_KIT###)
  --sample SAMPLE       sample name (default: Run#####_MIN###_KIT###)
  --minion_id MINION_ID
                        (default: GA#0000)
  --flowcell_id FLOWCELL_ID
                        (default: FAK#####)
  --protocol_start PROTOCOL_START
                        (default: YYYY-MM-DD hh:mm:ss.ms)

Help:
  -h, --help            Show this help message and exit
  --version             Show program's version number and exit
  -v, --verbose         Additional status information is printed to stdout
                        (default: False)
  -q, --quiet           No prints to stdout (default: False)
```
