import argparse
import cmd
import readline
from utils import *
from pathlib import Path
from threading import Thread
from tqdm import tqdm
from pandas import read_csv

import MEGDataset

W = '\033[0m'   # white (normal)
R = '\033[31m'  # red
G = '\033[32m'  # green
O = '\033[33m'  # orange
B = '\033[34m'  # blue
P = '\033[35m'  # purple


def apply_to_all(toplevel: Path, featuretypes: dict, f, *args, **kwargs):
    subjects = [x for x in toplevel.iterdir() if x.is_dir() and 'CC' in x.stem]
    for subject in tqdm(subjects, unit='subjects', unit_scale=True):
        pass


def handle_open_smile(args):
    meg_config = Path(args.meg_config)
    audio_config = Path(args.audio_config)

    if not meg_config.is_file() or not audio_config.is_file():
        print('Could not find config file')
        parser.print_help()
        exit(-1)

    if args.threads > 1:
        print('Starting ', args.threads, 'threads...')

    megfiles = [(x / 'MEG') for x in args.toplevel.iterdir() if x.is_dir() and 'CC' in x.stem]
    n = round(len(megfiles) / args.threads) + 1
    megbuckets = [megfiles[i:i + n] for i in range(0, len(megfiles), n)]

    threads = []
    for i in range(1, args.threads):
        threads.append(Thread(None, run_catch_fail, None, (loopandsmile, megbuckets[i], meg_config, args.no_preserve,
                                                           args.save_mat, args.save_pickle)))
        if not args.no_meg:
            threads[-1].start()

    if not args.no_meg:
        run_catch_fail(loopandsmile, megbuckets[0], meg_config,
                       args.no_preserve, args.save_mat, args.save_pickle)

    if not args.no_audio:
        run_catch_fail(loopandsmile, [(x / 'Audio') for x in args.toplevel.iterdir() if x.is_dir() and 'CC' in x.stem],
                       audio_config, args.no_preserve, args.save_mat, autotries=-1)


def handle_restore(args):
    for f in args.toplevel.glob('**/*.bak'):
        if not args.silent:
            print('Renaming {0} to {1}'.format(f, f.with_suffix('.csv')))
        shutil.move(str(f), str(f.with_suffix('.csv')))


def handle_hide(args):
    for f in args.toplevel.glob('**/*.csv'):
        if not args.silent:
            print('Renaming {0} to {1}'.format(f, f.with_suffix('.bak')))
        shutil.move(str(f), str(f.with_suffix('.bak')))


def handle_clean(args):
    extensions = [x.strip(' .') for x in str(args.extension).split(',')]
    for suff in extensions:
        suff = str('.'+suff)
        print('\n\nDeleting files with suffix: ', suff)
        for f in args.toplevel.glob('**/*.{0}'.format(suff)):
            if not args.silent:
                print('Removing file: ', f)
            f.unlink()


def handle_raw(args):
    COLS = np.arange(36, 187)
    for f in tqdm(args.toplevel.glob('**/epoch*.csv'), unit='files', unit_scale=True,
                  total=len([x for x in args.toplevel.glob('**/epoch*.csv')])):
        if not args.silent:
            # tqdm.write('Found raw file {0}...'.format(f))
            pass
        f = f.resolve()
        subj_top = f.parent.parent.parent.resolve()
        ff = f.relative_to(subj_top).with_suffix('.npy')
        f_npy = subj_top / 'raw' / ff

        if not args.overwrite and f_npy.exists():
            # tqdm.write('Skipping: ' + str(f))
            continue

        data = read_csv(f).as_matrix()
        if not args.preserve_channels:
            if data.shape[1] < 200:
                continue
            data = data[:, COLS]
        # assuming conforms to expected structure, resolve first to ensure no relative difficulties
        f_npy.parent.mkdir(exist_ok=True, parents=True)
        # tqdm.write('save {0}'.format(f_npy))
        np.save(str(f_npy), data)
        if not args.keep:
            # tqdm.write('delete {0}'.format(f))
            f.unlink()
        # tqdm.write('\n')


def handle_decimate(args):
    print('Decimating all samples')
    for f in tqdm(args.toplevel.glob('**/raw/**/epoch*.npy'), unit='files', unit_scale=True,
                  total=len([x for x in args.toplevel.glob('**/raw/**/epoch*.csv')])):
        x = np.load(str(f))
        x = x[np.arange(0, x.shape[0], 20), :]

        f.rename(f.with_suffix('.bak'))

        np.save(str(f), x)


def handle_param_search_tool(args):
    print('Analyzing Top Level...')
    pass


class DatasetShell(cmd.Cmd):
    intro = """This prompt provides tools to manage dataset files. Type ? or 'help' for a list of possible actions. Type
    'exit' to end the shell."""
    prompt = 'dataset>> '

    extension = '.npy'
    toplevel = None
    test_subjects = None

    def do_add_subject(self, args):
        if not self.toplevel:
            print('No top level set. You need to set the top level...')
            self.do_set_toplevel([])
        for subject in args:
            print(O + 'Analyzing subject: ', subject)
            d = self.toplevel / subject
            if not self.binary_check('Subject Directory', d.exists() and d.is_dir()): continue


    def do_set_toplevel(self, args):
        if len(args) == 0:
            toplevel = self.get_file_dir('Top Level: ')
        else:
            toplevel = Path(args[0])
        try:
            self.subject_struct = MEGDataset.parsesubjects(self.toplevel)
        except (FileNotFoundError, TypeError):
            print('Could not find subject struct in:', toplevel)
        self.toplevel = toplevel

    def do_summary(self):
        print('Top Level:', self.toplevel)
        print('Test Subjects:', self.test_subjects)

    def do_extension(self, args):
        if len(args) == 0:
            print('Current Extension:', self.extension)
        else:
            self.extension = args[0]
            self.do_extension([])

    def do_exit(self, args):
        if len(args) > 0:
            print('Ignoring', *args)
        print('Exiting...')
        return True

    def do_create(self, args):
        if not self.binary_check('Top Level', self.toplevel): self.do_set_toplevel([])
        if not self.binary_check('Test Subjects', self.test_subjects): return
        self.do_summary()

        channels = int(input('Number of channels: '))
        samples = int(input('Samples per datum: '))

        loaded_subjects = {}
        for subject in

    @staticmethod
    def get_file_dir(prompt='Path:'):
        while True:
            f = Path(input(prompt=prompt))
            if not f.exists():
                if input('Does not exist. Proceed? [y/n] ').lower() != 'y':
                    continue
                else:
                    break
            elif not f.is_dir():
                if input('Not a directory. Proceed? [y/n] ').lower() != 'y':
                    continue
                else:
                    break
        return f

    @staticmethod
    def binary_check(check_arg, val, width=30):
        print('{0 <{1}} =>{2: <5}'.format(check_arg, width, G+'[yes]' if val else R+'[no]'))
        return val

    def precmd(self, line):
        line = str(line).lower()
        return line.split()


def handle_dataset(args):
    dshell = DatasetShell()
    dshell.cmdloop()

# Command line arguments
parser = argparse.ArgumentParser(
    description='Manage the eeglab dataset directory structure. Extract features, organize and clean files'
)

subparsers = parser.add_subparsers()

# ----------------------------------------------------------------------------------------------------------------------
# Parser that handles the openSMILE Feature extractor
# ----------------------------------------------------------------------------------------------------------------------
os_parser = subparsers.add_parser('os', help='Extract openSMILE features from eeglab extracted data')
os_parser.set_defaults(func=handle_open_smile)
os_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
os_parser.add_argument('--meg-config', '-mc', default=DEFAULT_MEG_CONFIG, type=str,
                    help='openSMILE config file to use for MEG')
os_parser.add_argument('--audio-config', '-ac', default=DEFAULT_ACOUSTIC_CONFIG, type=str,
                    help='openSMILE config file to use for audio')
os_parser.add_argument('--save-mat', '-z', action='store_true',
                    help='Save the output as a compressed .mat file')
os_parser.add_argument('--save-pickle', help='Save the output as a pickled numpy array', action='store_true')
parser.add_argument('--no-preserve', '-n', action='store_true',
                    help='Do not preserve the original activations')
os_parser.add_argument('--no-meg', action='store_true', help='Do not extract MEG features')
os_parser.add_argument('--no-audio', action='store_true', help='Do not extract audio features')
os_parser.add_argument('--threads', type=int, default=1, choices=range(1, 5), help='Number of threads to use to process')

# ----------------------------------------------------------------------------------------------------------------------
# The next three parsers are responsible for managing the csv files
# ----------------------------------------------------------------------------------------------------------------------
res_parser = subparsers.add_parser('restore', help='Restore ".csv" files from the ".bak" backups.')
res_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
res_parser.add_argument('--silent', '-s', help='', action='store_true')
res_parser.set_defaults(func=handle_restore)

hid_parser = subparsers.add_parser('hide', help='Hide ".csv" files as ".bak" backups.')
hid_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
hid_parser.add_argument('--silent', '-s', help='', action='store_true')
hid_parser.set_defaults(func=handle_hide)

clean_parser = subparsers.add_parser('clean', help='Clean certain file types from the directory structure.')
clean_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
clean_parser.add_argument('extension', type=str, help='Type of extension to clear in a comma separated list. '
                                                      'eg. csv, bak')
clean_parser.set_defaults(func=handle_clean)

raw_parser = subparsers.add_parser('raw', help='Utility for processing raw csv files generated by MATLAB. '
                                               'In the event that no features are desired to be extracted. '
                                               'This will also move the data into its correct directory structure '
                                               'and encode as npy file for smaller footprint and fast access.')
raw_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
raw_parser.add_argument('--silent', '-s', help='', action='store_true')
raw_parser.add_argument('--keep', '-k', help='Retain original csv files after performing operations',
                        action='store_true')
raw_parser.add_argument('--preserve-channels', '-p', help='Preserve all channels, otherwise, if there are greater than'
                                                          '200, will assume that only 37 through 187 are relevant.',
                                                          action='store_true')
raw_parser.add_argument('--overwrite', '-f', help='Overwrite any existing files, otherwise skip existing',
                        action='store_true')
raw_parser.set_defaults(func=handle_raw)

# ----------------------------------------------------------------------------------------------------------------------
# This command decimates the raw data
# ----------------------------------------------------------------------------------------------------------------------

dec_parser = subparsers.add_parser('decimate')
dec_parser.add_argument('toplevel', type=str, help='Top level of where the study and datasets are located')
dec_parser.add_argument('--keep', '-k', help='Retain original files after performing operations', action='store_true')

dec_parser.set_defaults(func=handle_decimate)

# ----------------------------------------------------------------------------------------------------------------------
# This command deals with management of parameter searches
# ----------------------------------------------------------------------------------------------------------------------

param_search_parser = subparsers.add_parser('psmgmt', help='This utility displays and manages search space files.')
param_search_parser.add_argument('toplevel', type=str, help='Top level of where the models and search files are found')
param_search_parser.set_defaults(func=handle_param_search_tool)

# ----------------------------------------------------------------------------------------------------------------------
# This command helps manage the dataset files
# ----------------------------------------------------------------------------------------------------------------------

dataset_parser = subparsers.add_parser('dataset', help='CMD tool to manage dataset files')
dataset_parser.set_defaults(func=lambda :)

# ----------------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    args = parser.parse_args()

    # Toplevel exists for all commands
    args.toplevel = Path(args.toplevel)
    if not args.toplevel.is_dir():
        print('Could not find top level path: ', args.toplevel)
        parser.print_help()
        exit(-1)

    # Run the actual command
    args.func(args)

