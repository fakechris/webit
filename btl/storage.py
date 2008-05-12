#coding:utf-8

import os, os.path
from bisect import bisect_right
import Queue

from BTL.bencode import *
from BTL.DictWithLists import DictWithLists, DictWithSets
from BTL.sparse_set import SparseSet
from BTL.ConvertedMetainfo import ConvertedMetainfo

from BitTorrent.Storage_base import open_sparse_file, make_file_sparse
from BitTorrent.Storage_base import bad_libc_workaround, is_open_for_write
from BitTorrent.Storage_base import UnregisteredFileException

from BitTorrent.platform import is_path_too_long, no_really_makedirs
from BitTorrent.platform import get_allocated_regions

def get_metainfo(torrent_file):
    metafile = open(torrent_file, "rb")
    metainfo = ConvertedMetainfo(bdecode(metafile.read()))
    metafile.close()
    return metainfo

class BTFailure(Exception):
    pass    
    
class BtFilePool(object):
    def __init__(self, max_files_open):
        self.file_to_torrent = {}

        self.active_file_to_handles = DictWithSets()
        self.open_file_to_handles = DictWithLists()

        self.set_max_files_open(max_files_open)

        self.diskq = Queue.Queue()

    def close_all(self):
        failures = {}
        while self.get_open_file_count() > 0:
            while len(self.open_file_to_handles) > 0:
                filename, handle = self.open_file_to_handles.popitem()
                try:
                    handle.close()
                except Exception, e:
                    failures[self.file_to_torrent[filename]] = e

        for torrent, e in failures.iteritems():
            torrent.got_exception(e)

    def close_files(self, file_set):
        failures = set()
        done = False

        while not done:

            filenames = list(self.open_file_to_handles.iterkeys())
            for filename in filenames:
                if filename not in file_set:
                    continue
                handles = self.open_file_to_handles.poprow(filename)
                for handle in handles:
                    try:
                        handle.close()
                    except Exception, e:
                        failures.add(e)

            done = True
            for filename in file_set.iterkeys():
                if filename in self.active_file_to_handles:
                    done = False
                    break

        if len(failures) > 0:
            raise failures.pop()

    def set_max_files_open(self, max_files_open):
        if max_files_open <= 0:
            max_files_open = 1e100
        self.max_files_open = max_files_open
        self.close_all()

    def add_files(self, files, torrent):
        for filename in files:
            if filename in self.file_to_torrent:
                raise BTFailure(_("File %s belongs to another running torrent")
                                % filename)
        for filename in files:
            self.file_to_torrent[filename] = torrent

    def remove_files(self, files):
        for filename in files:
            del self.file_to_torrent[filename]

    def _ensure_exists(self, filename, length=0):
        if not os.path.exists(filename):
            f = os.path.split(filename)[0]
            if f != '' and not os.path.exists(f):
                os.makedirs(f)
            f = file(filename, 'wb')
            make_file_sparse(filename, f, length)
            f.close()

    def get_open_file_count(self):
        t = self.open_file_to_handles.total_length()
        t += self.active_file_to_handles.total_length()
        return t

    def acquire_handle(self, filename, for_write, length=0):
        # this will block until a new file handle can be made

        if filename not in self.file_to_torrent:
            raise UnregisteredFileException()

        if filename in self.open_file_to_handles:
            handle = self.open_file_to_handles.pop_from_row(filename)
            if for_write and not is_open_for_write(handle.mode):
                handle.close()
                handle = open_sparse_file(filename, 'rb+', length=length)
            #elif not for_write and is_open_for_write(handle.mode):
            #    handle.close()
            #    handle = open_sparse_file(filename, 'rb', length=length)
        else:
            if self.get_open_file_count() == self.max_files_open:
                oldfname, oldhandle = self.open_file_to_handles.popitem()
                oldhandle.close()
            self._ensure_exists(filename, length)
            if for_write:
                handle = open_sparse_file(filename, 'rb+', length=length)
            else:
                handle = open_sparse_file(filename, 'rb', length=length)

        self.active_file_to_handles.push_to_row(filename, handle)
        return handle

    def release_handle(self, filename, handle):
        self.active_file_to_handles.remove_fom_row(filename, handle)
        self.open_file_to_handles.push_to_row(filename, handle)

class BtStorage(object):

    def __init__(self, filepool, save_path, files):
        self.filepool = filepool
        self.initialize(save_path, files)

    def initialize(self, save_path, files):
        # a list of bytes ranges and filenames for window-based IO
        self.ranges = []
        # a dict of filename-to-ranges for piece priorities and filename lookup
        self.range_by_name = {}
        # a sparse set for smart allocation detection
        self.allocated_regions = SparseSet()

        # dict of filename-to-length on disk (for % complete in the file view)
        self.undownloaded = {}
        self.save_path = save_path

        # Rather implement this as an ugly hack here than change all the
        # individual calls. Affects all torrent instances using this module.
        #bad_libc_workaround()

        self.initialized = False
        return self._build_file_structs(self.filepool, files)
        
    def _build_file_structs(self, filepool, files):
        total = 0
        for filename, length in files:
            self.undownloaded[filename] = length
            if length > 0:
                self.ranges.append((total, total + length, filename))

            self.range_by_name[filename] = (total, total + length)

            if os.path.exists(filename):
                if not os.path.isfile(filename):
                    raise BTFailure(_("File %s already exists, but is not a "
                                      "regular file") % filename)
                l = os.path.getsize(filename)
                if l > length:
                    # This is the truncation Bram was talking about that no one
                    # else thinks is a good idea.
                    #h = file(filename, 'rb+')
                    #make_file_sparse(filename, h, length)
                    #h.truncate(length)
                    #h.close()
                    l = length

                a = get_allocated_regions(filename, begin=0, length=l)
                if a is not None:
                    a.offset(total)
                else:
                    a = SparseSet()
                    if l > 0:
                        a.add(total, total + l)
                self.allocated_regions += a
            total += length
        self.total_length = total
        self.initialized = True
        return True

    def get_byte_range_for_filename(self, filename):
        if filename not in self.range_by_name:
            filename = os.path.normpath(filename)
            filename = os.path.join(self.save_path, filename)
        return self.range_by_name[filename]

    def was_preallocated(self, pos, length):
        return self.allocated_regions.is_range_in(pos, pos+length)

    def get_total_length(self):
        return self.total_length

    def _intervals(self, pos, amount):
        r = []
        stop = pos + amount
        p = max(bisect_right(self.ranges, (pos, 2 ** 500)) - 1, 0)
        for begin, end, filename in self.ranges[p:]:
            if begin >= stop:
                break
            r.append((filename, max(pos, begin) - begin, min(end, stop) - begin))
        return r

    def _read(self, filename, pos, amount):
        begin, end = self.get_byte_range_for_filename(filename)
        length = end - begin
        
        h = self.filepool.acquire_handle(filename, for_write=False, length=length)
        if h is None:
            return
        try:
            h.seek(pos)
            r = h.read(amount)
        finally:
            self.filepool.release_handle(filename, h)
        return r

    def _batch_read(self, pos, amount):
        dfs = []
        r = []

        # queue all the reads
        for filename, pos, end in self._intervals(pos, amount):
            r.append(self._read(filename, pos, end - pos))

        r = ''.join(r)

        if len(r) != amount:
            raise BTFailure(_("Short read (%d of %d) - something truncated files?") %
                            (len(r), amount))

        return r

    def read(self, pos, amount):
        return self._batch_read(pos, amount)

    def _write(self, filename, pos, s):
        begin, end = self.get_byte_range_for_filename(filename)
        length = end - begin
        h = self.filepool.acquire_handle(filename, for_write=True, length=length)
        if h is None:
            return
        try:
            h.seek(pos)
            h.write(s)
        finally:
            self.filepool.release_handle(filename, h)
        return len(s)

    def _batch_write(self, pos, s):
        dfs = []

        total = 0
        amount = len(s)

        # queue all the writes
        for filename, begin, end in self._intervals(pos, amount):
            length = end - begin
            d = buffer(s, total, length)
            total += length
            self._write(filename, begin, d)

        return total

    def write(self, pos, s):
        return self._batch_write(pos, s)

    def close(self):
        self.filepool.close_files(self.range_by_name)

    def downloaded(self, pos, length):
        for filename, begin, end in self._intervals(pos, length):
            self.undownloaded[filename] -= end - begin
    
class StorageManage:
    def __init__(self, torrent_file, storage_path):        
        self.metainfo = get_metainfo(torrent_file)
        
        self._filepool = BtFilePool(1000)
                
        if self.metainfo.is_batch:
            myfiles = [os.path.join(storage_path, f) for f in
                       self.metainfo.files_fs]
        else:
            myfiles = [storage_path, ]
        
        for filename in myfiles:
            if is_path_too_long(filename):
                raise BTFailure("Filename path exceeds platform limit: %s" % filename)
        
        self.working_path = storage_path
        
        if self.metainfo.is_batch:
            myfiles = [os.path.join(self.working_path, f) for f in
                       self.metainfo.files_fs]
        else:
            myfiles = [self.working_path, ]
        
        #assert self._myfiles == None, '_myfiles should be None!'
        self._filepool.add_files(myfiles, self)
        self._myfiles = myfiles
        
        self._storage = BtStorage(self._filepool, storage_path, 
            zip(self._myfiles, self.metainfo.sizes))
            
    def read(self, pos, amount):
        return self._storage.read(pos, amount)

    def write(self, pos, s):
        return self._storage.write(pos, s)

    
if __name__ == "__main__":
    sm = StorageManage("c:\\temp\\test.torrent", "c:\\temp\\test")
    sm1 = StorageManage("c:\\temp\\test.torrent", "c:\\temp\\test1")
    for i in range(0, 10):
        for j in range(0, 8):            
            s = sm.read(i*524228 + j*65536, 65536)
            sm1.write(i*524228 + j*65536, s)
    
    
        
        
        