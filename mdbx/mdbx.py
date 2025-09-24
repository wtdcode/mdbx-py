#!/bin/env python3
# Python 3 libmdbx bindings using ctypes
# Copyright 2021 Noel Kuntze <noel.kuntze@contauro.com> for Contauro AG
# Development sponsored by Cloud 4 Job SRL, Italy
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted only as authorized by the OpenLDAP
# Public License.
#
# A copy of this license is available in the file LICENSE in the
# top-level directory of the distribution or, alternatively, at
# <http://www.OpenLDAP.org/license.html>.
#

# needed because we reference Env in TXN and TXN in Env method declarations in the type hints
# and the type hints are evaluated at declaration time until python 3.10.
from __future__ import annotations


import ctypes
import dataclasses
import enum
import errno
import os
from pathlib import Path
import sys
import itertools
from types import TracebackType
from typing import Optional, Iterator, Any, Callable, Type, Literal
from _ctypes import _Pointer
from weakref import ReferenceType
import weakref
import logging

# init lib
SO_FILE = {
    "linux": "libmdbx.so",
    "linux2": "libmdbx.so",
    "darwin": "libmdbx.dylib",
    "win32": "mdbx.dll",
}.get(sys.platform, "libmdbx.so")

_lib_path = Path(__file__).parent.resolve() / "lib" / SO_FILE
_lib = ctypes.CDLL(str(_lib_path.absolute()))

# Names are all CamelCase because PEP 8 states class names have to be CamelCase.
# Abbreviations like TXN (although they are native class names) are capitalized because of PEP 8, too.
#   Env is kept that way though because it's the beginning of Environment
#   (TXN is an abbreviation based on vowels and consonants of the whole word)

"""
Thin abstraction layer for libmdbx
Implements an easy to use API for working with libmdbx databases
It implements in-order memory management to avoid invalid memory access

All C enums and their values are translated into enums and user readable values
Bitwise ORing is implemented for the related enums.

Because it's a thin abstraction, the meaning of all parameters, modes, and constants are the same.

The documentation provided is largely taken from the C API headers.
For the enums, the help texts are only available in the python file because there's no reasonable
way to embed it into the declarations without replicating all declarations in the help text itself

Compare functions are not bound because it is better to handle that

Attribute support is available if it is compiled in libmdbx

Purely internal functions like b-tree traversal related or range query estimation related are not bound

Documentation for libmdbx is at https://erthink.github.io/libmdbx/

Bound functions:

mdbx_cursor_bind
mdbx_cursor_close
mdbx_cursor_copy
mdbx_cursor_count
mdbx_cursor_create
mdbx_cursor_dbi
mdbx_cursor_del
mdbx_cursor_eof
mdbx_cursor_get
mdbx_cursor_get_attr
mdbx_cursor_get_userctx
mdbx_cursor_on_first
mdbx_cursor_on_last
mdbx_cursor_open
mdbx_cursor_put
mdbx_cursor_put_attr
mdbx_cursor_renew
mdbx_cursor_set_userctx
mdbx_cursor_txn
mdbx_dbi_close
mdbx_dbi_open
mdbx_del
mdbx_drop
mdbx_env_close
mdbx_env_close_ex
mdbx_env_create
mdbx_env_get_flags
mdbx_env_get_maxdbs
mdbx_env_get_path
mdbx_env_get_userctx
mdbx_env_info_ex
mdbx_env_open
mdbx_env_set_flags
mdbx_env_set_geometry
mdbx_env_set_maxdbs
mdbx_env_set_maxreaders
mdbx_env_set_syncbytes
mdbx_env_set_syncperiod
mdbx_env_set_userctx
mdbx_env_stat_ex
mdbx_env_sync_ex
mdbx_get
mdbx_get_attr
mdbx_get_sysraminfo
mdbx_is_dirty
mdbx_is_readahead_reasonable
mdbx_liberr2str
mdbx_limits_dbsize_max
mdbx_limits_dbsize_min
mdbx_limits_keysize_max
mdbx_limits_pgsize_max
mdbx_limits_pgsize_min
mdbx_limits_txnsize_max
mdbx_limits_valsize_max
mdbx_put
mdbx_put_attr
mdbx_reader_list
mdbx_set_attr
mdbx_strerror_r
mdbx_thread_register
mdbx_thread_unregister
mdbx_txn_abort
mdbx_txn_begin_ex
mdbx_txn_break
mdbx_txn_commit
mdbx_txn_commit_ex
mdbx_txn_get_userctx
mdbx_txn_id
mdbx_txn_info
mdbx_txn_renew
mdbx_txn_reset
mdbx_txn_set_userctx
mdbx_txn_straggler

Defined prototypes:
MDBX_hsr_func
MDBX_reader_list_func

Not bound:
- mdbx_strerror
  Not working, made redundant by mdbx_strerror_r which is thread safe
- mdbx_strerror_ANSI2OEM
  Not necessary because Python deals with it
- mdbx_strerror_r_ANSI2OEM
  Not necessary because Python deals with it
- any of the short hand functions like mdbx_env_sync or mdbx_env_sync_poll
- any of the functions related to B-tree traversal
- any of the functions for key conversion
- any of the functions for setting comparison functions
- any of the functions for dealing with multiple value storage
- any deprecated function
- any of the debug functions
- mdbx_is_readahead_reasonable

"""

# all enums


class MDBXConstants(enum.IntFlag):
    # The hard limit for DBI handles
    MDBX_MAX_DBI = 32765

    # The maximum size of a data item.
    MDBX_MAXDATASIZE = 0x7FFF0000

    # The minimal database page size in bytes.
    MDBX_MIN_PAGESIZE = 256

    # The maximal database page size in bytes.
    MDBX_MAX_PAGESIZE = 65536


class MDBXLogLevel(enum.IntFlag):
    # Critical conditions i.e. assertion failures
    MDBX_LOG_FATAL = 0

    # Enables logging for error conditions and \ref MDBX_LOG_FATAL
    MDBX_LOG_ERROR = 1

    # Enables logging for warning conditions and \ref MDBX_LOG_ERROR ...
    #    \ref MDBX_LOG_FATAL
    MDBX_LOG_WARN = 2

    # Enables logging for normal but significant condition and
    #    \ref MDBX_LOG_WARN ... \ref MDBX_LOG_FATAL
    MDBX_LOG_NOTICE = 3

    # Enables logging for verbose informational and \ref MDBX_LOG_NOTICE ...
    #    \ref MDBX_LOG_FATAL
    MDBX_LOG_VERBOSE = 4

    # Enables logging for debug-level messages and \ref MDBX_LOG_VERBOSE ...
    #    \ref MDBX_LOG_FATAL
    MDBX_LOG_DEBUG = 5

    # Enables logging for trace debug-level messages and \ref MDBX_LOG_DEBUG ...
    #    \ref MDBX_LOG_FATAL
    MDBX_LOG_TRACE = 6

    # Enables extra debug-level messages (dump pgno lists) and all other log-messages
    MDBX_LOG_EXTRA = 7

    # for \ref mdbx_setup_debug() only: Don't change current settings
    MDBX_LOG_DONTCHANGE = -1


class MDBXDebugFlags(enum.IntFlag):
    # Enable assertion checks.
    # Requires build with \ref MDBX_DEBUG > 0
    MDBX_DBG_ASSERT = 1

    # Enable pages usage audit at commit transactions.
    # Requires build with \ref MDBX_DEBUG > 0
    MDBX_DBG_AUDIT = 2

    # Enable small random delays in critical points.
    # Requires build with \ref MDBX_DEBUG > 0
    MDBX_DBG_JITTER = 4

    # Include or not meta-pages in coredump files.
    # May affect performance in \ref MDBX_WRITEMAP mode
    MDBX_DBG_DUMP = 8

    # Allow multi-opening environment(s)
    MDBX_DBG_LEGACY_MULTIOPEN = 16

    # Allow read and write transactions overlapping for the same thread
    MDBX_DBG_LEGACY_OVERLAP = 32

    # for mdbx_setup_debug() only: Don't change current settings
    MDBX_DBG_DONTCHANGE = -1


# \brief Environment flags
# \ingroup c_opening
# \anchor env_flags
# \see mdbx_env_open() \see mdbx_env_set_flags()
class MDBXEnvFlags(enum.IntFlag):
    MDBX_ENV_DEFAULTS = 0

    # No environment directory.

    # By default, MDBX creates its environment in a directory whose pathname is
    # given in path, and creates its data and lock files under that directory.
    # With this option, path is used as-is for the database main data file.
    # The database lock file is the path with "-lck" appended.

    # - with `MDBX_NOSUBDIR` = in a filesystem we have the pair of MDBX-files
    #   which names derived from given pathname by appending predefined suffixes.

    # - without `MDBX_NOSUBDIR` = in a filesystem we have the MDBX-directory with
    #   given pathname, within that a pair of MDBX-files with predefined names.

    # This flag affects only at new environment creating by \ref mdbx_env_open(
    # otherwise at opening an existing environment libmdbx will choice this
    # automatically./
    MDBX_NOSUBDIR = 0x4000

    # Read only mode.

    # Open the environment in read-only mode. No write operations will be
    # allowed. MDBX will still modify the lock file - except on read-only
    # filesystems, where MDBX does not use locks.

    # - with `MDBX_RDONLY` = open environment in read-only mode.
    #   MDBX supports pure read-only mode (i.e. without opening LCK-file) only
    #   when environment directory and/or both files are not writable (and the
    #   LCK-file may be missing). In such case allowing file(s) to be placed
    #   on a network read-only share.

    # - without `MDBX_RDONLY` = open environment in read-write mode.

    # This flag affects only at environment opening but can't be changed after.

    MDBX_RDONLY = 0x20000

    # Open environment in exclusive/monopolistic mode.

    # `MDBX_EXCLUSIVE` flag can be used as a replacement for `MDB_NOLOCK`
    # which don't supported by MDBX.
    # In this way, you can get the minimal overhead, but with the correct
    # multi-process and multi-thread locking.

    # - with `MDBX_EXCLUSIVE` = open environment in exclusive/monopolistic mode
    #   or return \ref MDBX_BUSY if environment already used by other process.
    #   The main feature of the exclusive mode is the ability to open the
    #   environment placed on a network share.

    # - without `MDBX_EXCLUSIVE` = open environment in cooperative mode
    #   i.e. for multi-process access/interaction/cooperation.
    #   The main requirements of the cooperative mode are:

    #   1. data files MUST be placed in the LOCAL file system
    #      but NOT on a network share.
    #   2. environment MUST be opened only by LOCAL processes
    #      but NOT over a network.
    #   3. OS kernel (i.e. file system and memory mapping implementation) and
    #      all processes that open the given environment MUST be running
    #      in the physically single RAM with cache-coherency. The only
    #      exception for cache-consistency requirement is Linux on MIPS
    #      architecture, but this case has not been tested for a long time).

    # This flag affects only at environment opening but can't be changed after.
    MDBX_EXCLUSIVE = 0x400000

    # Using database/environment which already opened by another process(es).

    # The `MDBX_ACCEDE` flag is useful to avoid \ref MDBX_INCOMPATIBLE error
    # while opening the database/environment which is already used by another
    # process(es) with unknown mode/flags. In such cases, if there is a
    # difference in the specified flags (\ref MDBX_NOMETASYNC
    # \ref MDBX_SAFE_NOSYNC, \ref MDBX_UTTERLY_NOSYNC, \ref MDBX_LIFORECLAIM
    # \ref MDBX_COALESCE and \ref MDBX_NORDAHEAD instead of returning an error
    # the database will be opened in a compatibility with the already used mode.

    # `MDBX_ACCEDE` has no effect if the current process is the only one either
    # opening the DB in read-only mode or other process(es) uses the DB in
    # read-only mode./
    MDBX_ACCEDE = 0x40000000

    # Map data into memory with write permission.

    # Use a writeable memory map unless \ref MDBX_RDONLY is set. This uses fewer
    # mallocs and requires much less work for tracking database pages, but
    # loses protection from application bugs like wild pointer writes and other
    # bad updates into the database. This may be slightly faster for DBs that
    # fit entirely in RAM, but is slower for DBs larger than RAM. Also adds the
    # possibility for stray application writes thru pointers to silently
    # corrupt the database.

    # - with `MDBX_WRITEMAP` = all data will be mapped into memory in the
    #   read-write mode. This offers a significant performance benefit, since the
    #   data will be modified directly in mapped memory and then flushed to disk
    #   by single system call, without any memory management nor copying.

    # - without `MDBX_WRITEMAP` = data will be mapped into memory in the
    #   read-only mode. This requires stocking all modified database pages in
    #   memory and then writing them to disk through file operations.

    # \warning On the other hand, `MDBX_WRITEMAP` adds the possibility for stray
    # application writes thru pointers to silently corrupt the database.

    # \note The `MDBX_WRITEMAP` mode is incompatible with nested transactions
    # since this is unreasonable. I.e. nested transactions requires mallocation
    # of database pages and more work for tracking ones, which neuters a
    # performance boost caused by the `MDBX_WRITEMAP` mode.

    # This flag affects only at environment opening but can't be changed after.
    MDBX_WRITEMAP = 0x80000

    # Tie reader locktable slots to read-only transactions
    # instead of to threads.

    # Don't use Thread-Local Storage, instead tie reader locktable slots to
    # \ref MDBX_txn objects instead of to threads. So, \ref mdbx_txn_reset()
    # keeps the slot reserved for the \ref MDBX_txn object. A thread may use
    # parallel read-only transactions. And a read-only transaction may span
    # threads if you synchronizes its use.

    # Applications that multiplex many user threads over individual OS threads
    # need this option. Such an application must also serialize the write
    # transactions in an OS thread, since MDBX's write locking is unaware of
    # the user threads.

    # \note Regardless to `MDBX_NOTLS` flag a write transaction entirely should
    # always be used in one thread from start to finish. MDBX checks this in a
    # reasonable manner and return the \ref MDBX_THREAD_MISMATCH error in rules
    # violation.

    # This flag affects only at environment opening but can't be changed after.
    MDBX_NOTLS = 0x200000

    # Don't do readahead.

    # Turn off readahead. Most operating systems perform readahead on read
    # requests by default. This option turns it off if the OS supports it.
    # Turning it off may help random read performance when the DB is larger
    # than RAM and system RAM is full.

    # By default libmdbx dynamically enables/disables readahead depending on
    # the actual database size and currently available memory. On the other
    # hand, such automation has some limitation, i.e. could be performed only
    # when DB size changing but can't tracks and reacts changing a free RAM
    # availability, since it changes independently and asynchronously.

    # \note The mdbx_is_readahead_reasonable() function allows to quickly find
    # out whether to use readahead or not based on the size of the data and the
    # amount of available memory.

    # This flag affects only at environment opening and can't be changed after.
    MDBX_NORDAHEAD = 0x800000

    # Don't initialize malloc'ed memory before writing to datafile.

    # Don't initialize malloc'ed memory before writing to unused spaces in the
    # data file. By default, memory for pages written to the data file is
    # obtained using malloc. While these pages may be reused in subsequent
    # transactions, freshly malloc'ed pages will be initialized to zeroes before
    # use. This avoids persisting leftover data from other code (that used the
    # heap and subsequently freed the memory) into the data file.

    # Note that many other system libraries may allocate and free memory from
    # the heap for arbitrary uses. E.g., stdio may use the heap for file I/O
    # buffers. This initialization step has a modest performance cost so some
    # applications may want to disable it using this flag. This option can be a
    # problem for applications which handle sensitive data like passwords, and
    # it makes memory checkers like Valgrind noisy. This flag is not needed
    # with \ref MDBX_WRITEMAP, which writes directly to the mmap instead of using
    # malloc for pages. The initialization is also skipped if \ref MDBX_RESERVE
    # is used; the caller is expected to overwrite all of the memory that was
    # reserved in that case.

    # This flag may be changed at any time using `mdbx_env_set_flags()`./
    MDBX_NOMEMINIT = 0x1000000

    # Aims to coalesce a Garbage Collection items.

    # With `MDBX_COALESCE` flag MDBX will aims to coalesce items while recycling
    # a Garbage Collection. Technically, when possible short lists of pages
    # will be combined into longer ones, but to fit on one database page. As a
    # result, there will be fewer items in Garbage Collection and a page lists
    # are longer, which slightly increases the likelihood of returning pages to
    # Unallocated space and reducing the database file.

    # This flag may be changed at any time using mdbx_env_set_flags()./
    MDBX_COALESCE = 0x2000000

    # LIFO policy for recycling a Garbage Collection items.

    # `MDBX_LIFORECLAIM` flag turns on LIFO policy for recycling a Garbage
    # Collection items, instead of FIFO by default. On systems with a disk
    # write-back cache, this can significantly increase write performance, up
    # to several times in a best case scenario.

    # LIFO recycling policy means that for reuse pages will be taken which became
    # unused the lastest (i.e. just now or most recently). Therefore the loop of
    # database pages circulation becomes as short as possible. In other words
    # the number of pages, that are overwritten in memory and on disk during a
    # series of write transactions, will be as small as possible. Thus creates
    # ideal conditions for the efficient operation of the disk write-back cache.

    # \ref MDBX_LIFORECLAIM is compatible with all no-sync flags, but gives NO
    # noticeable impact in combination with \ref MDBX_SAFE_NOSYNC or
    # \ref MDBX_UTTERLY_NOSYNC. Because MDBX will reused pages only before the
    # last "steady" MVCC-snapshot, i.e. the loop length of database pages
    # circulation will be mostly defined by frequency of calling
    # \ref mdbx_env_sync() rather than LIFO and FIFO difference.

    # This flag may be changed at any time using mdbx_env_set_flags()./
    MDBX_LIFORECLAIM = 0x4000000

    # Debugging option, fill/perturb released pages./
    MDBX_PAGEPERTURB = 0x8000000

    # SYNC MODES****************************************************************
    # \defgroup sync_modes SYNC MODES

    # \attention Using any combination of \ref MDBX_SAFE_NOSYNC, \ref
    # MDBX_NOMETASYNC and especially \ref MDBX_UTTERLY_NOSYNC is always a deal to
    # reduce durability for gain write performance. You must know exactly what
    # you are doing and what risks you are taking!

    # \note for LMDB users: \ref MDBX_SAFE_NOSYNC is NOT similar to LMDB_NOSYNC
    # but \ref MDBX_UTTERLY_NOSYNC is exactly match LMDB_NOSYNC. See details
    # below.

    # THE SCENE:
    # - The DAT-file contains several MVCC-snapshots of B-tree at same time
    #   each of those B-tree has its own root page.
    # - Each of meta pages at the beginning of the DAT file contains a
    #   pointer to the root page of B-tree which is the result of the particular
    #   transaction, and a number of this transaction.
    # - For data durability, MDBX must first write all MVCC-snapshot data
    #   pages and ensure that are written to the disk, then update a meta page
    #   with the new transaction number and a pointer to the corresponding new
    #   root page, and flush any buffers yet again.
    # - Thus during commit a I/O buffers should be flushed to the disk twice;
    #   i.e. fdatasync( FlushFileBuffers() or similar syscall should be
    #   called twice for each commit. This is very expensive for performance
    #   but guaranteed durability even on unexpected system failure or power
    #   outage. Of course, provided that the operating system and the
    #   underlying hardware (e.g. disk) work correctly.

    # TRADE-OFF:
    # By skipping some stages described above, you can significantly benefit in
    # speed, while partially or completely losing in the guarantee of data
    # durability and/or consistency in the event of system or power failure.
    # Moreover, if for any reason disk write order is not preserved, then at
    # moment of a system crash, a meta-page with a pointer to the new B-tree may
    # be written to disk, while the itself B-tree not yet. In that case, the
    # database will be corrupted!

    # \see MDBX_SYNC_DURABLE \see MDBX_NOMETASYNC \see MDBX_SAFE_NOSYNC
    # \see MDBX_UTTERLY_NOSYNC

    # @{/

    # Default robust and durable sync mode.

    # Metadata is written and flushed to disk after a data is written and
    # flushed, which guarantees the integrity of the database in the event
    # of a crash at any time.

    # \attention Please do not use other modes until you have studied all the
    # details and are sure. Otherwise, you may lose your users' data, as happens
    # in [Miranda NG](https://www.miranda-ng.org/) messenger./
    MDBX_SYNC_DURABLE = 0

    # Don't sync the meta-page after commit.

    # Flush system buffers to disk only once per transaction commit, omit the
    # metadata flush. Defer that until the system flushes files to disk
    # or next non-\ref MDBX_RDONLY commit or \ref mdbx_env_sync(). Depending on
    # the platform and hardware, with \ref MDBX_NOMETASYNC you may get a doubling
    # of write performance.

    # This trade-off maintains database integrity, but a system crash may
    # undo the last committed transaction. I.e. it preserves the ACI
    # (atomicity, consistency, isolation) but not D (durability) database
    # property.

    # `MDBX_NOMETASYNC` flag may be changed at any time using
    # \ref mdbx_env_set_flags() or by passing to \ref mdbx_txn_begin() for
    # particular write transaction. \see sync_modes/
    MDBX_NOMETASYNC = 0x40000

    # Don't sync anything but keep previous steady commits.

    # Like \ref MDBX_UTTERLY_NOSYNC the `MDBX_SAFE_NOSYNC` flag disable similarly
    # flush system buffers to disk when committing a transaction. But there is a
    # huge difference in how are recycled the MVCC snapshots corresponding to
    # previous "steady" transactions (see below).

    # With \ref MDBX_WRITEMAP the `MDBX_SAFE_NOSYNC` instructs MDBX to use
    # asynchronous mmap-flushes to disk. Asynchronous mmap-flushes means that
    # actually all writes will scheduled and performed by operation system on it
    # own manner, i.e. unordered. MDBX itself just notify operating system that
    # it would be nice to write data to disk, but no more.

    # Depending on the platform and hardware, with `MDBX_SAFE_NOSYNC` you may get
    # a multiple increase of write performance, even 10 times or more.

    # In contrast to \ref MDBX_UTTERLY_NOSYNC mode, with `MDBX_SAFE_NOSYNC` flag
    # MDBX will keeps untouched pages within B-tree of the last transaction
    # "steady" which was synced to disk completely. This has big implications for
    # both data durability and (unfortunately) performance:
    #  - a system crash can't corrupt the database, but you will lose the last
    #    transactions; because MDBX will rollback to last steady commit since it
    #    kept explicitly.
    #  - the last steady transaction makes an effect similar to "long-lived" read
    #    transaction (see above in the \ref restrictions section) since prevents
    #    reuse of pages freed by newer write transactions, thus the any data
    #    changes will be placed in newly allocated pages.
    #  - to avoid rapid database growth, the system will sync data and issue
    #    a steady commit-point to resume reuse pages, each time there is
    #    insufficient space and before increasing the size of the file on disk.

    # In other words, with `MDBX_SAFE_NOSYNC` flag MDBX insures you from the
    # whole database corruption, at the cost increasing database size and/or
    # number of disk IOPs. So, `MDBX_SAFE_NOSYNC` flag could be used with
    # \ref mdbx_env_sync() as alternatively for batch committing or nested
    # transaction (in some cases). As well, auto-sync feature exposed by
    # \ref mdbx_env_set_syncbytes() and \ref mdbx_env_set_syncperiod() functions
    # could be very useful with `MDBX_SAFE_NOSYNC` flag.

    # The number and volume of of disk IOPs with MDBX_SAFE_NOSYNC flag will
    # exactly the as without any no-sync flags. However, you should expect a
    # larger process's [work set](https://bit.ly/2kA2tFX) and significantly worse
    # a [locality of reference](https://bit.ly/2mbYq2J due to the more
    # intensive allocation of previously unused pages and increase the size of
    # the database.

    # `MDBX_SAFE_NOSYNC` flag may be changed at any time using
    # \ref mdbx_env_set_flags() or by passing to \ref mdbx_txn_begin() for
    # particular write transaction./
    MDBX_SAFE_NOSYNC = 0x10000

    # \deprecated Please use \ref MDBX_SAFE_NOSYNC instead of `MDBX_MAPASYNC`.

    # Since version 0.9.x the `MDBX_MAPASYNC` is deprecated and has the same
    # effect as \ref MDBX_SAFE_NOSYNC with \ref MDBX_WRITEMAP. This just API
    # simplification is for convenience and clarity./
    MDBX_MAPASYNC = MDBX_SAFE_NOSYNC

    # Don't sync anything and wipe previous steady commits.

    # Don't flush system buffers to disk when committing a transaction. This
    # optimization means a system crash can corrupt the database, if buffers are
    # not yet flushed to disk. Depending on the platform and hardware, with
    # `MDBX_UTTERLY_NOSYNC` you may get a multiple increase of write performance
    # even 100 times or more.

    # If the filesystem preserves write order (which is rare and never provided
    # unless explicitly noted) and the \ref MDBX_WRITEMAP and \ref
    # MDBX_LIFORECLAIM flags are not used, then a system crash can't corrupt the
    # database, but you can lose the last transactions, if at least one buffer is
    # not yet flushed to disk. The risk is governed by how often the system
    # flushes dirty buffers to disk and how often \ref mdbx_env_sync() is called.
    # So, transactions exhibit ACI (atomicity, consistency, isolation) properties
    # and only lose `D` (durability). I.e. database integrity is maintained, but
    # a system crash may undo the final transactions.

    # Otherwise, if the filesystem not preserves write order (which is
    # typically) or \ref MDBX_WRITEMAP or \ref MDBX_LIFORECLAIM flags are used
    # you should expect the corrupted database after a system crash.

    # So, most important thing about `MDBX_UTTERLY_NOSYNC`:
    #  - a system crash immediately after commit the write transaction
    #    high likely lead to database corruption.
    #  - successful completion of mdbx_env_sync(force = true) after one or
    #    more committed transactions guarantees consistency and durability.
    #  - BUT by committing two or more transactions you back database into
    #    a weak state, in which a system crash may lead to database corruption!
    #    In case single transaction after mdbx_env_sync, you may lose transaction
    #    itself, but not a whole database.

    # Nevertheless, `MDBX_UTTERLY_NOSYNC` provides "weak" durability in case
    # of an application crash (but no durability on system failure and
    # therefore may be very useful in scenarios where data durability is
    # not required over a system failure (e.g for short-lived data or if you
    # can take such risk.

    # `MDBX_UTTERLY_NOSYNC` flag may be changed at any time using
    # \ref mdbx_env_set_flags( but don't has effect if passed to
    # \ref mdbx_txn_begin() for particular write transaction. \see sync_modes
    MDBX_UTTERLY_NOSYNC = MDBX_SAFE_NOSYNC | 0x100000

    # @} end of SYNC MODES/


class MDBXTXNFlags(enum.IntFlag):
    # Start read-write transaction.
    #
    # Only one write transaction may be active at a time. Writes are fully
    # serialized, which guarantees that writers can never deadlock.
    MDBX_TXN_READWRITE = 0

    # Start read-only transaction.
    #
    # There can be multiple read-only transactions simultaneously that do not
    # block each other and a write transactions.
    MDBX_TXN_RDONLY = MDBXEnvFlags.MDBX_RDONLY

    # Prepare but not start read-only transaction.
    #
    # Transaction will not be started immediately, but created transaction handle
    # will be ready for use with \ref mdbx_txn_renew(). This flag allows to
    # preallocate memory and assign a reader slot, thus avoiding these operations
    # at the next start of the transaction.
    MDBX_TXN_RDONLY_PREPARE = MDBXEnvFlags.MDBX_RDONLY | MDBXEnvFlags.MDBX_NOMEMINIT

    # Do not block when starting a write transaction.
    MDBX_TXN_TRY = 0x10000000

    # Exactly the same as \ref MDBX_NOMETASYNC
    # but for this transaction only
    MDBX_TXN_NOMETASYNC = MDBXEnvFlags.MDBX_NOMETASYNC

    # Exactly the same as \ref MDBX_SAFE_NOSYNC
    # but for this transaction only
    MDBX_TXN_NOSYNC = MDBXEnvFlags.MDBX_SAFE_NOSYNC

    def is_read_only(self) -> bool:
        return self == MDBXTXNFlags.MDBX_TXN_RDONLY

    def is_read_write(self) -> bool:
        return self == MDBXTXNFlags.MDBX_TXN_READWRITE


class MDBXDBFlags(enum.IntFlag):
    def from_param(self) -> int:
        return int(self)

    MDBX_DB_DEFAULTS = 0

    # Use reverse string keys
    MDBX_REVERSEKEY = 0x02

    # Use sorted duplicates, i.e. allow multi-values
    MDBX_DUPSORT = 0x04

    # Numeric keys in native byte order either uint32_t or uint64_t. The keys
    # must all be of the same size and must be aligned while passing as
    # arguments.
    MDBX_INTEGERKEY = 0x08

    # With \ref MDBX_DUPSORT; sorted dup items have fixed size
    MDBX_DUPFIXED = 0x10

    # With \ref MDBX_DUPSORT and with \ref MDBX_DUPFIXED; dups are fixed size
    # \ref MDBX_INTEGERKEY -style integers. The data values must all be of the
    # same size and must be aligned while passing as arguments.
    MDBX_INTEGERDUP = 0x20

    # With \ref MDBX_DUPSORT; use reverse string comparison
    MDBX_REVERSEDUP = 0x40

    # Create DB if not already existing
    MDBX_CREATE = 0x40000

    # Opens an existing sub-database created with unknown flags.
    #
    # The `MDBX_DB_ACCEDE` flag is intend to open a existing sub-database which
    # was created with unknown flags (\ref MDBX_REVERSEKEY, \ref MDBX_DUPSORT
    # \ref MDBX_INTEGERKEY, \ref MDBX_DUPFIXED, \ref MDBX_INTEGERDUP and
    # \ref MDBX_REVERSEDUP).
    #
    # In such cases, instead of returning the \ref MDBX_INCOMPATIBLE error, the
    # sub-database will be opened with flags which it was created, and then an
    # application could determine the actual flags by \ref mdbx_dbi_flags().
    MDBX_DB_ACCEDE = MDBXEnvFlags.MDBX_ACCEDE


class MDBXPutFlags(enum.IntFlag):
    def from_param(self) -> int:
        return int(self)

    # Upsertion by default (without any other flags)
    MDBX_UPSERT = 0

    # For insertion: Don't write if the key already exists.
    MDBX_NOOVERWRITE = 0x10

    # Has effect only for \ref MDBX_DUPSORT databases.
    # For upsertion: don't write if the key-value pair already exist.
    # For deletion: remove all values for key.
    MDBX_NODUPDATA = 0x20

    # For upsertion: overwrite the current key/data pair.
    # MDBX allows this flag for \ref mdbx_put() for explicit overwrite/update
    # without insertion.
    # For deletion: remove only single entry at the current cursor position.
    MDBX_CURRENT = 0x40

    # Has effect only for \ref MDBX_DUPSORT databases.
    # For deletion: remove all multi-values (aka duplicates) for given key.
    # For upsertion: replace all multi-values for given key with a new one.
    MDBX_ALLDUPS = 0x80

    # For upsertion: Just reserve space for data, don't copy it.
    # Return a pointer to the reserved space.
    MDBX_RESERVE = 0x10000

    # Data is being appended.
    # Don't split full pages, continue on a new instead.
    MDBX_APPEND = 0x20000

    # Has effect only for \ref MDBX_DUPSORT databases.
    # Duplicate data is being appended.
    # Don't split full pages, continue on a new instead.
    MDBX_APPENDDUP = 0x40000

    # Only for \ref MDBX_DUPFIXED.
    # Store multiple data items in one call.
    MDBX_MULTIPLE = 0x80000


# \brief Environment copy flags
# \ingroup c_extra
# \see mdbx_env_copy() \see mdbx_env_copy2fd()


class MDBXCopyFlags(enum.IntFlag):
    MDBX_CP_DEFAULTS = 0

    # Copy with compactification: Omit free space from copy and renumber all
    # pages sequentially
    MDBX_CP_COMPACT = 1

    # Force to make resizeable copy, i.e. dynamic size instead of fixed
    MDBX_CP_FORCE_DYNAMIC_SIZE = 2


class CEnum(enum.IntEnum):
    def from_param(self) -> int:
        return int(self)


class MDBXCursorOp(CEnum):
    # Position at first key/data item
    MDBX_FIRST = 0

    # \ref MDBX_DUPSORT -only: Position at first data item of current key.
    MDBX_FIRST_DUP = 1

    # \ref MDBX_DUPSORT -only: Position at key/data pair.
    MDBX_GET_BOTH = 2

    # \ref MDBX_DUPSORT -only: Position at given key and at first data greater
    # than or equal to specified data.
    MDBX_GET_BOTH_RANGE = 3

    # Return key/data at current cursor position
    MDBX_GET_CURRENT = 4

    # \ref MDBX_DUPFIXED -only: Return up to a page of duplicate data items
    # from current cursor position. Move cursor to prepare
    # for \ref MDBX_NEXT_MULTIPLE.
    MDBX_GET_MULTIPLE = 5

    # Position at last key/data item
    MDBX_LAST = 6

    # \ref MDBX_DUPSORT -only: Position at last data item of current key.
    MDBX_LAST_DUP = 7

    # Position at next data item
    MDBX_NEXT = 8

    # \ref MDBX_DUPSORT -only: Position at next data item of current key.
    MDBX_NEXT_DUP = 9

    # \ref MDBX_DUPFIXED -only: Return up to a page of duplicate data items
    # from next cursor position. Move cursor to prepare
    # for `MDBX_NEXT_MULTIPLE`.
    MDBX_NEXT_MULTIPLE = 10

    # Position at first data item of next key
    MDBX_NEXT_NODUP = 11

    # Position at previous data item
    MDBX_PREV = 12

    # \ref MDBX_DUPSORT -only: Position at previous data item of current key.
    MDBX_PREV_DUP = 13

    # Position at last data item of previous key
    MDBX_PREV_NODUP = 14

    # Position at specified key
    MDBX_SET = 15

    # Position at specified key, return both key and data
    MDBX_SET_KEY = 16

    # Position at first key greater than or equal to specified key.
    MDBX_SET_RANGE = 17

    # \ref MDBX_DUPFIXED -only: Position at previous page and return up to
    # a page of duplicate data items.
    MDBX_PREV_MULTIPLE = 18

    # Position at first key-value pair greater than or equal to specified
    # return both key and data, and the return code depends on a exact match.
    #
    # For non DUPSORT-ed collections this work the same to \ref MDBX_SET_RANGE
    # but returns \ref MDBX_SUCCESS if key found exactly and
    # \ref MDBX_RESULT_TRUE if greater key was found.
    #
    # For DUPSORT-ed a data value is taken into account for duplicates
    # i.e. for a pairs/tuples of a key and an each data value of duplicates.
    # Returns \ref MDBX_SUCCESS if key-value pair found exactly and
    # \ref MDBX_RESULT_TRUE if the next pair was returned.
    MDBX_SET_LOWERBOUND = 19

    # Positions cursor at first key-value pair greater than specified,
    # return both key and data, and the return code depends on whether a
    # upper-bound was found.
    #
    # For non DUPSORT-ed collections this work like \ref MDBX_SET_RANGE,
    # but returns \ref MDBX_SUCCESS if the greater key was found or
    # \ref MDBX_NOTFOUND otherwise.
    #
    # For DUPSORT-ed a data value is taken into account for duplicates,
    # i.e. for a pairs/tuples of a key and an each data value of duplicates.
    # Returns \ref MDBX_SUCCESS if the greater pair was returned or
    # \ref MDBX_NOTFOUND otherwise.
    MDBX_SET_UPPERBOUND = 20

    # Doubtless cursor positioning at a specified key.
    MDBX_TO_KEY_LESSER_THAN = 21
    MDBX_TO_KEY_LESSER_OR_EQUAL = 22
    MDBX_TO_KEY_EQUAL = 23
    MDBX_TO_KEY_GREATER_OR_EQUAL = 24
    MDBX_TO_KEY_GREATER_THAN = 25

    # Doubtless cursor positioning at a specified key-value pair
    # for dupsort/multi-value hives.
    MDBX_TO_EXACT_KEY_VALUE_LESSER_THAN = 26
    MDBX_TO_EXACT_KEY_VALUE_LESSER_OR_EQUAL = 27
    MDBX_TO_EXACT_KEY_VALUE_EQUAL = 28
    MDBX_TO_EXACT_KEY_VALUE_GREATER_OR_EQUAL = 29
    MDBX_TO_EXACT_KEY_VALUE_GREATER_THAN = 30

    # Doubtless cursor positioning at a specified key-value pair
    # for dupsort/multi-value hives.
    MDBX_TO_PAIR_LESSER_THAN = 31
    MDBX_TO_PAIR_LESSER_OR_EQUAL = 32
    MDBX_TO_PAIR_EQUAL = 33
    MDBX_TO_PAIR_GREATER_OR_EQUAL = 34
    MDBX_TO_PAIR_GREATER_THAN = 35

    # \ref MDBX_DUPFIXED -only: Seek to given key and return up to a page of
    # duplicate data items from current cursor position. Move cursor to prepare
    # for \ref MDBX_NEXT_MULTIPLE. \see MDBX_GET_MULTIPLE
    MDBX_SEEK_AND_GET_MULTIPLE = 36


class MDBXError(enum.IntFlag):
    # Successful result
    MDBX_SUCCESS = 0

    # Alias for \ref MDBX_SUCCESS
    MDBX_RESULT_FALSE = MDBX_SUCCESS

    # Successful result with special meaning or a flag
    MDBX_RESULT_TRUE = -1

    # key/data pair already exists
    MDBX_KEYEXIST = -30799

    # The first LMDB-compatible defined error code
    MDBX_FIRST_LMDB_ERRCODE = MDBX_KEYEXIST

    # key/data pair not found (EOF)
    MDBX_NOTFOUND = -30798

    # Requested page not found - this usually indicates corruption
    MDBX_PAGE_NOTFOUND = -30797

    # Database is corrupted (page was wrong type and so on)
    MDBX_CORRUPTED = -30796

    # Environment had fatal error
    # i.e. update of meta page failed and so on.
    MDBX_PANIC = -30795

    # DB file version mismatch with libmdbx
    MDBX_VERSION_MISMATCH = -30794

    # File is not a valid MDBX file
    MDBX_INVALID = -30793

    # Environment mapsize reached
    MDBX_MAP_FULL = -30792

    # Environment maxdbs reached
    MDBX_DBS_FULL = -30791

    # Environment maxreaders reached
    MDBX_READERS_FULL = -30790

    # Transaction has too many dirty pages, i.e transaction too big
    MDBX_TXN_FULL = -30788

    # Cursor stack too deep - this usually indicates corruption
    # i.e branch-pages loop
    MDBX_CURSOR_FULL = -30787

    # Page has not enough space - internal error
    MDBX_PAGE_FULL = -30786

    # Database engine was unable to extend mapping, e.g. since address space
    # is unavailable or busy. This can mean:
    #  - Database size extended by other process beyond to environment mapsize
    #    and engine was unable to extend mapping while starting read
    #    transaction. Environment should be reopened to continue.
    #  - Engine was unable to extend mapping during write transaction
    #    or explicit call of \ref mdbx_env_set_geometry().
    MDBX_UNABLE_EXTEND_MAPSIZE = -30785

    # Environment or database is not compatible with the requested operation
    # or the specified flags. This can mean:
    #  - The operation expects an \ref MDBX_DUPSORT / \ref MDBX_DUPFIXED
    #    database.
    #  - Opening a named DB when the unnamed DB has \ref MDBX_DUPSORT /
    #    \ref MDBX_INTEGERKEY.
    #  - Accessing a data record as a database, or vice versa.
    #  - The database was dropped and recreated with different flags.
    MDBX_INCOMPATIBLE = -30784

    # Invalid reuse of reader locktable slot
    # e.g. read-transaction already run for current thread
    MDBX_BAD_RSLOT = -30783

    # Transaction is not valid for requested operation
    # e.g. had errored and be must aborted, has a child, or is invalid
    MDBX_BAD_TXN = -30782

    # Invalid size or alignment of key or data for target database
    # either invalid subDB name
    MDBX_BAD_VALSIZE = -30781

    # The specified DBI-handle is invalid
    # or changed by another thread/transaction
    MDBX_BAD_DBI = -30780

    # Unexpected internal error, transaction should be aborted
    MDBX_PROBLEM = -30779

    # The last LMDB-compatible defined error code
    MDBX_LAST_LMDB_ERRCODE = MDBX_PROBLEM

    # Another write transaction is running or environment is already used while
    # opening with \ref MDBX_EXCLUSIVE flag
    MDBX_BUSY = -30778

    # The first of MDBX-added error codes
    MDBX_FIRST_ADDED_ERRCODE = MDBX_BUSY

    # The specified key has more than one associated value
    MDBX_EMULTIVAL = -30421

    # Bad signature of a runtime object(s), this can mean:
    #  - memory corruption or double-free;
    #  - ABI version mismatch (rare case);
    MDBX_EBADSIGN = -30420

    # Database should be recovered, but this could NOT be done for now
    # since it opened in read-only mode
    MDBX_WANNA_RECOVERY = -30419

    # The given key value is mismatched to the current cursor position
    MDBX_EKEYMISMATCH = -30418

    # Database is too large for current system
    # e.g. could NOT be mapped into RAM.
    MDBX_TOO_LARGE = -30417

    # A thread has attempted to use a not owned object
    # e.g. a transaction that started by another thread.
    MDBX_THREAD_MISMATCH = -30416

    # Overlapping read and write transactions for the current thread
    MDBX_TXN_OVERLAPPING = -30415

    # The last of MDBX-added error codes
    MDBX_LAST_ADDED_ERRCODE = MDBX_TXN_OVERLAPPING

    MDBX_ENODATA = errno.ENODATA
    MDBX_EINVAL = errno.EINVAL
    MDBX_EACCES = errno.EACCES
    MDBX_ENOMEM = errno.ENOMEM
    MDBX_EROFS = errno.EROFS
    MDBX_ENOSYS = errno.ENOSYS
    MDBX_EIO = errno.EIO
    MDBX_EPERM = errno.EPERM
    MDBX_EINTR = errno.EINTR
    MDBX_ENOFILE = errno.ENOENT
    MDBX_EREMOTE = 15  # Win32 doesn't have this


class MDBXOption(CEnum):
    MDBX_opt_max_db = 0
    MDBX_opt_max_readers = 1
    MDBX_opt_sync_bytes = 2
    MDBX_opt_sync_period = 3
    MDBX_opt_rp_augment_limit = 4
    MDBX_opt_loose_limit = 5
    MDBX_opt_dp_reserve_limit = 6
    MDBX_opt_txn_dp_limit = 7
    MDBX_opt_txn_dp_initial = 8
    MDBX_opt_spill_max_denominator = 9
    MDBX_opt_spill_min_denominator = 10
    MDBX_opt_spill_parent4child_denominator = 11


class MDBXEnvDeleteMode(CEnum):
    MDBX_ENV_JUST_DELETE = 0
    MDBX_ENV_ENSURE_UNUSED = 1
    MDBX_ENV_WAIT_FOR_UNUSED = 2


class MDBXDBIState(enum.IntFlag):
    MDBX_DBI_DIRTY = 0x01
    MDBX_DBI_STALE = 0x02
    MDBX_DBI_FRESH = 0x04
    MDBX_DBI_CREAT = 0x08


class MDBXPageType(CEnum):
    MDBX_page_broken = 0
    MDBX_page_meta = 1
    MDBX_page_large = 2
    MDBX_page_branch = 3
    MDBX_page_leaf = 4
    MDBX_page_dupfixed_leaf = 5
    MDBX_subpage_leaf = 6
    MDBX_subpage_dupfixed_leaf = 7
    MDBX_subpage_broken = 8


class MDBXCopyMode(CEnum):
    MDBX_CP_DEFAULTS = 0

    # Copy with compactification: Omit free space from copy and renumber all
    # pages sequentially
    MDBX_CP_COMPACT = 1

    # Force to make resizeable copy, i.e. dynamic size instead of fixed
    MDBX_CP_FORCE_DYNAMIC_SIZE = 2


class MDBXBuildInfo(ctypes.Structure):
    """
    brief libmdbx build information
    attention Some strings could be NULL in case no corresponding information
    was provided at build time (i.e. flags).
    extern LIBMDBX_VERINFO_API const struct MDBX_build_info {
        const char *datetime; /**< build timestamp (ISO-8601 or __DATE__ __TIME__) */
        const char *target;   /**< cpu/arch-system-config triplet */
        const char *options;  /**< mdbx-related options */
        const char *compiler; /**< compiler */
        const char *flags;    /**< CFLAGS and CXXFLAGS */
    }
    """

    _fields_ = [
        ("datetime", ctypes.c_char_p),
        ("target", ctypes.c_char_p),
        ("options", ctypes.c_char_p),
        ("compiler", ctypes.c_char_p),
        ("flags", ctypes.c_char_p),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "datetime": self.datetime,
                "target": self.target,
                "options": self.options,
                "compiler": self.compiler,
                "flags": self.flags,
            }
        )


class MDBXVersionInfo(ctypes.Structure):
    """
    brief libmdbx version information
    extern LIBMDBX_VERINFO_API const struct MDBX_version_info {
        uint8_t major;     /**< Major version number */
        uint8_t minor;     /**< Minor version number */
        uint16_t release;  /**< Release number of Major.Minor */
        uint32_t revision; /**< Revision number of Release */
        struct {
            const char *datetime; /**< committer date, strict ISO-8601 format */
            const char *tree;     /**< commit hash (hexadecimal digits) */
            const char *commit;   /**< tree hash, i.e. digest of the source code */
            const char *describe; /**< git-describe string */
        } git;                  /**< source information from git */
        const char *sourcery;   /**< sourcery anchor for pinning */
    }
    """

    _fields_ = [
        ("major", ctypes.c_uint8),
        ("minor", ctypes.c_uint8),
        ("release", ctypes.c_uint16),
        ("revision", ctypes.c_uint32),
        ("datetime", ctypes.c_char_p),
        ("tree", ctypes.c_char_p),
        ("commit", ctypes.c_char_p),
        ("describe", ctypes.c_char_p),
        ("sourcery", ctypes.c_char_p),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "major": self.major,
                "minor": self.minor,
                "release": self.release,
                "revision": self.revision,
                "datetime": self.datetime,
                "tree": self.tree,
                "commit": self.commit,
                "describe": self.describe,
                "sourcery": self.sourcery,
            }
        )


class MDBXStat(ctypes.Structure):
    """
    brief Statistics for a database in the environment
    see mdbx_env_stat_ex() see mdbx_dbi_stat() */
    struct MDBX_stat {
      uint32_t ms_psize; /**< Size of a database page. This is the same for all
                            databases. */
      uint32_t ms_depth; /**< Depth (height) of the B-tree */
      uint64_t ms_branch_pages;   /**< Number of internal (non-leaf) pages */
      uint64_t ms_leaf_pages;     /**< Number of leaf pages */
      uint64_t ms_overflow_pages; /**< Number of overflow pages */
      uint64_t ms_entries;        /**< Number of data items */
      uint64_t ms_mod_txnid; /**< Transaction ID of committed last modification */
    };
    """

    _fields_ = [
        ("ms_psize", ctypes.c_uint32),
        ("ms_depth", ctypes.c_uint32),
        ("ms_branch_pages", ctypes.c_uint64),
        ("ms_leaf_pages", ctypes.c_uint64),
        ("ms_overflow_pages", ctypes.c_uint64),
        ("ms_entries", ctypes.c_uint64),
        ("ms_mod_txnid", ctypes.c_uint64),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "ms_psize": self.ms_psize,
                "ms_depth": self.ms_depth,
                "ms_branch_pages": self.ms_branch_pages,
                "ms_leaf_pages": self.ms_leaf_pages,
                "ms_overflow_pages": self.ms_overflow_pages,
                "ms_entries": self.ms_entries,
                "ms_mod_txnid": self.ms_mod_txnid,
            }
        )


class MDBXMiGeo(ctypes.Structure):
    """
    brief Information about the environment
    struct MDBX_envinfo {
      struct {
        uint64_t lower;   /**< Lower limit for datafile size */
        uint64_t upper;   /**< Upper limit for datafile size */
        uint64_t current; /**< Current datafile size */
        uint64_t shrink;  /**< Shrink threshold for datafile */
        uint64_t grow;    /**< Growth step for datafile */
      } mi_geo;
    """

    _fields_ = [
        ("lower", ctypes.c_uint64),
        ("upper", ctypes.c_uint64),
        ("current", ctypes.c_uint64),
        ("shrink", ctypes.c_uint64),
        ("grow", ctypes.c_uint64),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "lower": self.lower,
                "upper": self.upper,
                "current": self.current,
                "shrink": self.shrink,
                "grow": self.grow,
            }
        )


class MDBXEnvinfoCurrent(ctypes.Structure):
    _fields_ = [("x", ctypes.c_uint64), ("y", ctypes.c_uint64)]

    def __repr__(self) -> str:
        return str({"x": self.x, "y": self.y})


class MDBXEnvinfoMeta0(ctypes.Structure):
    _fields_ = [("x", ctypes.c_uint64), ("y", ctypes.c_uint64)]

    def __repr__(self) -> str:
        return str({"x": self.x, "y": self.y})


class MDBXEnvinfoMeta1(ctypes.Structure):
    _fields_ = [("x", ctypes.c_uint64), ("y", ctypes.c_uint64)]

    def __repr__(self) -> str:
        return str({"x": self.x, "y": self.y})


class MDBXEnvinfoMeta2(ctypes.Structure):
    _fields_ = [("x", ctypes.c_uint64), ("y", ctypes.c_uint64)]

    def __repr__(self) -> str:
        return str({"x": self.x, "y": self.y})


class MDBXEnvinfo_mi_bootid(ctypes.Structure):
    _fields_ = [
        ("current", MDBXEnvinfoCurrent),
        ("meta0", MDBXEnvinfoMeta0),
        ("meta1", MDBXEnvinfoMeta1),
        ("meta2", MDBXEnvinfoMeta2),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "current": self.current,
                "meta0": self.meta0,
                "meta1": self.meta1,
                "meta2": self.meta2,
            }
        )


class MDBXEnvinfo(ctypes.Structure):
    """
    brief Information about the environment
    ingroup c_statinfo
    see mdbx_env_info_ex() */
    struct MDBX_envinfo {
      struct {
        uint64_t lower;   /**< Lower limit for datafile size */
        uint64_t upper;   /**< Upper limit for datafile size */
        uint64_t current; /**< Current datafile size */
        uint64_t shrink;  /**< Shrink threshold for datafile */
        uint64_t grow;    /**< Growth step for datafile */
      } mi_geo;
      uint64_t mi_mapsize;             /**< Size of the data memory map */
      uint64_t mi_last_pgno;           /**< Number of the last used page */
      uint64_t mi_recent_txnid;        /**< ID of the last committed transaction */
      uint64_t mi_latter_reader_txnid; /**< ID of the last reader transaction */
      uint64_t mi_self_latter_reader_txnid; /**< ID of the last reader transaction
                                               of caller process */
      uint64_t mi_meta0_txnid, mi_meta0_sign;
      uint64_t mi_meta1_txnid, mi_meta1_sign;
      uint64_t mi_meta2_txnid, mi_meta2_sign;
      uint32_t mi_maxreaders;   /**< Total reader slots in the environment */
      uint32_t mi_numreaders;   /**< Max reader slots used in the environment */
      uint32_t mi_dxb_pagesize; /**< Database pagesize */
      uint32_t mi_sys_pagesize; /**< System pagesize */

      brief A mostly unique ID that is regenerated on each boot.

       As such it can be used to identify the local machine's current boot. MDBX
       uses such when open the database to determine whether rollback required to
       the last steady sync point or not. I.e. if current bootid is differ from the
       value within a database then the system was rebooted and all changes since
       last steady sync must be reverted for data integrity. Zeros mean that no
       relevant information is available from the system. */
      struct {
        struct {
          uint64_t x, y;
        } current, meta0, meta1, meta2;
      } mi_bootid;

      /** Bytes not explicitly synchronized to disk */
      uint64_t mi_unsync_volume;
      /** Current auto-sync threshold, see mdbx_env_set_syncbytes(). */
      uint64_t mi_autosync_threshold;
      /** Time since the last steady sync in 1/65536 of second */
      uint32_t mi_since_sync_seconds16dot16;
      /** Current auto-sync period in 1/65536 of second,
       * see mdbx_env_set_syncperiod(). */
      uint32_t mi_autosync_period_seconds16dot16;
      /** Time since the last readers check in 1/65536 of second,
       * see mdbx_reader_check(). */
      uint32_t mi_since_reader_check_seconds16dot16;
      /** Current environment mode.
       * The same as mdbx_env_get_flags() returns. */
      uint32_t mi_mode;

      /** Statistics of page operations.
       * Overall statistics of page operations of all (running, completed
       * and aborted) transactions in the current multi-process session (since the
       * first process opened the database after everyone had previously closed it).
       */
      struct {
        uint64_t newly;   /**< Quantity of a new pages added */
        uint64_t cow;     /**< Quantity of pages copied for update */
        uint64_t clone;   /**< Quantity of parent's dirty pages clones
                               for nested transactions */
        uint64_t split;   /**< Page splits */
        uint64_t merge;   /**< Page merges */
        uint64_t spill;   /**< Quantity of spilled dirty pages */
        uint64_t unspill; /**< Quantity of unspilled/reloaded pages */
        uint64_t wops;    /**< Number of explicit write operations (not a pages)
                               to a disk */
      } mi_pgop_stat;
    };

    """

    _fields_ = [
        ("MDBXMiGeo", MDBXMiGeo),
        ("mi_mapsize", ctypes.c_uint64),
        ("mi_last_pgno", ctypes.c_uint64),
        ("mi_recent_txnid", ctypes.c_uint64),
        ("mi_latter_reader_txnid", ctypes.c_uint64),
        ("mi_self_latter_reader_txnid", ctypes.c_uint64),
        ("mi_meta0_txnid", ctypes.c_uint64),
        ("mi_meta0_sign", ctypes.c_uint64),
        ("mi_meta1_txnid", ctypes.c_uint64),
        ("mi_meta1_sign", ctypes.c_uint64),
        ("mi_meta2_txnid", ctypes.c_uint64),
        ("mi_meta2_sign", ctypes.c_uint64),
        ("mi_maxreaders", ctypes.c_uint32),
        ("mi_numreaders", ctypes.c_uint32),
        ("mi_dxb_pagesize", ctypes.c_uint32),
        ("mi_sys_pagesize", ctypes.c_uint32),
        ("mi_bootid", MDBXEnvinfo_mi_bootid),
        ("mi_unsync_volume", ctypes.c_uint64),
        ("mi_autosync_threshold", ctypes.c_uint64),
        ("mi_since_sync_seconds16dot16", ctypes.c_uint32),
        ("mi_autosync_period_seconds16dot16", ctypes.c_uint32),
        ("mi_since_reader_check_seconds16dot16", ctypes.c_uint32),
        ("mi_mode", ctypes.c_uint32),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "MDBXMiGeo": self.MDBXMiGeo,
                "mi_mapsize": self.mi_mapsize,
                "mi_last_pgno": self.mi_last_pgno,
                "mi_recent_txnid": self.mi_recent_txnid,
                "mi_latter_reader_txnid": self.mi_latter_reader_txnid,
                "mi_self_latter_reader_txnid": self.mi_self_latter_reader_txnid,
                "mi_meta0_txnid": self.mi_meta0_txnid,
                "mi_meta0_sign": self.mi_meta0_sign,
                "mi_meta1_txnid": self.mi_meta1_txnid,
                "mi_meta1_sign": self.mi_meta1_sign,
                "mi_meta2_txnid": self.mi_meta2_txnid,
                "mi_meta2_sign": self.mi_meta2_sign,
                "mi_maxreaders": self.mi_maxreaders,
                "mi_numreaders": self.mi_numreaders,
                "mi_dxb_pagesize": self.mi_dxb_pagesize,
                "mi_sys_pagesize": self.mi_sys_pagesize,
                "mi_bootid": self.mi_bootid,
                "mi_unsync_volume": self.mi_unsync_volume,
                "mi_autosync_threshold": self.mi_autosync_threshold,
                "mi_since_sync_seconds16dot16": self.mi_since_sync_seconds16dot16,
                "mi_autosync_period_seconds16dot16": self.mi_autosync_period_seconds16dot16,
                "mi_since_reader_check_seconds16dot16": self.mi_since_reader_check_seconds16dot16,
                "mi_mode": self.mi_mode,
            }
        )


class MDBXCommitLatency(ctypes.Structure):
    """
    brief Latency of commit stages in 1/65536 of seconds units.
    warning This structure may be changed in future releases.
    see mdbx_txn_commit_ex() */
    struct MDBX_commit_latency {
      /** Duration of preparation (commit child transactions, update
       * sub-databases records and cursors destroying). */
      uint32_t preparation;
      /** Duration of GC/freeDB handling & updation. */
      uint32_t gc;
      /** Duration of internal audit if enabled. */
      uint32_t audit;
      /** Duration of writing dirty/modified data pages. */
      uint32_t write;
      /** Duration of syncing written data to the dist/storage. */
      uint32_t sync;
      /** Duration of transaction ending (releasing resources). */
      uint32_t ending;
      /** The total duration of a commit. */
      uint32_t whole;
    };
    """

    _fields_ = [
        ("preparation", ctypes.c_uint32),
        ("gc", ctypes.c_uint32),
        ("audit", ctypes.c_uint32),
        ("write", ctypes.c_uint32),
        ("sync", ctypes.c_uint32),
        ("ending", ctypes.c_uint32),
        ("whole", ctypes.c_uint32),
    ]

    def __repr__(self) -> str:
        return str(
            {
                "preparation": self.preparation,
                "gc": self.gc,
                "audit": self.audit,
                "write": self.write,
                "sync": self.sync,
                "ending": self.ending,
                "whole": self.whole,
            }
        )


class MDBXCanary(ctypes.Structure):
    """
    The fours integers markers (aka "canary") associated with the
    environment.

    The `x`, `y` and `z` values could be set by mdbx_canary_put(), while the
    'v' will be always set to the transaction number. Updated values becomes
    visible outside the current transaction only after it was committed. Current
    values could be retrieved by mdbx_canary_get(). */
    """

    _fields_ = [
        ("x", ctypes.c_uint64),
        ("y", ctypes.c_uint64),
        ("z", ctypes.c_uint64),
        ("v", ctypes.c_uint64),
    ]

    def __repr__(self) -> str:
        return str({"x": self.x, "y": self.y, "z": self.z, "v": self.v})


class MDBXTXNInfo(ctypes.Structure):
    _fields_ = [
        ("txn_id", ctypes.c_uint64),
        ("txn_reader_lag", ctypes.c_uint64),
        ("txn_space_used", ctypes.c_uint64),
        ("txn_space_limit_soft", ctypes.c_uint64),
        ("txn_space_limit_hard", ctypes.c_uint64),
        ("txn_space_retired", ctypes.c_uint64),
        ("txn_space_leftover", ctypes.c_uint64),
        ("txn_space_dirty", ctypes.c_uint64),
    ]


class Iovec(ctypes.Structure):
    """
    Abstraction of the Iovec struct
    It holds references to byte vectors in the database

    The abstract bindings do not return this type, instead this is used internally to
    communicate with the C API./
    """

    _fields_ = [("iov_base", ctypes.c_void_p), ("iov_len", ctypes.c_size_t)]

    def __init__(self, base: Optional[bytes] = None, length: int = 0):
        if length < 0:
            raise ValueError("length must be 0 or positive")
        if length == 0 and base:
            length = len(base)
        self.iov_base = ctypes.cast(ctypes.c_char_p(base), ctypes.c_void_p)
        self.iov_len = length

    def to_bytes(self) -> Optional[bytes]:
        length = self.iov_len
        if length == 0:
            return None
        else:
            return bytes(
                ctypes.cast(self.iov_base, ctypes.POINTER(ctypes.c_ubyte))[:length]
            )

    def __repr__(self) -> str:
        return "iovec{.iov_base=%s, iov.len=%s}" % (self.iov_base, self.iov_len)


class MDBXEnv(ctypes.Structure):
    """
    Opaque struct used for declaration of Pointer to it
    """

    pass


class MDBXTXN(ctypes.Structure):
    """
    Opaque struct used for declaration of Pointer to it
    """

    pass


class MDBXCursor(ctypes.Structure):
    """
    Opaque struct used for declaration of Pointer to it
    """

    pass


class MDBXDBI(ctypes.Structure):
    """
    Struct in place of a #define, so type requirements can be declared
    """

    _fields_ = [("dbi", ctypes.c_uint32)]

    def __repr__(self) -> str:
        return str({"dbi": self.dbi})


class MDBXAttr(ctypes.Structure):
    """
    Struct in place of a #define, so type requirements can be declared
    """

    _fields_ = [("attr", ctypes.c_uint64)]

    def __repr__(self) -> str:
        return str({"attr": self.attr})


class MDBXErrorExc(BaseException):
    """
    Exception for MDBX errors.
    Its message parameter is set to the OS or MDBX error text.
    """

    def __init__(self, errno: int, errmsg: str):
        """
        :param errnum: MDBX error number
        :type errnum: int
        :param errmsg: text error message message from mdbx_liberr2str
        :type errmsg: str
        """
        self.errno = errno
        self.message = errmsg
        super().__init__(self.message)


class TXN:
    """
    An abstraction of the MdbxTxn struct and related functions
    """

    def __init__(
        self,
        env: Env,
        parent: Optional[TXN] = None,
        flags: MDBXTXNFlags = MDBXTXNFlags.MDBX_TXN_READWRITE,
        ctx: Optional[Any] = None,
    ):
        """

        Raises MDBXErrorExc or OSError
        :param env: Environment for which this Transaction is valid for
        :type env: Env
        :param parent: Parent exception
        :type parent: TXN
        :param flags: ORed combination of MDBXTXNFlags
        :type flags: MDBXTXNFlags
        :param context: User defined context object, can be anything.
        :type context: Object
        """
        self._txn: _Pointer[MDBXTXN] | None = ctypes.POINTER(MDBXTXN)()
        self._env: Env | None = env
        self._ctx: Optional[Any] = ctx
        self._flags = flags
        self._dependents: list[ReferenceType[Cursor]] = []
        env._dependents.append(weakref.ref(self))
        ret = _lib.mdbx_txn_begin_ex(
            env._env,
            parent._txn if parent else None,
            flags,
            ctypes.pointer(self._txn),
            self._ctx,
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

    def __del__(self) -> None:
        logging.getLogger(__name__).debug(
            f"Transaction {self._txn} being deleted, dependents: {self._dependents}"
        )
        self.close()

    def __enter__(self) -> TXN:
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> Literal[False]:
        logging.getLogger(__name__).debug(
            f"Transaction {self._txn} exits, dependents: {self._dependents}"
        )
        self.close()
        return False

    def break_txn(self) -> bool:
        """
        Thin wrapper around mdbx_txn_break

        Raises MDBXErrorExc or OSError
        :returns: True
        :rtype: bool
        """
        ret = _lib.mdbx_txn_break(self._txn)
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        return True

    def commit(self) -> bool:
        """
        Thin wrapper around mdbx_txn_commit

        Raises MDBXErrorExc or OSError

        Also calls self._invalidate if self._txn was still valid
        :returns: True
        ;rtype bool
        """
        logging.getLogger(__name__).debug(
            f"Transaction {self._txn} being commit, dependents: {self._dependents}"
        )
        if self._txn:
            self.__inform_deps()
            ret = _lib.mdbx_txn_commit(self._txn)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            self._txn = None
            self._env = None
        return True

    def commit_ex(self) -> MDBXCommitLatency:
        """
        Thin wrapper around mdbx_txn_commit_ex

        Raises MDBXErrorExc or OSError
        :returns ctypes struct of MDBX_commit_latency
        :rtype MDBXCommitLatency
        """
        logging.getLogger(__name__).debug(
            f"Transaction {self._txn} being committed_ex, dependents: {self._dependents}"
        )
        if self._txn:
            self.__inform_deps()
            commit_latency = MDBXCommitLatency()
            ret = _lib.mdbx_txn_commit_ex(self._txn, ctypes.byref(commit_latency))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            self._txn = None
            self._env = None
            return commit_latency
        raise RuntimeError("TXN is not available")

    def id(self) -> int:
        """
        Thin wrapper around mdbx_txn_id

        :returns transaction id, or 0 in case of failure
        """
        return _lib.mdbx_txn_id(self._txn)

    def get_env(self) -> Env | None:
        """
        Returns a reference to the Env object for which this TXN is valid

        :returns: self._env
        :rtype Env
        """
        return self._env

    def set_user_ctx(self, ctx: Any) -> None:
        """
        Sets the user context of the TXN

        We can _not_ use mdbx_txn_set_userctx here because it is not valid to cast a Python object to a C pointer!

        :param ctx: Context reference
        :type ctx: Object
        """
        self._ctx = ctx

    def set_user_ctx_int(self, ctx: ctypes.c_void_p) -> bool:
        """
        Thin wrapper around mdbx_txn_set_userctx

        Sets the user context of the MDBXTXN

        Raises MDBXErrorExc with returned error in case of failure
        :param ctx: Context reference
        :type ctx: ctypes object
        :returns: boolean indicating success or failure (if TXN was invalidated)
        :rtype bool
        """
        if self._txn:
            ret = _lib.mdbx_txn_set_userctx(self._txn, ctx)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return True
        raise RuntimeError("TXN is not available")

    def get_user_ctx(self) -> Optional[Any]:
        """
        Returns the reference to the stored userctx

        We can _not_ use mdbx_txn_sgt_userctx here because it is not valid to cast a Python object to a C pointer!
        :returns: Reference to stored context
        :rtype Object
        """
        return self._ctx

    def get_user_ctx_int(self) -> ctypes.c_void_p:
        """
        Returns the reference to the stored userctx that is part of the MDBXTXN

        :returns: Reference to stored context, or False
        :rtype ctype.c_void_p
        """
        if self._txn:
            return _lib.mdbx_txn_get_userctx(self._txn)
        raise RuntimeError("TXN is not available")

    def renew(self) -> bool:
        """
        Thin wrapper around mdbx_txn_renew
        Renews the TXN

        Raises MDBXErrorExc or OSError
        :returns: boolean indicating success or failure (if TXN was invalidated)
        :rtype bool
        """
        if self._txn:
            ret = _lib.mdbx_txn_renew(self._txn)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return True
        raise RuntimeError("TXN is not available")

    def reset(self) -> bool:
        """
        Thin wrapper around mdbx_txn_reset
        Resets the TXN

        Raises MDBXErrorExc or OSError
        :returns: boolean indicating success or failure (if TXN was invalidated)
        :rtype bool
        """
        if self._txn:
            ret = _lib.mdbx_txn_reset(self._txn)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return True
        raise RuntimeError("TXN is not available")

    def __inform_deps(self) -> None:
        for cur_ref in self._dependents:
            cur = cur_ref()
            if cur is not None:
                cur.close()
        self._dependents = []

    def close(self) -> None:
        if self._txn:
            # The transaction is still alive, we must abort it
            self.abort()

    def abort(self) -> bool:
        """
        Thin wrapper around mdbx_txn_abort
        Aborts the TXN

        Invalidates the TXN
        Raises MDBXErrorExc or OSError
        :returns: boolean indicating success or failure (if TXN was invalid)
        :rtype bool
        """
        logging.getLogger(__name__).debug(
            f"Transaction {self._txn} being aborted, dependents: {self._dependents}"
        )
        if self._txn:
            self.__inform_deps()  # It's okay to double-close
            ret = _lib.mdbx_txn_abort(self._txn)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            self._txn = None
            self._env = None
            return True
        raise RuntimeError("TXN is not available")

    def create_map(
        self,
        name: Optional[str | bytes | None] = None,
        flags: int = MDBXDBFlags.MDBX_CREATE,
    ) -> DBI:
        """
        Wrapper around mdbx_dbi_open2, intended to create a database(map)

        Raises MDBXErrorExc or OSerror
        :param name: DBI name or None, if default DB is to be opened
        :type name: str or bytes
        :param flags: Combination of MDBXDBFlags, passed to mdbx_dbi_open2
        :type flags: Combination of MDBXDBFlags
        :returns: Reference to opened DBI DBI if success, or False in case TXN was invalid
        :rtype DBI in case of success, or bool in case of failure
        """
        return self.open_map(name, flags | MDBXDBFlags.MDBX_CREATE)

    def open_map(
        self,
        name: Optional[str | bytes | None] = None,
        flags: int = MDBXDBFlags.MDBX_DB_DEFAULTS,
    ) -> DBI:
        """
        Wrapper around mdbx_dbi_open2, intended to open an existing map

        Raises MDBXErrorExc or OSerror
        :param name: DBI name or None, if default DB is to be opened
        :type name: str or bytes
        :param flags: Combination of MDBXDBFlags, passed to mdbx_dbi_open2
        :type flags: Combination of MDBXDBFlags
        :returns: Reference to opened DBI DBI if success, or False in case TXN was invalid
        :rtype DBI in case of success, or bool in case of failure
        """
        if self._txn:
            cname: Optional[bytes]
            dbi = ctypes.c_uint32()
            dbi.value = 0
            if isinstance(name, str):
                cname = name.encode("utf-8")
            else:
                cname = name
            key_iovec = Iovec(cname)
            ret = _lib.mdbx_dbi_open2(
                self._txn, ctypes.byref(key_iovec), flags, ctypes.pointer(dbi)
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)

            # self._env should never be None, but like self._tnx will be None upon close
            assert self._env
            return DBI(self._env, MDBXDBI(dbi))
        raise RuntimeError("TXN is not available")

    def get_info(self, scan_rlt: bool = False) -> MDBXTXNInfo:
        """
        Thin wrapper around mdbx_txn_info

        Raises MDBXErrorExc or OSerror
        :param scan_rlt: passed to scan_rlt
        :param scan_rlt: bool
        :returns MDBXTXNInfo containing all information
        :rtype MDBXTXNinfo or None
        """
        info = MDBXTXNInfo()
        if self._txn:
            ret = _lib.mdbx_txn_info(self._txn, ctypes.byref(info), scan_rlt)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return info
        raise RuntimeError("TXN is not available")

    def get_canary(self) -> MDBXCanary:
        """
        Thin wrapper around mdbx_canary_get

        Raises MDBXErrorExc or OSError
        :returns canary
        :rtype MDBXCanary
        """
        canary = MDBXCanary()
        ret = _lib.mdbx_canary_get(self._txn, ctypes.byref(canary))
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        return canary

    def put_canary(self, canary: MDBXCanary) -> None:
        """
        Thin wrapper around mdbx_canary_put

        Raises MDBXErrorExc or OSError
        :param canary: Canary to put
        :type MDBXCanary
        """
        ret = _lib.mdbx_canary_get(self._txn, ctypes.byref(canary))
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

    def cursor(self, db: DBI | str | bytes | None) -> Cursor:
        """
        Creata a cursor on a database. If the argument is str and current transaction is a read-write
        transaction, the database will be created.
        """
        dbi: DBI | None
        if isinstance(db, DBI):
            dbi = db
        elif isinstance(db, str) or isinstance(db, bytes):
            if self._flags.is_read_only():
                dbi = self.open_map(db)
            else:
                dbi = self.create_map(db)
        elif db is None:
            dbi = self.open_map(db)
        else:
            raise RuntimeError("db is not a DBI, str or bytes")

        return Cursor(dbi, self, self._ctx)


@dataclasses.dataclass
class Geometry:
    """
    Storage object for set_geometry and instanciation of Env with passed Env
    """

    size_lower: int = -1
    size_now: int = -1
    size_upper: int = -1
    growth_step: int = -1
    shrink_threshold: int = -1
    pagesize: int = -1


class Env(object):
    """
    Thin wrapper around mdbx_env

    Raises MDBXErrorExc or OSError
    :param path: default environment name, defaults to "default_db"
    :type path: str
    :param flags: Combination of MDBXEnvFlags
    :type flags: MDBXEnvFlags
    :param mode: Access mode for the environment directory
    :type mode: int
    :param geometry: Geometry of the database, entirely optional
    :type geometry: Geometry
    :param maxreaders: Maxreaders to be set, defaults to 1
    :type maxreaders: int
    :param, maxdbs: Maxdbs to be set, defaults to 1
    :type maxdbs: int

    """

    def __init__(
        self,
        path: str,
        flags: int = MDBXEnvFlags.MDBX_ENV_DEFAULTS,
        mode: int = 0o755,
        geometry: Optional[Geometry] = None,
        maxreaders: int = 1,
        maxdbs: int = 1,
        sync_bytes: Optional[int] = None,
        sync_period: Optional[int] = None,
    ):
        self._env: _Pointer[MDBXEnv] | None = ctypes.pointer(MDBXEnv())
        ret = _lib.mdbx_env_create(ctypes.byref(self._env))
        self._default_db: str | bytes | None = None
        self._current_txn = None
        self._dependents: list[ReferenceType[TXN] | ReferenceType[DBI]] = []
        self._ctx: Optional[Any] = None
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        if geometry:
            ret = _lib.mdbx_env_set_geometry(
                self._env,
                geometry.size_lower,
                geometry.size_now,
                geometry.size_upper,
                geometry.growth_step,
                geometry.shrink_threshold,
                geometry.pagesize,
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        if maxreaders > 0:
            ret = _lib.mdbx_env_set_maxreaders(self._env, maxreaders)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        if maxdbs > 0:
            ret = _lib.mdbx_env_set_maxdbs(self._env, maxdbs)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        ret = _lib.mdbx_env_open(
            self._env, ctypes.c_char_p(bytes(str(path), "utf-8")), flags, mode
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

        if sync_bytes is not None:
            self.set_option(MDBXOption.MDBX_opt_sync_bytes, sync_bytes)

        if sync_period is not None:
            self.set_option(MDBXOption.MDBX_opt_sync_period, sync_period)

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> Env:
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> Literal[False]:
        self.close()
        return False

    def __repr__(self) -> str:
        return f'Env {{ "path" : "{self.get_path()}" }}'

    def __getitem__(self, key: str | bytes) -> bytes | None:
        """
        Gets item from currently set default database
        Opens a read only transaction, gets the object, aborts the transaction

        Raises MDBXErrorExc, OSError, or KeyError
        :param key: Key
        :type key: str or bytes
        :returns: bytes in case object is found, or None if no object is found, or Null is stored for it
        :rtype bytes or None
        """
        if not isinstance(key, (str, bytes)):
            raise KeyError("Key can only be string or bytes")
        try:
            txn = self.ro_transaction()
            db = txn.open_map(self._default_db)
            if isinstance(key, str):
                key = key.encode("utf-8")
            val = db.get(txn, key)
            txn.abort()
            return val
        except Exception as _e:
            return None

    def __setitem__(self, key: str | bytes, val: str | bytes) -> bytes | None:
        """
        Sets the given key and val in the current default database
        if key or val are strings, they are converted into bytes using utf-8 encoding

        Raises MDBXErrorExc, OSError, or KeyError
        :param key: Key to be used
        :type key: str or bytes
        :param val: Value to store
        :type val: str or bytes
        :returns: val
        :rtype: bytes
        """
        if not isinstance(key, (str, bytes)):
            raise KeyError("Key can only be string or bytes")
        if not isinstance(val, (str, bytes)):
            raise KeyError("Value can only be string or bytes")
        txn = self.start_transaction()
        dbi = txn.open_map(self._default_db)
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        val_bytes: bytes = val.encode("utf-8") if isinstance(val, str) else val
        result = dbi.put(txn, key_bytes, val_bytes)
        txn.commit()

        return result

    def __iter__(self) -> Iterator[tuple[bytes | None, bytes | None]]:
        """
        Create iterator over this Env's currently set default_db

        :returns iterator over default_db
        :rtype: EnvIterator
        """
        txn = self.ro_transaction()
        dbi = txn.open_map(self._default_db)
        cur = Cursor(dbi, txn, self._ctx)
        return cur.iter()

    def close(self) -> None:
        """
        Closes this Env. _In most cases, you don't need to call this._ mdbx-py has
        internal reference counting to _safely_ garbage collect envs, txs and cursors.

        Raises MDBXErrorExc or OSError
        """
        logging.getLogger(__name__).debug(
            f"env {self._env} being closed, dependents: {self._dependents}"
        )
        if self._env:
            for tx_ref in self._dependents:
                tx = tx_ref()
                if tx is not None:
                    tx.close()
            self._dependents = []
            ret = _lib.mdbx_env_close(self._env)
            if ret != MDBXError.MDBX_BUSY.value:
                self._env = None
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)

    def items(self) -> Iterator[tuple[bytes | None, bytes | None]]:
        """
        bsddb compatibility function. Returns an iterator over contents of default db (self._default_db)
        :returns: iterator over self
        :rtype: EnvIterator
        """
        return self.__iter__()

    def get(self, key: bytes) -> bytes | None:
        """
        Returns the value stored under this key, uses self.__getitem__
        See self.__getitem__ for behaviour

        """
        return self.__getitem__(key)

    def set_default_db(self, name: str | bytes | None) -> None:
        """
        Sets the default DB to be used for __setitem__ and __getitem__
        :param name: name of the DBI
        :type name: str or bytes
        """
        self._default_db = name

    def ro_transaction(self) -> TXN:
        return self.start_transaction(MDBXTXNFlags.MDBX_TXN_RDONLY, None)

    def rw_transaction(self, parent_txn: Optional[TXN] = None) -> TXN:
        return self.start_transaction(MDBXTXNFlags.MDBX_TXN_READWRITE, parent_txn)

    def start_transaction(
        self,
        flags: MDBXTXNFlags = MDBXTXNFlags.MDBX_TXN_READWRITE,
        parent_txn: Optional[TXN] = None,
    ) -> TXN:
        """
        Starts a transaction on the given Env

        Raises MDBXErrorExc or OSError
        :param flags: Combination of MDBXTXNFlags
        :type flags: MDBXTXNFlags
        :param parent_txn: Parent transaction, defaults to None
        :type parent_txn: TXN
        :returns: Transaction
        :rtype TXN
        """
        # start transaction and return new object
        if self._env:
            txn = TXN(self, parent_txn, flags)
            logging.getLogger(__name__).debug(f"Starting transaction {txn._txn}")
            return txn
        raise RuntimeError("Env is not available")

    def get_path(self) -> str:
        """
        Thin wrapper around mdbx_env_get_path

        Raises MDBXErrorExc or OSErro
        :returns: path to the directory of the Env
        :rtype: str
        """
        if self._env:
            ptr = ctypes.c_char_p()
            ret = _lib.mdbx_env_get_path(self._env, ctypes.byref(ptr))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            assert ptr.value
            return ptr.value.decode("utf-8")
        raise RuntimeError("Env is not available")

    def set_user_ctx(self, val: Any) -> None:
        """
        Store val in self._ctx

        We can _not_ use mdbx_env_set_userctx here because it is not valid to cast a Python object to a C pointer!

        :param val: Context to set
        :type val: Object
        """
        self._ctx = val

    def get_user_ctx(self) -> Optional[Any]:
        """
        Retrieve self._ctx

        We can _not_ use mdbx_env_get_userctx here because it is not valid to cast a Python object to a C pointer!
        :returns: stored userctx
        :rtype Object
        """
        return self._ctx

    def set_user_ctx_int(self, val: ctypes.c_void_p) -> None:
        """
        Thin wrapper around mdbx_env_set_userctx
        Store val in self._ctx

        Raises MDBXErrorExc or OSError
        :param val: Context to set
        :type val: ctypes.c_void_p
        """
        if self._env:
            ret = _lib.mdbx_env_set_userctx(self._env, val)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def get_user_ctx_int(self) -> ctypes.c_void_p:
        """
        Thin wrapper around mdbx_env_get_userctx
        Retrieve self._ctx

        :returns: stored userctx
        :rtype ctypes.c_void_p
        """
        if self._env:
            return _lib.mdbx_env_get_userctx(self._env)
        raise RuntimeError("Env is not available")

    def get_info(self, txn: TXN) -> MDBXEnvinfo:
        """
        Thin wrapper around mdbx_env_info_ex

        Raises MDBXErrorExc or OSError
        :param txn: transaction to use while getting info
        :type txn: TXN
        :returns information about environment
        :rtype MDBXEnvinfo
        """
        if self._env:
            info = MDBXEnvinfo()
            ret = _lib.mdbx_env_info_ex(
                self._env, txn._txn, ctypes.byref(info), ctypes.sizeof(info)
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return info
        raise RuntimeError("Env is not available")

    def get_stat(self, txn: TXN) -> MDBXStat:
        """
        Thin wrapper around mdbx_env_stat_ex

        Raises MDBXErrorExc or OSError
        :returns stats
        :rtype MDBXStat
        """
        if self._env:
            stats = MDBXStat()
            ret = _lib.mdbx_env_stat_ex(
                self._env, txn._txn, ctypes.byref(stats), ctypes.sizeof(stats)
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return stats
        raise RuntimeError("Env is not available")

    def copy(
        self, destination: str, flags: int = MDBXCopyMode.MDBX_CP_DEFAULTS
    ) -> None:
        """
        Thin wrapper around mdbx_env_copy

        Raises MDBXErrorExc or OSError
        :param destination: Path to the new Env
        :type destination: str
        """
        if self._env:
            ret = _lib.mdbx_env_copy(self._env, destination, flags)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def copy2fd(self, fd: int, flags: int = MDBXCopyMode.MDBX_CP_DEFAULTS) -> None:
        """
        Thin wrapper around mdbx_env_copy2fd

        Raises MDBXErrorExc or OSError
        :param fd: File descriptor to the parent directory for the new Env
        :type fd: int
        :param flag: Combination of MDBXCopyMode flags
        :type flag: int
        """
        if self._env:
            if hasattr(fd, "fileno"):
                fd = fd.fileno()

            ret = _lib.mdbx_env_copy2fd(
                self._env, ctypes.c_int(fd), ctypes.c_int(flags)
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def register_thread(self) -> None:
        """
        Thin wrapper around mdbx_thread_register

        Raises MDBXErrorExc or OSerror
        """
        if self._env:
            ret = _lib.mdbx_thread_register(self._env)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def unregister_thread(self) -> None:
        """
        Thin wrapper around mdbx_unregister_thread

        Raises MDBXErrorExc or OSError
        """
        if self._env:
            ret = _lib.mdbx_thread_unregister(self._env)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def set_geometry(self, geometry: Geometry) -> None:
        """
        Thin wrapper around mdbx_env_set_geometry

        Raises MDBXErrorExc or OSError
        :param geometry: Geometry type object holding all parameters for the geometry
        :type geometry: Geometry
        """
        if self._env:
            ret = _lib.mdbx_env_set_geometry(
                self._env,
                geometry.size_lower,
                geometry.size_now,
                geometry.size_upper,
                geometry.growth_step,
                geometry.shrink_threshold,
                geometry.pagesize,
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def set_option(self, option: int, value: int) -> None:
        """
        Thin wrapper around mdbx_env_set_option

        Raises MDBXErrorExc or OSError
        :param option: ORed combination of mdbx environment options
        :type option: int
        :param value: Value to set
        :type value: int
        """
        if self._env:
            val = ctypes.c_uint64(value)
            ret = _lib.mdbx_env_set_option(self._env, option, val)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def get_option(self, option: int) -> int:
        """
        Thin wrapper around mdbx_env_get_option

        Raises MDBXErrorExc or OSError
        :param option: Option to get
        :type option: int
        :returns value of the option
        :rtype int
        """
        if self._env:
            val = ctypes.c_uint64()
            ret = _lib.mdbx_env_get_option(self._env, option, ctypes.byref(val))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return val.value
        raise RuntimeError("Env is not available")

    def get_fd(self) -> int:
        """
        Thin wrapper around mdbx_env_get_fd

        Raises MDBXErrorExc or OSError
        :returns fd for the Env
        :rtype int
        """
        if self._env:
            fd = ctypes.c_uint()
            ret = _lib.mdbx_env_get_fd(self._env, ctypes.byref(fd))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return fd.value
        raise RuntimeError("Env is not available")

    def get_maxdbs(self) -> int:
        """
        Thin wrapper around mdbx_env_get_maxdbs

        Raises MDBXErrorExc or OSError
        :returns maxdbs value
        :rtype int
        """
        if self._env:
            val = ctypes.c_uint64()
            ret = _lib.mdbx_env_get_maxdbs(self._env, ctypes.byref(val))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return val.value
        raise RuntimeError("Env is not available")

    def get_maxkeysize(
        self, flags: int = MDBXDBFlags.MDBX_DB_DEFAULTS
    ) -> Optional[int]:
        """
        Thin wrapper around mdbx_env_get_maxkeysize_ex

        :returns int or None if function returns -1
        :rtype int or None
        """
        if self._env:
            val = _lib.mdbx_env_get_maxkeysize_ex(self._env, flags)
            return None if val == -1 else val
        raise RuntimeError("Env is not available")

    def get_maxvalsize(
        self, flags: int = MDBXDBFlags.MDBX_DB_DEFAULTS
    ) -> Optional[int]:
        """
        Thin wrapper around mdbx_env_get_maxvalsize_ex

        :returns int or None if function returns -1
        :rtype int or None
        """
        if self._env:
            val = _lib.mdbx_env_get_maxvalsize_ex(self._env, flags)
            return None if val == -1 else val
        raise RuntimeError("Env is not available")

    def sync(self, force: bool = False, nonblock: bool = False) -> None:
        """
        Thin wrapper around mdbx_env_sync_ex

        Raises MDBXErrorExc or OSError
        :param force: Force flag
        :type force: bool
        :param nonblock: nonblock flag
        :type nonblock: bool
        """
        if self._env:
            ret = _lib.mdbx_env_sync_ex(
                self._env, ctypes.c_bool(force), ctypes.c_bool(nonblock)
            )
            if ret != MDBXError.MDBX_RESULT_TRUE.value and ret != 0:
                raise make_exception(ret)
            return
        raise RuntimeError("Env is not available")

    def get_db_names(self) -> list[str]:
        """
        Returns a list of all databases in the Env

        Internally uses a read only TXN and iterates over all keys and values in database NULL

        Raises MDBXErrorExc or OSError
        :returns list of all databases
        :rtype list
        """
        if self._env:
            if not self.get_maxdbs():
                return []
            txn = TXN(self, flags=MDBXTXNFlags.MDBX_TXN_RDONLY)
            dbi = txn.open_map(flags=MDBXDBFlags.MDBX_DB_DEFAULTS)
            names: list[str] = []
            cursor = Cursor(dbi, txn)
            for key, val in cursor:
                assert key
                names.append(key.decode("utf-8"))
            return names
        raise RuntimeError("Env is not available")

    @classmethod
    def delete(
        cls, path: str, mode: MDBXEnvDeleteMode = MDBXEnvDeleteMode.MDBX_ENV_JUST_DELETE
    ) -> bool:
        """
        Thin wrapper around mdbx_env_delete

        Deletes the environment under the given path

        Raises MDBXErrorExc or OSError
        :param path: Path to the Environment
        :type path: str
        :param mode: Mode for the environment
        :type mode: int
        :returns True
        :rtype bool
        """
        arr = path.encode("utf-8")
        ret = _lib.mdbx_env_delete(ctypes.string_at(arr, len(arr)), mode)
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        return True

    def set_hsr(self, hsr: MDBXHSRFunc) -> None:
        """
        Thin wrapper around mdbx_env_set_hsr

        Raises MDBXErrorExc or OSError
        :param hsr: HSR type function
        :type hsr: _lib.HDBX_hsr_func
        """
        if self._env:
            cb = MDBX_hsr_func(hsr)

            ret = _lib.mdbx_env_set_hsr(self._env, cb)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)

            self._hsr_callback = cb
        raise RuntimeError("Env is not available")

    def get_hsr(self) -> MDBXHSRFunc:
        """
        Thin wrapper around mdbx_env_get_hsr

        Raises MDBXErrorExc with returned error in case of failure
        """
        if self._env:
            raw_ptr = _lib.mdbx_env_get_hsr(self._env)
            return ctypes.cast(raw_ptr, MDBX_hsr_func)
        raise RuntimeError("Env is not available")


class DBI:
    """
    Abstraction of a database inside an environment
    """

    def __init__(self, env: Env, dbi: MDBXDBI):
        """
        :param env: Environment this DBI belongs to
        :type env: Env
        :param dbi: integer identifying the DBI
        :type dbi: MDBXDBI
        """
        self._dbi = dbi
        self._env = env

    def __del__(self) -> None:
        pass

    def __enter__(self) -> DBI:
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return str("%s: %s" % (self._env, self._dbi))

    def close(self) -> None:
        """
        Do nothing and delegate mdbx_env_close to close all handles.

        MDBX will reuse handles (closing one will invalidate other aliased handles) and it is
        tedious to track the duplicate handle aliases by our side.
        """
        pass

    def get(self, txn: TXN, key: bytes) -> Optional[bytes]:
        """
        Wrapper around mdbx_get.

        Uses the TXN to get the value stored under the key

        Raises MDBXErrorExc or OSError
        :param txn: Transaction to use
        :type txn: TXN
        :param key: Key to lookup
        :type key: bytes
        """
        key_iovec = Iovec(key)
        data_iovec = Iovec(None, 1)
        ret = _lib.mdbx_get(
            txn._txn, self._dbi, ctypes.byref(key_iovec), ctypes.byref(data_iovec)
        )
        if ret == MDBXError.MDBX_NOTFOUND:
            return None
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

        return data_iovec.to_bytes()

    def get_stat(self, txn: TXN) -> MDBXStat:
        """
        Thin wrapper around mdbx_dbi_stat

        Raises MDBXErrorExc or OSError
        :returns stats
        :rtype MDBXStat
        """
        stats = MDBXStat()
        ret = _lib.mdbx_dbi_stat(
            txn._txn, self._dbi, ctypes.byref(stats), ctypes.sizeof(stats)
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        return stats

    def put(
        self, txn: TXN, key: bytes, value: bytes, flags: int = MDBXPutFlags.MDBX_UPSERT
    ) -> bytes | None:
        """
        Thin wrapper around mdbx_put

        Raises MDBXErrorExc or OSError
        :param txn: Transaction to use
        :type txn: TXN
        :param key: key to store value under
        :type key: bytes
        :param value: Value to store
        :type value: bytes
        :param flags: Combination of MDBXPutFlags, defaults to 0
        :type flags: MDBXPutFlags
        """

        key_iov = Iovec(key, len(key))
        value_iov = Iovec(value, len(value))
        ret = _lib.mdbx_put(
            txn._txn,
            self._dbi,
            ctypes.c_void_p(ctypes.addressof(key_iov)),
            ctypes.c_void_p(ctypes.addressof(value_iov)),
            flags,
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        assert value_iov
        return value_iov.to_bytes()

    def drop(self, txn: TXN, delete: bool = False) -> None:
        """
        Thin wrapper around mdbx_drop

        Raises MDBXErrorExc or OSError
        :param txn: Transaction to use
        :type txn: TXN
        :param delete: delete flag to mdbx_drop, defaults to False
        :type delete: bool
        """
        ret = _lib.mdbx_drop(txn._txn, self._dbi, delete)
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

    def replace(
        self,
        txn: TXN,
        key: bytes,
        new_data: bytes,
        flags: int = MDBXPutFlags.MDBX_UPSERT,
    ) -> bytes:
        """
        Thin wrapper around mdbx_replace

        Raises MDBXErrorExc or OSError
        :param txn: Transaction to use
        :type txn: TXN
        :param key: Key whose value is to be replaced
        :type key: bytes
        :param new_data: new data to store
        :type new_data: bytes
        :param flags: Combination of MDBXPutFlags, defaults to 0
        :type flags: MDBXPUtFlags
        :returns old data of the key
        :rtype bytes
        """
        old_data = Iovec()
        key_iovec = Iovec(key)
        new_iovec = Iovec(new_data)
        ret = _lib.mdbx_replace(
            txn._txn,
            self._dbi,
            ctypes.byref(key_iovec),
            ctypes.byref(new_iovec),
            ctypes.byref(old_data),
            flags,
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)
        return bytes(
            ctypes.cast(old_data.iov_base, ctypes.POINTER(ctypes.c_ubyte))[
                : old_data.iov_len
            ]
        )

    def delete(self, txn: TXN, key: bytes, value: Optional[bytes] = None) -> None:
        """
        Thin wrapper around mdbx_del

        Raises MDBXErrorExc or OSError
        :param txn: Transaction to use
        :type txn: TXN
        :param key: Key whose value is to be deleted
        :type key: bytes
        :param value: The value to delete
        :type value: bytes
        """
        key_iovec = Iovec(key)
        ret = _lib.mdbx_del(
            txn._txn,
            self._dbi,
            ctypes.byref(key_iovec),
            ctypes.byref(Iovec(value)) if value else None,
        )
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

    def get_sequence(self, txn: TXN, increment: int = 0) -> int:
        """
        Wrapper around mdbx_dbi_sequence.

        :param txn: Transaction handle
        :param dbi: Database handle
        :param increment: Value to increase the sequence by (0 for read-only transactions)
        :return: Previous sequence value
        :raises MDBXErrorExc: on failure
        """
        result = ctypes.c_uint64(0)
        ret = _lib.mdbx_dbi_sequence(
            txn._txn, self._dbi, ctypes.byref(result), ctypes.c_uint64(increment)
        )
        if ret == MDBXError.MDBX_SUCCESS.value:
            return result.value
        elif ret == MDBXError.MDBX_RESULT_TRUE.value:
            raise OverflowError("Sequence increment resulted in overflow")
        else:
            raise make_exception(ret)


class Cursor:
    """
    Abstraction of an MDBX cursor

    Used for iterating over values within a key
    """

    def __init__(
        self,
        db: Optional[DBI] = None,
        txn: Optional[TXN] = None,
        ctx: Optional[Any] = None,
    ):
        """
        Thin wrapper around either mdbx_cursor_open or mdbx_cursor_create

        Raises MDBXErrorExc, OSError, ValueError, or MemoryError
        :param db: Database this cursor is bound to
        :type db: DBI
        :param txn: Transaction in which this cursor is valid
        :type txn: TXN
        :param ctx: User provided context
        :type ctx: Object
        """
        self._db = db
        self._txn = txn
        self._ctx: Optional[Any] = ctx
        self._started = False
        self._cursor: Optional[_Pointer[MDBXCursor]] = None
        ret = None
        if db and txn:
            cursor_ptr = ctypes.POINTER(MDBXCursor)()
            ret = _lib.mdbx_cursor_open(txn._txn, db._dbi, ctypes.byref(cursor_ptr))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            self._cursor = cursor_ptr

        else:
            self._cursor = _lib.mdbx_cursor_create(ctx)
            if not self._cursor:
                raise MemoryError("mdbx_cursor_create failed")

        if txn:
            txn._dependents.append(weakref.ref(self))

    def bind(self, txn: TXN, db: Optional[DBI] = None) -> None:
        """
        Thin wrapper around mdbx_cursor_bind

        Raises MDBXErrorExc or OSError
        :param txn: transaction to bind to
        :type txn: TXN
        :param db: database to bind to
        :type db: DBI
        """
        ret = _lib.mdbx_cursor_bind(txn._txn, self._cursor, db._dbi if db else self._db)
        if ret != MDBXError.MDBX_SUCCESS.value:
            raise make_exception(ret)

    def __enter__(self) -> Cursor:
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> Literal[False]:
        logging.getLogger(__name__).debug(f"Cursor {self._cursor} exits")
        self.__del__()
        return False

    def __del__(self) -> None:
        logging.getLogger(__name__).debug(f"Cursor {self._cursor} being deleted")
        self.close()

    def __iter__(self) -> Cursor:
        return self

    def __next__(self) -> tuple[bytes | None, bytes | None]:
        """
        Wrapper around mdbx_cursor_get and mdbx_Cursor_eof

        Raises MDBXErrorExc or OSError
        Raises StopIteration if the cursor can not be moved further (last item returned was the last item stored under this key)
        """
        if self._cursor:
            val_iov = Iovec(bytes())
            key_iov = Iovec(bytes())
            if not self._started:
                self._started = True
                ret = _lib.mdbx_cursor_get(
                    self._cursor,
                    ctypes.pointer(key_iov),
                    ctypes.pointer(val_iov),
                    MDBXCursorOp.MDBX_FIRST,
                )
            else:
                ret = _lib.mdbx_cursor_get(
                    self._cursor,
                    ctypes.pointer(key_iov),
                    ctypes.pointer(val_iov),
                    MDBXCursorOp.MDBX_NEXT,
                )

            if ret != MDBXError.MDBX_SUCCESS.value:
                if _lib.mdbx_cursor_eof(self._cursor) or ret == MDBXError.MDBX_NOTFOUND:
                    raise StopIteration
                raise make_exception(ret)
            val = bytes(
                ctypes.cast(val_iov.iov_base, ctypes.POINTER(ctypes.c_ubyte))[
                    : val_iov.iov_len
                ]
            )
            key = bytes(
                ctypes.cast(key_iov.iov_base, ctypes.POINTER(ctypes.c_ubyte))[
                    : key_iov.iov_len
                ]
            )
            return key, val
        return None, None

    def close(self) -> None:
        """
        Thin wrapper around mdbx_cursor_close

        Sets self._cursor to None, invalidating the reference to it
        """
        logging.getLogger(__name__).debug(f"Cursor {self._cursor} being closed")
        if self._cursor:
            _lib.mdbx_cursor_close(self._cursor)
            # This is important to release the strong references
            self._cursor = None
            self._txn = None
            self._db = None

    def set_user_ctx(self, val: Any) -> None:
        """
        Sets self._ctx to val
        """
        self._ctx = val

    def get_user_ctx(self) -> Optional[Any]:
        """
        Returns self._ctx
        :returns self._ctx
        """
        return self._ctx

    def set_user_ctx_int(self, ptr: ctypes.c_void_p) -> None:
        """
        Thin wrapper around mdbx_cursor_set_userctx

        Raises MDBXErrorExc or OSError
        :param ptr: pointer to object
        :type ptr: ctypes.c_void_p
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_set_userctx(self._cursor, ptr)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        raise RuntimeError("Cursor is not available")

    def get_user_ctx_int(self) -> ctypes.c_void_p:
        """
        Thin wrapper around mdbx_cursor_get_userctx
        :rtype ctypes.c_void_p
        """
        if self._cursor:
            return _lib.mdbx_cursor_get_userctx(self._cursor)
        raise RuntimeError("Cursor is not available")

    def txn(self) -> MDBXTXN:
        """
        Thin wrapper around mdbx_cursor_txn
        :returns Transaction for which this Cursor is valid
        :rtype MDBXTXN
        """
        if self._cursor:
            return _lib.mdbx_cursor_txn(self._cursor)
        raise RuntimeError("Cursor is not available")

    def dbi(self) -> MDBXDBI:
        """
        Thin wrapper around mdbx_cursor_dbi
        :returns Database to which this Cursor is bound
        :rtype MDBXDBI
        """
        if self._cursor:
            return _lib.mdbx_cursor_dbi(self._cursor)
        raise RuntimeError("Cursor is not available")

    def copy(self, dest: Cursor) -> Cursor:
        """
        Thin wrapper around mdbx_cursor_copy
        Copies this cursor's state to the given Cursor

        Raises MDBXErrorExc or OSError
        :param dest: Cursor to which this cursor's state is copied to
        :type dest: Cursor
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_copy(self._cursor, dest._cursor)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return dest
        raise RuntimeError("Cursor is not available")

    def dup(self) -> Cursor:
        cursor = Cursor(self._db, self._txn, self._ctx)
        self.copy(cursor)
        return cursor

    def first(self) -> tuple[Optional[bytes], Optional[bytes]]:
        return self.get_full(None, MDBXCursorOp.MDBX_FIRST)

    def first_dup(self) -> Optional[bytes]:
        _, v = self.get_full(None, MDBXCursorOp.MDBX_FIRST_DUP)
        return v

    def last(self) -> tuple[Optional[bytes], Optional[bytes]]:
        return self.get_full(None, MDBXCursorOp.MDBX_LAST)

    def last_dup(self) -> Optional[bytes]:
        _, v = self.get_full(None, MDBXCursorOp.MDBX_LAST_DUP)
        return v

    def get_full(
        self, key: Optional[bytes], cursor_op: MDBXCursorOp
    ) -> tuple[Optional[bytes], Optional[bytes]]:
        if self._cursor:
            io_key = Iovec(key)
            io_data = Iovec(None, 1)

            ret = _lib.mdbx_cursor_get(
                self._cursor, ctypes.byref(io_key), ctypes.byref(io_data), cursor_op
            )
            if ret == MDBXError.MDBX_NOTFOUND or ret == MDBXError.MDBX_ENODATA:
                return (None, None)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            out_key = io_key.to_bytes()
            out_value = io_data.to_bytes()
            return (out_key, out_value)
        raise RuntimeError("Cursor is not available")

    def get(
        self, key: Optional[bytes], cursor_op: MDBXCursorOp = MDBXCursorOp.MDBX_FIRST
    ) -> Optional[bytes]:
        """
        Wrapper around mdbx_cursor_get

        Raises MDBXErrorExc or OSError
        :param key: Key to retrieve data from
        :type key: bytes
        :param cursor_op: Operation parameter for mdbx_cursor_get
        :type cursor_op: MDBXCursorOp
        :returns value of the key
        :rtype bytes
        """
        _, v = self.get_full(key, cursor_op)
        return v

    def put(
        self, key: bytes, val: bytes, flags: int = MDBXPutFlags.MDBX_UPSERT
    ) -> None:
        """
        Thin wrapper around mdbx_cursor_put

        Raises MDBXErrorExc or OSError
        :param key: Key to store data at
        :type key: bytes
        :param val: value to store
        :type val: bytes
        :param cursor_op: op parameter for mdbx_cursor_get
        :type cursor_op: MDBXCursorOp
        """
        if self._cursor:
            key_iovec = Iovec(key, len(key))
            value_iovec = Iovec(val, len(val))

            ret = _lib.mdbx_cursor_put(
                self._cursor, ctypes.byref(key_iovec), ctypes.byref(value_iovec), flags
            )
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Cursor is not available")

    def delete(self, cursor_op: MDBXCursorOp = MDBXCursorOp.MDBX_FIRST) -> None:
        """
        Thin wrapper around mdbx_cursor_del

        Raises MDBXErrorExc or OSError
        :param cursor_op: op parameter to mdbx_cursor_delete
        :type cursor_op: MDBXCursorOP
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_del(self._cursor, cursor_op)
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return
        raise RuntimeError("Cursor is not available")

    def count(self) -> int:
        """
        Thin wrapper around mdbx_cursor_count

        Raises MDBXErrorExc or OSError
        :returns count of duplicates for current key
        :rtype int
        """
        if self._cursor:
            count = ctypes.c_size_t()
            ret = _lib.mdbx_cursor_count(self._cursor, ctypes.byref(count))
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
            return int(count)
        raise RuntimeError("Cursor is not available")

    def eof(self) -> bool:
        """
        Thin wrapper around mdbx_cursor_eof

        Raises MDBXErrorExc or OSError
        :returns whether cursor is at a key-value pair or not
        :rtype bool
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_eof(self._cursor)

            if ret == MDBXError.MDBX_RESULT_TRUE:
                return True
            if ret == MDBXError.MDBX_RESULT_FALSE:
                return False
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        raise RuntimeError("Cursor is not available")

    def on_first(self) -> bool:
        """
        Thin wrapper around mdbx_cursor_on_first

        Raises MDBXErrorExc or OSError
        :returns Whether cursor is on first key-value pair or not
        :rtype bool
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_on_first(self._cursor)
            if ret == MDBXError.MDBX_RESULT_TRUE:
                return True
            if ret == MDBXError.MDBX_RESULT_FALSE:
                return False
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        raise RuntimeError("Cursor is not available")

    def on_last(self) -> bool:
        """
        Thin wrapper around mdbx_cursor_on_last

        Raises MDBXErrorExc or OSError
        :returns whether cursor is on last key-value pair or not
        :rtype bool
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_on_last(self._cursor)
            if ret == MDBXError.MDBX_RESULT_TRUE:
                return True
            if ret == MDBXError.MDBX_RESULT_FALSE:
                return False
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        raise RuntimeError("Cursor is not available")

    def renew(self, txn: TXN) -> bool:
        """
        Thin wrapper around mdbx_cursor_renew

        Raises MDBXErrorExc or OSError
        :returns bool indicating success
        :rtype bool
        """
        if self._cursor:
            ret = _lib.mdbx_cursor_renew(txn._txn, self._cursor)
            if ret == MDBXError.MDBX_RESULT_TRUE:
                return True
            if ret != MDBXError.MDBX_SUCCESS.value:
                raise make_exception(ret)
        raise RuntimeError("Cursor is not available")

    def iter(
        self,
        start_key: Optional[bytes] = None,
        from_next: bool = False,
        copy_cursor: bool = False,
    ) -> Iterator[tuple[bytes | None, bytes | None]]:
        if start_key is not None and from_next:
            raise RuntimeError(
                "start_key and from_next can not be used at the same time"
            )
        if copy_cursor:
            cursor = self.dup()
        else:
            cursor = self
        if from_next:
            first_op = MDBXCursorOp.MDBX_NEXT
        else:
            first_op = MDBXCursorOp.MDBX_FIRST
        if start_key is None:
            return DBIter(cursor, first_op, MDBXCursorOp.MDBX_NEXT)
        else:
            self.get_full(start_key, MDBXCursorOp.MDBX_SET_RANGE)
            return DBIter(cursor, MDBXCursorOp.MDBX_GET_CURRENT, MDBXCursorOp.MDBX_NEXT)

    def iter_dupsort(
        self,
        start_key: Optional[bytes] = None,
        from_next: bool = False,
        copy_cursor: bool = False,
    ) -> Iterator[tuple[bytes | None, bytes | None]]:
        its = self.iter_dupsort_rows(start_key, from_next, copy_cursor)
        return itertools.chain.from_iterable(its)

    def iter_dupsort_rows(
        self,
        start_key: Optional[bytes] = None,
        from_next: bool = False,
        copy_cursor: bool = False,
    ) -> Iterator[Iterator[tuple[bytes | None, bytes | None]]]:
        if start_key is not None and from_next:
            raise RuntimeError(
                "start_key and from_next can not be used at the same time"
            )
        if copy_cursor:
            cursor = self.dup()
        else:
            cursor = self
        if from_next:
            first_op = MDBXCursorOp.MDBX_NEXT
        else:
            first_op = MDBXCursorOp.MDBX_FIRST
        if start_key is None:
            return DBDupIter(cursor, first_op)
        else:
            self.get_full(start_key, MDBXCursorOp.MDBX_SET_RANGE)
            return DBDupIter(cursor, MDBXCursorOp.MDBX_GET_CURRENT)


class DBIter(object):
    def __init__(
        self, cur: Cursor, first_op: MDBXCursorOp, second_op: Optional[MDBXCursorOp]
    ):
        self.cur = cur  # Strong reference!
        self.first_op = first_op
        self.second_op = second_op

        self.op = first_op

    def __iter__(self) -> DBIter:
        return self

    def __next__(self) -> tuple[bytes | None, bytes | None]:
        op = self.first_op
        if self.second_op is not None:
            self.first_op = self.second_op
        out_key, out_data = self.cur.get_full(None, op)
        if out_data is None:
            raise StopIteration
        else:
            return (out_key, out_data)


class DBDupIter(object):
    def __init__(self, cur: Cursor, op: MDBXCursorOp):
        self.cur = cur
        self.op = op

    def __iter__(self) -> DBDupIter:
        return self

    def __next__(self) -> DBIter:
        op = self.op
        self.op = MDBXCursorOp.MDBX_NEXT_NODUP

        k, v = self.cur.get_full(None, op)
        if k is None or v is None:
            raise StopIteration

        return DBIter(
            self.cur.dup(), MDBXCursorOp.MDBX_GET_CURRENT, MDBXCursorOp.MDBX_NEXT_DUP
        )


def get_build_info() -> Any:
    """
    :returns mdbx_build struct embedded in lib
    :rtype MDBXBuildInfo
    """
    return MDBXBuildInfo.in_dll(_lib, "mdbx_build")


def get_version_info() -> Any:
    """
    :returns mdbx_version struct embedded in lib
    :rtype MDBXVersionInfo
    """
    return MDBXVersionInfo.in_dll(_lib, "mdbx_version")


def make_exception(errno: int) -> BaseException:
    """
    Construct an exception as correct
    """
    err = _lib.mdbx_liberr2str(errno)
    if err is not None:
        return MDBXErrorExc(errno, err)
    return OSError(errno, os.strerror(errno))


_lib.mdbx_strerror_r.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
_lib.mdbx_strerror_r.restype = ctypes.c_char_p
_lib.mdbx_liberr2str.argtypes = [ctypes.c_int]
_lib.mdbx_liberr2str.restype = ctypes.c_char_p
_lib.mdbx_thread_register.argtypes = [ctypes.c_void_p]
_lib.mdbx_thread_register.restype = ctypes.c_int
_lib.mdbx_thread_unregister.argtypes = [ctypes.c_void_p]
_lib.mdbx_thread_unregister.restype = ctypes.c_int
_lib.mdbx_dbi_open2.argtypes = [
    ctypes.POINTER(MDBXTXN),
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_uint32),
]
_lib.mdbx_dbi_open2.restype = ctypes.c_int
_lib.mdbx_txn_abort.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_abort.restype = ctypes.c_int
_lib.mdbx_txn_set_userctx.argtypes = [ctypes.POINTER(MDBXTXN), ctypes.c_void_p]
_lib.mdbx_txn_set_userctx.restype = ctypes.c_int
_lib.mdbx_txn_get_userctx.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_get_userctx.restype = ctypes.c_void_p
_lib.mdbx_txn_reset.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_reset.restype = ctypes.c_int
_lib.mdbx_txn_renew.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_renew.restype = ctypes.c_int
_lib.mdbx_txn_commit.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_commit.restype = ctypes.c_int
_lib.mdbx_txn_commit_ex.argtypes = [
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(MDBXCommitLatency),
]
_lib.mdbx_txn_commit_ex.restype = ctypes.c_int
_lib.mdbx_txn_id.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_id.restype = ctypes.c_uint64
_lib.mdbx_txn_break.argtypes = [ctypes.POINTER(MDBXTXN)]
_lib.mdbx_txn_break.restype = ctypes.c_int
_lib.mdbx_txn_begin_ex.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(MDBXTXN),
    ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(MDBXTXN)),
    ctypes.c_void_p,
]
_lib.mdbx_txn_begin_ex.restype = ctypes.c_int
_lib.mdbx_txn_info.argtypes = [
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(MDBXTXNInfo),
    ctypes.c_bool,
]
_lib.mdbx_txn_info.restype = ctypes.c_int

_lib.mdbx_canary_get.argtypes = [ctypes.POINTER(MDBXTXN), ctypes.POINTER(MDBXCanary)]
_lib.mdbx_canary_get.restype = ctypes.c_int
_lib.mdbx_canary_put.argtypes = [ctypes.POINTER(MDBXTXN), ctypes.POINTER(MDBXCanary)]
_lib.mdbx_canary_put.restype = ctypes.c_int

MDBX_reader_list_func = ctypes.CFUNCTYPE(ctypes.c_int)
MDBX_reader_list_func.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint64,
    ctypes.c_uint64,
    ctypes.c_size_t,
    ctypes.c_size_t,
]
MDBX_reader_list_func.restype = ctypes.c_int
_lib.mdbx_reader_list.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(MDBX_reader_list_func),
    ctypes.c_void_p,
]
_lib.mdbx_reader_list.restype = ctypes.c_int
_lib.mdbx_drop.argtypes = [ctypes.POINTER(MDBXTXN), MDBXDBI, ctypes.c_void_p]
_lib.mdbx_drop.restype = ctypes.c_int
_lib.mdbx_put.argtypes = [
    ctypes.POINTER(MDBXTXN),
    MDBXDBI,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
]
_lib.mdbx_put.restype = ctypes.c_int
_lib.mdbx_get.argtypes = [
    ctypes.POINTER(MDBXTXN),
    MDBXDBI,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_lib.mdbx_get.restype = ctypes.c_int
_lib.mdbx_del.argtypes = [
    ctypes.POINTER(MDBXTXN),
    MDBXDBI,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_lib.mdbx_del.restype = ctypes.c_int

_lib.mdbx_env_create.argtypes = [ctypes.POINTER(ctypes.POINTER(MDBXEnv))]

_lib.mdbx_env_open.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_int,
]
_lib.mdbx_env_open.restype = ctypes.c_int

_lib.mdbx_env_close.argtypes = [ctypes.POINTER(MDBXEnv)]
_lib.mdbx_env_close.restype = ctypes.c_int

_lib.mdbx_env_close_ex.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_int]

_lib.mdbx_env_get_path.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(ctypes.c_char_p),
]
_lib.mdbx_env_get_path.restype = ctypes.c_int

_lib.mdbx_env_get_userctx.argtypes = [ctypes.POINTER(MDBXEnv)]
_lib.mdbx_env_get_userctx.restype = ctypes.c_void_p
_lib.mdbx_env_set_userctx.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_void_p]
_lib.mdbx_env_set_userctx.restype = ctypes.c_int
_lib.mdbx_env_info_ex.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(MDBXEnvinfo),
    ctypes.c_size_t,
]
_lib.mdbx_env_info_ex.restype = ctypes.c_int
_lib.mdbx_env_stat_ex.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(MDBXStat),
    ctypes.c_size_t,
]
_lib.mdbx_env_stat_ex.restype = ctypes.c_int

_lib.mdbx_env_set_syncperiod.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_uint]
_lib.mdbx_env_set_syncperiod.restype = ctypes.c_int
_lib.mdbx_env_set_syncbytes.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_size_t]
_lib.mdbx_env_set_syncbytes.restype = ctypes.c_int
_lib.mdbx_env_set_maxreaders.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_uint]
_lib.mdbx_env_set_maxreaders.restype = ctypes.c_int
_lib.mdbx_env_set_maxdbs.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_uint]
_lib.mdbx_env_set_maxdbs.restype = ctypes.c_int
_lib.mdbx_env_get_maxdbs.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_void_p]
_lib.mdbx_env_get_maxdbs.restype = ctypes.c_int
_lib.mdbx_env_set_geometry.argtypes = [
    ctypes.POINTER(MDBXEnv),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_lib.mdbx_env_set_geometry.restype = ctypes.c_int
_lib.mdbx_env_set_flags.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_int, ctypes.c_int]
_lib.mdbx_env_set_flags.restype = ctypes.c_int
_lib.mdbx_env_get_flags.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_void_p]
_lib.mdbx_env_get_flags.restype = ctypes.c_int

_lib.mdbx_env_sync_ex.argtypes = [ctypes.POINTER(MDBXEnv), ctypes.c_bool, ctypes.c_bool]
_lib.mdbx_env_sync_ex.restype = ctypes.c_int
_lib.mdbx_cursor_open.argtypes = [
    ctypes.POINTER(MDBXTXN),
    MDBXDBI,
    ctypes.POINTER(ctypes.POINTER(MDBXCursor)),
]
_lib.mdbx_cursor_open.restype = ctypes.c_int
_lib.mdbx_cursor_dbi.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_dbi.restype = ctypes.c_longlong
_lib.mdbx_cursor_get.argtypes = [
    ctypes.POINTER(MDBXCursor),
    ctypes.POINTER(Iovec),
    ctypes.POINTER(Iovec),
    ctypes.c_uint,
]
_lib.mdbx_cursor_get.restype = ctypes.c_int
_lib.mdbx_cursor_set_userctx.argtypes = [ctypes.POINTER(MDBXCursor), ctypes.c_void_p]
_lib.mdbx_cursor_set_userctx.restype = ctypes.c_int
_lib.mdbx_cursor_set_userctx.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_get_userctx.restype = ctypes.c_void_p
_lib.mdbx_cursor_txn.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_txn.restype = ctypes.POINTER(MDBXTXN)
_lib.mdbx_cursor_dbi.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_dbi.restype = ctypes.POINTER(MDBXDBI)
_lib.mdbx_cursor_copy.argtypes = [
    ctypes.POINTER(MDBXCursor),
    ctypes.POINTER(MDBXCursor),
]
_lib.mdbx_cursor_copy.restype = ctypes.c_int

_lib.mdbx_cursor_create.argtypes = [ctypes.c_void_p]
_lib.mdbx_cursor_create.restype = ctypes.POINTER(MDBXCursor)
_lib.mdbx_cursor_bind.argtypes = [
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(MDBXCursor),
    MDBXDBI,
]
_lib.mdbx_cursor_bind.restype = ctypes.c_int
_lib.mdbx_cursor_close.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_renew.argtypes = [ctypes.POINTER(MDBXTXN), ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_renew.restype = ctypes.c_int
_lib.mdbx_cursor_put.argtypes = [
    ctypes.POINTER(MDBXCursor),
    ctypes.POINTER(Iovec),
    ctypes.POINTER(Iovec),
    ctypes.c_uint,
]
_lib.mdbx_cursor_put.restype = ctypes.c_int
_lib.mdbx_cursor_del.argtypes = [ctypes.POINTER(MDBXCursor), ctypes.c_uint]
_lib.mdbx_cursor_del.restype = ctypes.c_int
_lib.mdbx_cursor_count.argtypes = [
    ctypes.POINTER(MDBXCursor),
    ctypes.POINTER(ctypes.c_size_t),
]
_lib.mdbx_cursor_count.restype = ctypes.c_int
_lib.mdbx_cursor_eof.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_eof.restype = ctypes.c_int
_lib.mdbx_cursor_on_first.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_on_first.restype = ctypes.c_int
_lib.mdbx_cursor_on_last.argtypes = [ctypes.POINTER(MDBXCursor)]
_lib.mdbx_cursor_on_last.restype = ctypes.c_int

_lib.mdbx_dbi_close.argtypes = [ctypes.POINTER(MDBXEnv), MDBXDBI]
_lib.mdbx_dbi_close.restype = ctypes.c_int

try:
    _lib.mdbx_cursor_put_attr.argtypes = [
        ctypes.POINTER(MDBXCursor),
        ctypes.POINTER(Iovec),
        ctypes.POINTER(Iovec),
        MDBXAttr,
        ctypes.c_uint,
    ]
    _lib.mdbx_cursor_put_attr.restype = ctypes.c_int
except:  # noqa: E722
    pass

try:
    _lib.mdbx_put_attr.argtypes = [
        ctypes.POINTER(MDBXTXN),
        MDBXDBI,
        ctypes.POINTER(Iovec),
        ctypes.POINTER(Iovec),
        MDBXAttr,
        ctypes.c_uint,
    ]
    _lib.mdbx_put_attr.restype = ctypes.c_int
except:  # noqa: E722
    pass

try:
    _lib.mdbx_set_attr.argtypes = [
        ctypes.POINTER(MDBXTXN),
        MDBXDBI,
        ctypes.POINTER(Iovec),
        ctypes.POINTER(Iovec),
        MDBXAttr,
    ]
    _lib.mdbx_set_attr.restype = ctypes.c_int
except:  # noqa: E722
    pass

try:
    _lib.mdbx_cursor_get_attr.argtypes = [
        ctypes.POINTER(MDBXCursor),
        ctypes.POINTER(Iovec),
        ctypes.POINTER(Iovec),
        ctypes.POINTER(MDBXAttr),
        ctypes.c_uint,
    ]
    _lib.mdbx_cursor_get_attr.restype = ctypes.c_int
except:  # noqa: E722
    pass

try:
    _lib.mdbx_get_attr.argtypes = [
        ctypes.POINTER(MDBXTXN),
        MDBXDBI,
        ctypes.POINTER(Iovec),
        ctypes.POINTER(Iovec),
        ctypes.POINTER(MDBXAttr),
    ]
    _lib.mdbx_get_attr.restype = ctypes.c_int
except:  # noqa: E722
    pass

MDBX_hsr_func = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(MDBXEnv),
    ctypes.POINTER(MDBXTXN),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint64,
    ctypes.c_uint,
    ctypes.c_size_t,
    ctypes.c_int,
)

MDBXHSRFunc = Callable[
    [
        Any,
        Any,
        int,
        int,
        int,  # of int/ctypes.c_uint64 afhankelijk van je voorkeur
        int,
        int,
        int,
    ],
    int,
]

_lib.mdbx_limits_dbsize_max.argtypes = [ctypes.POINTER(ctypes.c_int)]
_lib.mdbx_limits_dbsize_max.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_dbsize_min.argtypes = [ctypes.POINTER(ctypes.c_int)]
_lib.mdbx_limits_dbsize_min.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_keysize_max.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
_lib.mdbx_limits_keysize_max.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_pgsize_max.argtypes = []
_lib.mdbx_limits_pgsize_max.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_pgsize_min.argtypes = []
_lib.mdbx_limits_pgsize_min.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_txnsize_max.argtypes = [ctypes.POINTER(ctypes.c_int)]
_lib.mdbx_limits_txnsize_max.restype = ctypes.POINTER(ctypes.c_int)

_lib.mdbx_limits_valsize_max.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
_lib.mdbx_limits_valsize_max.restype = ctypes.POINTER(ctypes.c_int)


_lib.mdbx_is_readahead_reasonable.argtypes = [
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_int),
]
_lib.mdbx_is_readahead_reasonable.restype = ctypes.c_int

try:
    _lib.mdbx_get_sysraminfo.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    _lib.mdbx_get_sysraminfo.restype = ctypes.c_int
except:  # noqa: E722
    pass

_lib.mdbx_is_dirty.argtypes = [ctypes.POINTER(MDBXTXN), ctypes.c_void_p]
_lib.mdbx_is_dirty.restype = ctypes.c_int

_lib.mdbx_txn_straggler.argtypes = [
    ctypes.POINTER(MDBXTXN),
    ctypes.POINTER(ctypes.c_int),
]
_lib.mdbx_txn_straggler.restype = ctypes.c_int

_lib.mdbx_dbi_sequence.argtypes = [
    ctypes.POINTER(MDBXTXN),
    MDBXDBI,
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.c_uint64,
]
_lib.mdbx_dbi_sequence.restype = ctypes.c_int
