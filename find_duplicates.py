"""Finds duplicate files and generates a script to deduplicate them"""

# Copyright (c) 2017 Aubrey Barnard.  This is free software released
# under the MIT License.  See `LICENSE.txt` for details.


import collections
import datetime
import hashlib
import itertools as itools
import operator
import os.path
import pathlib
import shlex
import sqlite3
import subprocess
import sys

from barnapy import logging


def resolve_path(path):
    # Convert to a string path because pathlib doesn't support expanding
    # user directories
    return pathlib.Path(os.path.abspath(os.path.expanduser(str(path))))


def run_command_pipe_errout(command):
    logger = logging.getLogger(__name__ + '.run_command')
    logger.info('Running command: {!r} |& ...',
                ' '.join(shlex.quote(arg) for arg in command))
    with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
    ) as proc:
        for line in proc.stdout:
            yield line


def gather_file_metadata_records(
        paths,
        minimum_file_size=(1024**2), # 1MiB
        maximum_file_size=(1024**5), # 1PiB
):
    # Make sure the paths are absolute
    abspaths = [resolve_path(p) for p in paths]
    # Run `find` to gather size, inode, and modification time of files
    # that fall within a given size range
    command = [
        'find',
        # Treat symlinks as files (do not follow them)
        '-P',
        # Only look for files
        '-type',
        'f',
        # Adjust sizes so that given sizes are included
        '-size',
        '+{}c'.format(minimum_file_size - 1),
        '-size',
        '-{}c'.format(maximum_file_size + 1),
        # Return a (size, inode, mtime, path) record for each file
        '-printf',
        '%s %i %TY-%Tm-%TdT%TT %p\n',
    ]
    # Add the files and directories as starting points
    for idx, path in enumerate(abspaths):
        command.insert(2 + idx, str(path))
    # Run command and process output
    for line in run_command_pipe_errout(command):
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


def load_metadata_records(records, db, commit_interval=1000):
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
                elif n_recs == 1:
                    # Update the record only if necessary
                    if existing_info[0] != record:
                        #print('updating:\n', existing_info[0], '\nto:\n', record)
                        db.execute(_update_files_meta_sql, record)
                else:
                    raise BaseException(
                        'Path has multiple records: {!r}'.format(path))
                # Increment
                insert_idx += 1
                record = next(records, None)
        # Transaction commits
        #print('commit')


# TODO remove files that no longer exist from the DB


def load_metadata(db_filename, paths):
    # Connect to the DB
    db = sqlite3.connect(db_filename)
    # Create tables (if they don't exist)
    create_tables(db)
    # Gather file metadata
    metadata_records = gather_file_metadata_records(
        paths, minimum_file_size=1)
    # Load the metadata into the DB
    load_metadata_records(metadata_records, db)
    # Create indexes (if they don't exist)
    create_indexes(db)
    # Close the connection
    db.close()


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


def checksum_file(
        filename,
        chunk_size=(1024 * 64), # 64KiB
        offset=0,
        hash_name='md5',
        buffer_size=(1024 ** 2 * 10), # 10MiB
        stat=None,
):
    # Get the hash function first as a way of checking the argument
    hash_func = hashlib.new(hash_name)
    # Get the file size in order to resolve the offset and chunk size
    logger = logging.getLogger(__name__ + '.checksum_file')
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
    # Return the checksum
    return hash_func.hexdigest()


# TODO separate classes for representing file metadata as read from a
# file and fingerprints (which can be saved and loaded irrespective of
# any files)


class FileMeta:

    checksum_size = (1024 * 64) # 64KiB

    hash_name = 'md5'

    _logger = logging.getLogger(__name__ + '.FileMeta')

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


def find_duplicates(db):
    with db:
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


def report_script(
        groups_of_duplicates,
        find_original,
        template='ln -fv {orig} {dup}',
        file=sys.stdout,
):
    for dups in groups_of_duplicates:
        # Identify the original file
        orig = find_original(dups)
        # Filter out hard links and the original itself
        dups = [d for d in dups if d.inode() != orig.inode()]
        # Continue with the next group if there were only hard links
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


def find_original_by_inodecount_mtime_inode_path(fmetas):
    # Collect frequency of inodes to detect hard links
    inode_counts = collections.Counter(f.inode() for f in fmetas)
    fmetas.sort(key=lambda f: (
        -inode_counts[f.inode()], f.mtime(), f.inode(), f.path))
    return fmetas[0]


def scan(paths, options):
    if not paths:
        paths = ('.',)
    load_metadata(options['db'], paths)


def report(paths, options):
    db = sqlite3.connect(options['db'])
    dups_groups = find_duplicates(db)
    report_script(
        dups_groups,
        find_original_by_inodecount_mtime_inode_path,
        template=options['cmd'],
    )
    db.close()


_commands = collections.OrderedDict((
    ('scan', scan),
    ('report', report),
))


_default_options = {
    'report_type': 'script',
    'db': 'find_duplicates.sqlite',
    'cmd': 'cp -a --reflink=always {orig} {dup}',
}


def main(args):
    logging.default_config()
    logger = logging.getLogger(__name__ + '.main')
    logger.info('Start')
    commands = set()
    options = dict(_default_options)
    arg_idx = 0
    while arg_idx < len(args) and args[arg_idx] in _commands:
        commands.add(args[arg_idx])
        arg_idx += 1
    if not commands:
        commands = _commands.keys()
    for cmd in _commands:
        if cmd in commands:
            _commands[cmd](args[arg_idx:], options)
    logger.info('Done')


if __name__ == '__main__':
    main(sys.argv[1:])


# head --bytes 40K Fedora-Workstation-Live-x86_64-26-1.5.iso | md5sum
# tail --bytes 40K Fedora-Workstation-Live-x86_64-26-1.5.iso | md5sum

# parameterize hash program
