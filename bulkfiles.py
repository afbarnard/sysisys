"""Utility for working with files en masse."""

# Copyright (c) 2022 Aubrey Barnard.
#
# This is free, open software released under the MIT License.  See
# `LICENSE.txt` or https://choosealicense.com/licenses/mit/ for details.



_create_table_config_sql = '''
create table if not exists config (
    key text not null,
    val text,
    primary key (key) on conflict abort
) without rowid
'''.strip()

_create_table_files_sql = '''
create table if not exists files (
    path text not null,
    size integer,
    mtime_s integer,
    mtime_ns integer,
    cksum_1 text,
    cksum_2 text,
    cksum_3 text,
    cksum_4 text,
    cksum_5 text,
    cksum_all text
) -- implicit, indexed primary key 'rowid'
'''.strip()

_create_index_files_path_sql = '''
create index if not exists idx_files__path on files (path)
'''.strip()

1K
16K
256K
4M
1G
all
