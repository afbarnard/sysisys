"""Finds duplicate files and generates a script to deduplicate them"""

# Copyright (c) 2019 Aubrey Barnard.  This is free software released
# under the MIT License.  See `LICENSE.txt` for details.


from enum import Enum
import collections
import datetime
import hashlib
import inspect
import itertools as itools
import operator
import os.path
import pathlib
import pprint
import re
import shlex
import sqlite3
import subprocess
import sys

from barnapy import arguments
from barnapy import files
from barnapy import logging
from barnapy import parse


__version__ = '0.1.0'


def resolve_path(path):
    # Convert to a string path because pathlib doesn't support expanding
    # user directories until Python 3.5
    return pathlib.Path(os.path.abspath(os.path.expanduser(str(path))))


def is_child_path(child, parent):
    child = os.path.normpath(child)
    parent = os.path.normpath(parent)
    if not parent.endswith(os.path.sep):
        parent += os.path.sep
    return child.startswith(parent) and len(child) > len(parent)


def run_command_read_out(command):
    logger = logging.getLogger('find_dups')
    logger.info('Running command: {!r} |& ...',
                ' '.join(shlex.quote(arg) for arg in command))
    with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            universal_newlines=True,
    ) as proc:
        yield from proc.stdout


def gather_file_metadata_records(
        paths,
        prune_patterns=(),
        exclude_patterns=(),
        min_file_size=None,
        max_file_size=None,
):
    # Make sure the paths are absolute
    abspaths = [resolve_path(p) for p in paths]
    # Assemble `find` command to gather size, inode, and modification time of files
    # that match the criteria in the arguments
    command = [
        'find',
        # Treat symlinks as files (do not follow them)
        '-P',
    ]
    # Add the files and directories as starting points
    for path in abspaths:
        command.append(str(path))
    # Add prune patterns if given
    for pattern in prune_patterns:
        command.extend(('-ipath', pattern, '-prune', '-or'))
    # Only look for files
    command.extend(('-type', 'f'))
    # Add exclude patterns if given
    for pattern in exclude_patterns:
        command.extend(('-not', '-ipath', pattern))
    # Add size constraints if given
    if isinstance(min_file_size, int) and min_file_size > 0:
        command.extend(('-size', '+{}c'.format(min_file_size - 1)))
    if isinstance(max_file_size, int) and max_file_size > 0:
        command.extend(('-size', '-{}c'.format(max_file_size + 1)))
    # Return a (size, inode, mtime, path) record for each file
    command.extend(('-printf', '%s %i %TY-%Tm-%TdT%TT %p\n'))
    # Run command and process output
    n_files = 0
    for line in run_command_read_out(command):
        # Split the line into 4 pieces using whitespace
        size, inode, mtime, path = line.strip().split(maxsplit=3)
        yield (
            int(size),
            int(inode),
            # Truncate the fractional seconds to 6 digits (microseconds)
            #datetime.strptime(mtime[:26], '%Y-%m-%dT%H:%M:%S.%f'),
            mtime, # Leave as string
            path,
        )
        n_files += 1
    logger = logging.getLogger('find_dups')
    logger.info('Scanned {} files', n_files)


_n_file_extents = 0

def file_extents(path, remove_path=False):
    # Assemble `filefrag` command
    command = [
        'filefrag',
        '-ev',
        path,
    ]
    # Run command
    lines = list(run_command_read_out(command))
    # Remove the occurrences of `path` to make extents comparable
    if remove_path:
        path_pattern = re.compile(re.escape(path))
        lines[1] = path_pattern.sub('*', lines[1])
        lines[-1] = path_pattern.sub('*', lines[-1])
    # Count calls
    global _n_file_extents
    _n_file_extents += 1
    return lines


_create_table_files_sql = """
create table if not exists fmeta (
    path text not null,
    mtime text,
    size int,
    inode int,
    checksum_beg text,
    checksum_end text,
    checksum_all text,
    primary key (path)
)
""".strip()

_create_index_sql = """
create index if not exists {} on fmeta ({})
""".strip()

_select_basic_record_from_files_sql = """
select size, inode, mtime, path from fmeta where path = ?
""".strip()

_insert_into_files_sql = """
insert into fmeta (size, inode, mtime, path) values (?, ?, ?, ?)
""".strip()

_update_files_meta_sql = """
update fmeta set
  size = ?,
  inode = ?,
  mtime = ?,
  checksum_beg = null,
  checksum_end = null,
  checksum_all = null
where path = ?
""".strip()

_select_files_by_size_sql = """
select size, inode, mtime, path, checksum_beg, checksum_end,
    checksum_all
from fmeta
order by size asc
""".strip()

_update_checksums_sql = """
update fmeta
set checksum_beg = ?, checksum_end = ?, checksum_all = ?
where path = ?
""".strip()


def create_tables(db):
    # Start a new transaction
    with db:
        # Create a table to hold the file metadata
        db.execute(_create_table_files_sql)
    # Commit transaction


def create_indexes(db):
    # Start a new transaction
    with db:
        # Create indexes for size and inode
        db.execute(_create_index_sql.format('idx_fmeta_size', 'size'))
        #db.execute(_create_index_sql.format('idx_fmeta_inode', 'inode'))
    # Commit transaction


def load_file_metadata_records(records, db, commit_interval=1000):
    n_inserts = 0
    n_updates = 0
    record = next(records, None)
    while record is not None:
        # Start a new transaction
        with db:
            insert_idx = 0
            while insert_idx < commit_interval and record is not None:
                #print('record:\n', record)
                # Unpack the record
                size, inode, mtime, path = record
                # See what information already exists for this file
                cursor = db.execute(
                    _select_basic_record_from_files_sql, (path,))
                existing_info = cursor.fetchall()
                # Insert or update as necessary
                n_recs = len(existing_info)
                if n_recs == 0:
                    # Insert the current record into the table
                    #print('inserting:\n', record)
                    db.execute(_insert_into_files_sql, record)
                    n_inserts += 1
                elif n_recs == 1:
                    # Update the record only if necessary
                    if existing_info[0] != record:
                        #print('updating:\n', existing_info[0], '\nto:\n', record)
                        db.execute(_update_files_meta_sql, record)
                        n_updates += 1
                else:
                    raise BaseException(
                        'Path has multiple records: {!r}'.format(path))
                # Increment
                insert_idx += 1
                record = next(records, None)
        # Transaction commits
    # Log number of files processed
    logger = logging.getLogger('find_dups')
    logger.info('Inserted metadata for {} files', n_inserts)
    logger.info('Updated metadata for {} files', n_updates)


# TODO remove files that no longer exist from the DB


def load_file_metadata(
        db_filename,
        paths,
        prune_patterns=(),
        exclude_patterns=(),
        min_file_size=None,
        max_file_size=None,
):
    logger = logging.getLogger('find_dups')
    # Connect to the DB
    logger.info('Connecting to DB `{}`', db_filename)
    with sqlite3.connect(db_filename) as db:
        # Create tables (if they don't exist)
        create_tables(db)
        # Gather file metadata
        metadata_records = gather_file_metadata_records(
            paths,
            prune_patterns,
            exclude_patterns,
            min_file_size,
            max_file_size,
        )
        # Load the metadata into the DB
        load_file_metadata_records(metadata_records, db)
        # Create indexes (if they don't exist)
        create_indexes(db)
    # Connection to DB automatically closed
    logger.info('Closed DB `{}`', db_filename)


def sort_slice(lst, start=None, stop=None, key=None, reverse=False):
    if start is None:
        start = 0
    if stop is None:
        stop = len(lst)
    slc = lst[start:stop]
    slc.sort(key=key, reverse=reverse)
    lst[start:stop] = slc


def multikey_sort(lst, keys, reverses=None, start=None, stop=None):
    """
    Sort the given list by the given keys, only evaluating the next key
    if the previous led to ties.
    """
    if not keys or not lst:
        return
    if not reverses:
        reverses = (False,) * len(keys)
    if start is None:
        start = 0
    if stop is None:
        stop = len(lst)
    _multikey_sort(lst, keys, reverses, start, stop)


def _multikey_sort(lst, keys, reverses, start, stop):
    sort_slice(lst, start, stop, keys[0], reverses[0])
    if len(keys) == 1:
        return
    idx = start
    for _, group in itools.groupby(lst[start:stop], key=keys[0]):
        group_size = 0
        for _ in group:
            group_size += 1
        if group_size > 1:
            _multikey_sort(
                lst,
                keys[1:],
                reverses[1:],
                idx,
                idx + group_size,
            )
        idx += group_size


_unix_epoch_datetime = datetime.datetime(1970, 1, 1)


def unix_nanos_to_datetime(ns):
    """Does not account for leap seconds."""
    ms = int(round(ns / 1000))
    td = datetime.timedelta(microseconds=ms)
    return _unix_epoch_datetime + td


_n_checksums = 0

def checksum_file(
        filename,
        chunk_size=(2 ** 10 * 64), # 64KiB
        offset=0,
        hash_name='md5',
        buffer_size=(2 ** 20 * 10), # 10MiB
        stat=None,
):
    # Get the hash function first as a way of checking the argument
    hash_func = hashlib.new(hash_name)
    # Get the file size in order to resolve the offset and chunk size
    logger = logging.getLogger('find_dups')
    if stat is None:
        logger.debug('Stat: {!r}', filename)
        stat = os.stat(filename)
    file_size = stat.st_size
    # Actual chunk size can be at most the file size
    size = min(abs(chunk_size), file_size)
    # Adjust the offset and the chunk size so that they are both
    # positive but represent the same section of the file
    if chunk_size < 0:
        offset -= size
    offset = offset % file_size
    # Read the file
    logger.info('Checksumming file ({}): {!r}@{}+{}',
                hash_name, filename, offset, size)
    buffer_size = min(size, buffer_size, file_size)
    with open(filename, 'rb', buffering=buffer_size) as file:
        # Jump to the start of the requested chunk of data
        file.seek(offset)
        # Checksum the requested chunk of data
        n_bytes_read = 0
        while n_bytes_read < size:
            # How much yet to read
            amount = min(size - n_bytes_read, buffer_size)
            buf = file.read(amount)
            n_bytes_read += len(buf)
            # Incorporate the data into the checksum
            if len(buf) > 0:
                hash_func.update(buf)
            # Break out of loop if EOF
            elif amount != 0:
                break
    # Count calls
    global _n_checksums
    _n_checksums += 1
    # Return the checksum
    return hash_func.hexdigest()


# TODO separate classes for representing file metadata as read from a
# file and fingerprints (which can be saved and loaded irrespective of
# any files)


class FileMeta:

    checksum_size = (2 ** 10 * 64) # 64KiB

    hash_name = 'md5'

    _logger = logging.getLogger('FileMeta')

    def __init__(
            self,
            path,
            size=None,
            mtime=None,
            inode=None,
            checksum_beg=None,
            checksum_end=None,
            checksum_all=None,
    ):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self._path = path
        self._size = size
        self._inode = inode
        self._checksum_beg = checksum_beg
        self._checksum_end = checksum_end
        self._checksum_all = checksum_all
        self._calculated_checksum = False
        self._stat = None
        self._mtime_ns = None
        self._mtime_str = None
        self._extents = None
        if isinstance(mtime, int):
            self._mtime_ns = mtime
        else:
            self._mtime_str = mtime

    @property
    def path(self):
        return self._path

    @property
    def calculated_checksum(self):
        return self._calculated_checksum

    def stat(self):
        if self._stat is None:
            self._logger.debug('Stat: {!r}', self.path)
            self._stat = os.stat(self.path)
            self._called_stat = True
        return self._stat

    def size(self):
        if self._size is None:
            self._size = self.stat().st_size
        return self._size

    def mtime_ns(self):
        if self._mtime_ns is None:
            self._mtime_ns = self.stat().st_mtime_ns
        return self._mtime_ns

    def mtime(self): # TODO call `find` for string with nanoseconds as this implementation currently loses precision (datetime only supports microsecond precision)
        if self._mtime_str is None:
            dt = unix_nanos_to_datetime(self.mtime_ns())
            self._mtime_str = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
        return self._mtime_str

    def inode(self):
        if self._inode is None:
            self._inode = self.stat().st_ino
        return self._inode

    def checksum_beg(self):
        if self._checksum_beg is None:
            self._checksum_beg = checksum_file(
                self.path,
                chunk_size=FileMeta.checksum_size,
                hash_name=FileMeta.hash_name,
                stat=self.stat(),
            )
            self._calculated_checksum = True
        return self._checksum_beg

    def checksum_end(self):
        if self._checksum_end is None:
            if self.size() < FileMeta.checksum_size:
                self._checksum_end = self.checksum_beg()
            else:
                self._checksum_end = checksum_file(
                    self.path,
                    chunk_size=-FileMeta.checksum_size,
                    hash_name=FileMeta.hash_name,
                    stat=self.stat(),
                )
                self._calculated_checksum = True
        return self._checksum_end

    def checksum_all(self):
        if self._checksum_all is None:
            if self.size() < FileMeta.checksum_size:
                self._checksum_all = self.checksum_beg()
            else:
                self._checksum_all = checksum_file(
                    self.path,
                    chunk_size=self.size(),
                    hash_name=FileMeta.hash_name,
                    stat=self.stat(),
                )
                self._calculated_checksum = True
        return self._checksum_all

    def raw_checksums(self):
        return (
            self._checksum_beg, self._checksum_end, self._checksum_all)

    def __repr__(self):
        return (
            'FileMeta(path={!r}, size={!r}, mtime={!r}, inode={!r}, '
            'checksum_beg={!r}, checksum_end={!r}, checksum_all={!r})'
            .format(self._path, self._size, self._mtime_str,
                    self._inode, self._checksum_beg, self._checksum_end,
                    self._checksum_all))

    def extents(self):
        if self._extents is None:
            self._extents = file_extents(self.path, remove_path=True)
        return self._extents


def find_duplicates(db):
        # Get rows that support access by name
        db.row_factory = sqlite3.Row
        # Sort files by size
        cursor = db.execute(_select_files_by_size_sql)
        # Process files in groups of the same size
        for size, size_group in itools.groupby(
                cursor, key=lambda t: t['size']):
            # Convert the records into objects to make them sortable and
            # modifiable
            files = []
            for fmeta_record in size_group:
                try:
                    fmeta = FileMeta(
                        path=fmeta_record['path'],
                        size=fmeta_record['size'],
                        mtime=fmeta_record['mtime'],
                        inode=fmeta_record['inode'],
                        checksum_beg=fmeta_record['checksum_beg'],
                        checksum_end=fmeta_record['checksum_end'],
                        checksum_all=fmeta_record['checksum_all'],
                    )
                    files.append(fmeta)
                # Ignore files that have disappeared
                except FileNotFoundError:
                    pass

            # Skip to the next group if there is only one file
            if len(files) == 1:
                continue

            # Do a multi-key sort: only worry about the next key if the
            # current key (and all earlier keys) are tied.  This
            # calculates checksums only if necessary (due to the lazy
            # nature of the methods).
            multikey_sort(files, (
                operator.methodcaller('checksum_beg'),
                operator.methodcaller('checksum_end'),
                operator.methodcaller('checksum_all'),
            ))
            # TODO avoid checksumming files with same inode

            # Add checksums to the DB
            for fmeta in files:
                if fmeta.calculated_checksum:
                    db.execute(_update_checksums_sql,
                               fmeta.raw_checksums() + (fmeta.path,))

            # Yield the files in groups of duplicates.  Avoid
            # calculating additional checksums.
            for _, dups_group in itools.groupby(
                    files, key=operator.methodcaller('raw_checksums')):
                dups = list(dups_group)
                # Yield only if there are multiple files that match
                if len(dups) > 1:
                    yield dups


# Attributes for picking an original


def pick_orig__path(fmeta, fmetas=None, cli_paths=None):
    return os.path.abspath(fmeta.path)

def pick_orig__basename(fmeta, fmetas=None, cli_paths=None):
    return os.path.basename(fmeta.path)

def pick_orig__cli(fmeta, fmetas=None, cli_paths=None):
    child = os.path.abspath(fmeta.path)
    idx = 0
    for parent in cli_paths:
        if is_child_path(child, os.path.abspath(parent)):
            return idx
        idx += 1
    return idx

def pick_orig__mtime(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_mtime_ns

def pick_orig__atime(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_atime_ns

def pick_orig__ctime(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_ctime_ns

def pick_orig__inode(fmeta, fmetas=None, cli_paths=None):
    return fmeta.inode()

def pick_orig__depth(fmeta, fmetas=None, cli_paths=None):
    path = os.path.normpath(os.path.abspath(fmeta.path))
    path = pathlib.Path(path)
    return len(path.parts) - 1

def pick_orig__n_links(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_nlink

def pick_orig__uid(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_uid

def pick_orig__gid(fmeta, fmetas=None, cli_paths=None):
    return fmeta.stat().st_gid


def partially_apply_args(f, *args):
    return lambda x: f(x, *args)

def mk_pick_original(attr_getters, reverses=None):
    def pick_original(fmetas, cli_paths=None):
        fmetas = list(fmetas)
        keys = []
        for ag in attr_getters:
            keys.append(partially_apply_args(ag, fmetas, cli_paths))
        multikey_sort(fmetas, keys, reverses)
        return fmetas[0]
    return pick_original


def organize_duplicates(duplicates, pick_original, cli_paths=None):
    # Identify the original file
    orig = pick_original(duplicates, cli_paths)
    # Categorize files by relationship to original
    hard_links = []
    ref_links = []
    copies = []
    for dup in duplicates:
        if dup is orig:
            pass
        elif dup.inode() == orig.inode():
            hard_links.append(dup)
        elif dup.extents() == orig.extents():
            ref_links.append(dup)
        else:
            copies.append(dup)
    assert hard_links or ref_links or copies
    # Return organized duplicates
    return (orig, hard_links, ref_links, copies)


# Reports


def report_script(
        organized_duplicates,
        template='ln -fv {orig} {dup}',
        file=sys.stdout,
):
    for orgd_dups in organized_duplicates:
        orig, hard_links, ref_links, dups = orgd_dups
        # Continue with the next group if there were only links
        if not dups:
            continue
        # Output the original for reference
        orig_quoted = shlex.quote(orig.path)
        print('# orig_path={} size={} mtime={} inode={} {}={}'.format(
            orig_quoted, orig.size(), orig.mtime(), orig.inode(),
            FileMeta.hash_name, orig.checksum_all()), file=file)
        # Sort duplicates
        dups.sort(key=lambda d: (d.mtime(), d.inode(), d.path))
        # Output shell commands
        for dup in dups:
            dup_quoted = shlex.quote(dup.path)
            cmd = template.format(orig=orig_quoted, dup=dup_quoted)
            print(cmd, '#', dup.mtime(), dup.inode(), file=file)
        print(file=file)


def report_table(): # TODO
    pass


# Commands


# Alias
scan = load_file_metadata


def report(db_filename, dedup, paths, pick_original):
    logger = logging.getLogger('find_dups')
    # Get the deduplication command template
    ok, dedup, msg = interpret_dedup(dedup)
    if not ok:
        raise ValueError(msg)
    template = (_dedup_styles_to_command_templates[dedup]
                if dedup in _dedup_styles_to_command_templates
                else dedup)
    logger.info('Using deduplication command template: {!r}', template)
    # Do the report
    logger.info('Connecting to DB `{}`', db_filename)
    with sqlite3.connect(db_filename) as db:
        dups_groups = find_duplicates(db)
        orgd_dups = map(
            lambda dups: organize_duplicates(
                dups, pick_original, paths),
            dups_groups)
        report_script(orgd_dups, template=template)
    logger.info('Closed DB `{}`', db_filename)


_command_pattern = re.compile(r'\w+')


_commands = collections.OrderedDict((
    ('scan', scan),
    ('report', report),
))


# Main


_dedup_styles_to_command_templates = {
    'btrfs': 'cp -a --reflink=always {orig} {dup}',
    'hardlink': 'ln -f {orig} {dup}',
    'softlink': 'ln -sf {orig} {dup}',
}


def main_api(
        commands=['scan', 'report'],
        paths=['.'],
        db_filename='find_duplicates.sqlite',
        prune_patterns=[],
        exclude_patterns=[],
        min_file_size=(2 ** 20), # 1 MiB # TODO convert to integer with suffixes à la dd, head
        max_file_size=None,
        pick_original=mk_pick_original(
            (pick_orig__mtime,
             pick_orig__n_links,
             pick_orig__inode,
             pick_orig__path),
            (False, True, False, False),
        ),
        dedup='hardlink',
        verbosity=logging.INFO,
):
    # Get the arguments of this function as a dictionary
    args = locals()
    # Start logging and log runtime environment
    logging.default_config(level=verbosity)
    logger = logging.getLogger(__name__)
    logger.info('find_duplicates.py {}', __version__)
    logger.info('Python {}', sys.version.replace('\n', ' '))
    logger.info('argv: {}', sys.argv)
    logger.info('cwd: {}', os.getcwd())
    logger.info('options:\n{}', pprint.pformat(args))
    # Execute commands in order
    for cmd_name, cmd_func in _commands.items():
        if cmd_name in commands:
            logger.info('Running command: {}', cmd_name)
            signature = inspect.signature(cmd_func)
            kwargs = {k: args.get(k)
                      for k in signature.parameters.keys()}
            cmd_func(**kwargs)
    # Log stats
    logger.info('Calculated {} checksums', _n_checksums)
    logger.info('Retrieved extents of {} files', _n_file_extents)
    # Done!
    logger.info('Done')


# Interpreters for command line options


def interpret_value_required(vals):
    if vals and vals[-1] is not None:
        return True, vals[-1], None
    else:
        return False, None, 'No value given'


def interpret_read_path(path):
    file = files.new(path)
    if file.exists() and file.is_readable():
        return True, path, None
    else:
        return False, None, 'Path does not exist: {!r}'.format(path)


def interpret_keyword(word, keywords, error_message):
    lower_word = word.lower()
    if lower_word in keywords:
        return True, lower_word, None
    else:
        return False, None, error_message.format(
            word=word, keys=', '.join(sorted(keywords)))


def interpret_size(size): # TODO where check for strictly positive size?
    try:
        return True, int(size), None
    except:
        pass
    else:
        return False, None, 'Bad size: {!r}'.format(size)


def interpret_dedup(dedup):
    if dedup in _dedup_styles_to_command_templates:
        return True, dedup, None
    # Use the presence of a space to differentiate deduplication styles
    # and command templates
    elif ' ' not in dedup:
        return (
            False, None,
            'Unrecognized deduplication style: {}\n'
            '    Known styles: {}'.format(
                dedup,
                ' '.join(_dedup_styles_to_command_templates.keys())))
    for placeholder in ('{orig}', '{dup}'):
        if placeholder not in dedup:
            return (
                False, None,
                'No `{}` placeholder in deduplication command '
                'template: {!r}'.format(placeholder, dedup))
    return True, dedup, None


def interpret_verbosity(verbosity):
    if parse.is_int(verbosity):
        return True, int(verbosity), None
    elif verbosity.lower() in logging.levels:
        return True, logging.levels[verbosity.lower()], None
    else:
        return (
            False, None,
            'Unrecognized verbosity: {}\n'
            '    Recognized values: {}'.format(
                verbosity, ' '.join(logging.levels.keys())))


def interpret_pick_original_by(arg):
    keys = []
    revs = []
    attrs = arg.split(',')
    for attr in attrs:
        attr = attr.strip()
        if attr.endswith('<'):
            reverse = False
            attr = attr[:-1].strip()
        elif attr.endswith('>'):
            reverse = True
            attr = attr[:-1].strip()
        else:
            reverse = False
        func = globals().get('pick_orig__' + attr)
        if func is None:
            return (False, None,
                    'Unrecognized attribute: {}\n'
                    '    Recognized values: {}'
                    .format(attr, ' '.join(
                        k[11:] for k in sorted(globals().keys())
                        if k.startswith('pick_orig__'))))
        keys.append(func)
        revs.append(reverse)
    pick_original = mk_pick_original(keys, revs)
    return True, pick_original, None


def compose_interpreters(value, *interpreters):
    ok = True
    message = None
    for interpreter in interpreters:
        ok, value, message = interpreter(value)
        if not ok:
            break
    return ok, value, message


_cli_options = {
    # Options that are really informational commands
    'help': None,
    'version': None,

    # Regular options
    'db': (
        'db_filename',
        interpret_value_required,
    ),
    'prune': (
        'prune_patterns',
        interpret_value_required,
    ),
    'exclude': (
        'exclude_patterns',
        interpret_value_required,
    ),
    'min-size': (
        'min_file_size',
        lambda sizes: compose_interpreters(
            sizes,
            interpret_value_required,
            interpret_size),
    ),
    'max-size': (
        'max_file_size',
        lambda sizes: compose_interpreters(
            sizes,
            interpret_value_required,
            interpret_size),
    ),
    'dedup': (
        'dedup',
        lambda words: compose_interpreters(
            words,
            interpret_value_required,
            interpret_dedup),
    ),
    'verbosity': (
        'verbosity',
        lambda verbosities: compose_interpreters(
            verbosities,
            interpret_value_required,
            interpret_verbosity),
    ),
    'pick-original-by': (
        'pick_original',
        lambda arg: compose_interpreters(
            arg,
            interpret_value_required,
            interpret_pick_original_by),
    ),
}


class CliError(Exception):
    pass


class CliUsageError(CliError):
    pass


def print_usage(prog_name=sys.argv[0], file=sys.stdout):
    usage_msg = 'Usage: {} (<option> | <command>)* <path>*'.format(
        prog_name)
    print(usage_msg, file=file)
    print('Commands:', *_commands.keys(), file=file)
    print('Options: ',
          *('--' + k for k in sorted(_cli_options.keys())),
          file=file)


def print_version(file=sys.stdout):
    print('find_duplicates.py', __version__, file=file)


def main_args(args):
    # Keyword arguments for `main_api`
    kwargs = {}

    # Parse arguments
    options, positional_args = arguments.parse(args)

    # Execute informational commands (which short-circuit regular
    # execution)
    if 'help' in options: # TODO change to actual command
        print_usage()
        return
    if 'version' in options: # TODO change to actual command
        print_version()
        return

    # Separate positional arguments into commands and paths.  The
    # commands are any initial identifier-like strings that are not
    # existing paths.
    commands = []
    pos_arg_idx = 0
    for pos_arg in positional_args:
        if (
                # Arg is a command
                pos_arg.lower() in _commands
                # Or arg looks more like a command than a path
                or (_command_pattern.fullmatch(pos_arg) is not None
                    and not os.path.exists(pos_arg))):
            commands.append(pos_arg)
            pos_arg_idx += 1
        else:
            break
    paths = positional_args[pos_arg_idx:]

    # Validate commands
    commands = [c.lower() for c in commands]
    unrecognized_commands = set(commands) - _commands.keys()
    # Order the unrecognized commands according to the command line to
    # make the error more interpretable
    unrecognized_commands = [
        c for c in commands if c in unrecognized_commands]
    if unrecognized_commands:
        raise CliUsageError('Unrecognized command: {}'
                            .format(unrecognized_commands[0]))
    if commands:
        kwargs['commands'] = commands

    # Validate options
    unrecognized_options = options.keys() - _cli_options.keys()
    if unrecognized_options:
        raise CliUsageError('Unrecognized option: --{}'
                            .format(sorted(unrecognized_options)[0]))
    for opt_name, opt_vals in options.items():
        api_name, interpreter = _cli_options[opt_name]
        ok, val, msg = interpreter(opt_vals)
        if ok:
            kwargs[api_name] = val
        else:
            raise CliUsageError('--{}: {}'.format(opt_name, msg))

    # Validate paths
    for idx, path in enumerate(paths):
        ok, val, msg = interpret_read_path(path)
        if ok:
            paths[idx] = val
        else:
            raise CliError(msg)
    if paths:
        kwargs['paths'] = paths

    # OK, good to go
    main_api(**kwargs)


class ExitStatus(Enum):
    normal = 0
    cli_error = 2


def main_cli():
    exit_status = ExitStatus.normal
    try:
        main_args(sys.argv[1:])
    except CliError as e:
        print('Error:', str(e), file=sys.stderr)
        if isinstance(e, CliUsageError):
            print_usage(file=sys.stderr)
        exit_status = ExitStatus.cli_error
    # Exit with the given status
    sys.exit(exit_status.value)


if __name__ == '__main__':
    main_cli()


# head --bytes 40K Fedora-Workstation-Live-x86_64-26-1.5.iso | md5sum
# tail --bytes 40K Fedora-Workstation-Live-x86_64-26-1.5.iso | md5sum

# TODO parameterize hash
# TODO migrate to `argparse`
# TODO incorporate hash of extents into DB
