#! /usr/bin/env python

###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
#
# Weasel is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# version 2 for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
###############################################################################
#
# brandiso.py [options]
#
# Implant an ISO image with a checksum and the given volume identifier
# string.  See usage for more details.

import os
import sys
import getopt
import struct
try:
    import task_progress
except ImportError:
    # fake the module if we can't find it.
    class TaskProgress(object):
        def taskStarted(*args): pass
        def taskProgress(*args): pass
        def taskFinish(*args): pass
    task_progress = TaskProgress()

class BrandISOException(Exception):
    '''Exception raise by the brandiso module'''

VERBOSE = 0

SECTOR_SIZE = 2048

ID_FIELD = 'vol id'
CHECKSUM_FIELD = 'app use'
# offset of md5 checksum in the appdata field, in case appdata is used
# for some other purposes as well
CHECKSUM_OFFSET = 0

CHECKSUM_SIZE = 16
READ_BLOCK_SIZE = 4096

# Map of byte lengths to struct.pack format letters.
PACK_FORMAT = {
    1 : "B",
    2 : "H",
    4 : "I",
    }

SEEK_SET = 0
SEEK_CUR = 1
SEEK_END = 2

# Conversion functions for each field type:
#   sec - The contents of the sector.
#   o - Offset of the field in bytes.
#   s - Size of the field in bytes.
def TYPE_RAW(sec, o, s):
    return ' '.join(["%02X" % ord(ch) for ch in sec[o:o + s]])
def TYPE_STR(sec, o, s):
    return sec[o:o + s].strip()
def TYPE_LSB_INT(sec, o, s):
    return str(struct.unpack("<%s" % PACK_FORMAT[s], sec[o:o + s])[0])
def TYPE_MSB_INT(sec, o, s):
    return str(struct.unpack(">%s" % PACK_FORMAT[s], sec[o:o + s])[0])
def TYPE_DATETIME(sec, o, s):
    return ("%s-%s-%s %s:%s:%s.%s %d" %
            struct.unpack("4s2s2s2s2s2s2s1b", sec[o:o + s]))

# primary volume descriptor fields
# reference: http://www.ccs.neu.edu/home/bchafy/cdb/info/iso9660.txt,
# http://www.mactech.com/articles/develop/issue_03/high_sierra.html
VOL_DESC_STRUCT = (
    (1, TYPE_LSB_INT, 'type'), # must be 1 for primary volume descriptor
    (5, TYPE_STR, 'std id'), # must be "CD001"
    (1, TYPE_LSB_INT, 'std ver'), # must be 1
    (1, TYPE_LSB_INT, 'flags'), # 0 in primary volume descriptor
    (32, TYPE_STR, 'sys id'),
    (32, TYPE_STR, 'vol id'),
    (8, TYPE_RAW, 'reserved 0'), # zeros
    (4, TYPE_LSB_INT, 'lsb vol size'), # volume size in LSB byte order, in sectors
    (4, TYPE_MSB_INT, 'msb vol size'), # volume size in MSB byte order, in sectors
    (32, TYPE_RAW, 'escape seq'), # zeros in primary volume descriptor
    (2, TYPE_LSB_INT, 'lsb vol count'), # number of volumes
    (2, TYPE_MSB_INT, 'msb vol count'),
    (2, TYPE_LSB_INT, 'lsb vol set seq num'), # which volume in volume set (not used)
    (2, TYPE_MSB_INT, 'msb vol set seq num'),
    (2, TYPE_LSB_INT, 'lsb sec size'), # sector size, 2048
    (2, TYPE_MSB_INT, 'msb sec size'),
    (4, TYPE_LSB_INT, 'lsb path table size'), # number of bytes in path table
    (4, TYPE_MSB_INT, 'msb path table size'), 
    (4, TYPE_LSB_INT, 'lsb path table 1'), # mandatory
    (4, TYPE_LSB_INT, 'lsb path table 2'), # optional
    (4, TYPE_MSB_INT, 'msb path table 1'), # mandatory
    (4, TYPE_MSB_INT, 'msb path table 2'), # optional
    (34, TYPE_RAW, 'root dir'), # duplicate root directory entry
    (128, TYPE_STR, 'vol set id'),
    (128, TYPE_STR, 'publisher id'),
    (128, TYPE_STR, 'data preparer id'),
    (128, TYPE_STR, 'app id'),
    (37, TYPE_RAW, 'copyright file id'),
    (37, TYPE_RAW, 'abstract file id'),
    (37, TYPE_RAW, 'bibliographical file id'),
    (17, TYPE_DATETIME, 'vol created'), # creation time
    (17, TYPE_DATETIME, 'vol modified'), # last modification time
    (17, TYPE_DATETIME, 'vol expires'), # expiration
    (17, TYPE_DATETIME, 'vol effective'), # ?
    (1, TYPE_LSB_INT, 'file struct std ver'), # 1
    (1, TYPE_RAW, 'reserved 1'), # must be 0
    (512, TYPE_RAW, 'app use'), # reserved for application use (usually zeros)
    (653, TYPE_RAW, 'future'), # zeros
)

fields = {}

# fills in the offset field
def fill_fields():
    off = 0
    for (sz, tpfn, nm) in VOL_DESC_STRUCT:
        fields[nm] = (off, sz, tpfn)
        off += sz

# returns md5 hash of a file with a hole,
# the hole contents is treated as zeros
def calc_md5(f, zpos, zlen, isosize):
    from md5 import md5

    f.seek(0, SEEK_END)
    fileSize = f.tell()
    task_progress.taskStarted('brandiso.calc_md5', fileSize)
    m = md5()
    f.seek(0, SEEK_SET)
    pos = 0
    while pos < isosize:
        # Read up to the start of the zero-d out spot, skip that and then read
        # through the rest of the file.
        if pos < zpos:
            blockSize = min(zpos - pos, READ_BLOCK_SIZE)
        elif pos == zpos:
            task_progress.taskProgress('brandiso.calc_md5', zlen)
            pos = zpos + zlen
            f.seek(pos, SEEK_SET)
            m.update('\0' * zlen) # Still need to update the digest with zeroes.
            continue
        else:
            blockSize = min(isosize - pos, READ_BLOCK_SIZE)

        block = f.read(blockSize)
        if not block:
            break

        task_progress.taskProgress('brandiso.calc_md5', len(block))
        m.update(block)
        pos += len(block)

    digest = m.digest()
    assert len(digest) == CHECKSUM_SIZE
    task_progress.taskFinish('brandiso.calc_md5')
    
    return digest
    

# prints fields of the primary volume descriptor
def print_primary(sec):
    for _sz, _fn, fld in VOL_DESC_STRUCT: # ('sys id', 'vol id', 'app use')
        (off, sz, fn) = fields[fld]
        print "%s: %s" % (fld, fn(sec, off, sz))

# seeks to the primary volume descriptor and returns that sector
def seek_to_primary(img):
    # contents of the first 16 sectors is not specified
    img.seek(SECTOR_SIZE * 16)

    # processing volume descriptors
    while True:
        sec = img.read(SECTOR_SIZE)
        if len(sec) != SECTOR_SIZE:
            raise BrandISOException('Unexpected EOF (wrong ISO image?)')

        # terminating descriptor
        if ord(sec[0]) == 255:
            raise BrandISOException('No primary descriptor found!')

        #primary descriptor
        if ord(sec[0]) == 1:
            img.seek(-SECTOR_SIZE, SEEK_CUR)
            return sec

# returns printable representation of binary data
def pretty(bin):
    return ''.join(["%02x" % ord(c) for c in bin])

def iso_size(sec):
    size_off, size_len, size_fn = fields['lsb vol size']
    isosecsize = int(size_fn(sec, size_off, size_len))
    secsize_off, secsize_len, secsize_fn = fields['lsb sec size']
    secsize = int(secsize_fn(sec, secsize_off, secsize_len))
    
    return isosecsize * secsize

# brands an image with specified appid and writes md5 hash into appdata field
def brand_iso(filename, idstr):
    img = open(filename, 'r+b')
    try:
        sec = seek_to_primary(img)
        
        sec_off = img.tell()
        chsum_off, _, _ = fields[CHECKSUM_FIELD]
        id_off, id_len, _ = fields[ID_FIELD]

        # writing id
        img.seek(sec_off + id_off, os.SEEK_SET)
        img.write(idstr[:id_len])
        print "ID written:", idstr[:id_len]
        
        digest = calc_md5(img,
                          sec_off + chsum_off + CHECKSUM_OFFSET,
                          CHECKSUM_SIZE,
                          iso_size(sec))

        # writing checksum
        img.seek(sec_off + chsum_off + CHECKSUM_OFFSET, os.SEEK_SET)
        img.write(digest)
        print "Checksum written:", pretty(digest)
    finally:
        img.close()

# verifies an md5 hash of a branded image and prints its sys id
def extract_iso_checksums(filename):
    img = open(filename, 'rb')
    retval = None
    try:
        sec = seek_to_primary(img)

        sec_off = img.tell()
        chsum_off, _, _ = fields[CHECKSUM_FIELD]
        id_off, id_len, _ = fields[ID_FIELD]
        written_digest = sec[chsum_off + CHECKSUM_OFFSET:
                                 chsum_off + CHECKSUM_OFFSET + CHECKSUM_SIZE]
        id_str = sec[id_off: id_off + id_len]

        # calculating the actual checksum
        digest = calc_md5(img, sec_off + chsum_off + CHECKSUM_OFFSET,
                          CHECKSUM_SIZE,
                          iso_size(sec))

        retval = (written_digest, digest, id_str)
    finally:
        img.close()

    return retval

def verify_iso(filename):
    written_digest, digest, id_str = extract_iso_checksums(filename)
    if digest == written_digest:
        print "%s: OK" % id_str.strip()
    else:
        print "%s: FAILED recorded %s != actual %s" % (
            id_str.strip(), pretty(written_digest), pretty(digest))
        sys.exit(1)

# prints fields of the primary volume descriptor
def list_iso(filename):
    img = open(filename, 'rb')
    try:
        print_primary(seek_to_primary(img))
    finally:
        img.close()

# zero-fill the checksum placeholder
def zfill_iso(filename):
    img = open(filename, 'r+b')
    try:
        seek_to_primary(img)
        sec_off = img.tell()
        chsum_off, _, _ = fields[CHECKSUM_FIELD]

        img.seek(sec_off + chsum_off + CHECKSUM_OFFSET, os.SEEK_SET)
        img.write('\0' * CHECKSUM_SIZE)
    finally:
        img.close()

def usage(argv):
    print "Usage: %s [-hv] <mode> <ISO image>" % argv[0]
    print
    print "Mode options:"
    print "  -b <vol id>    Brand an ISO image with a checksum and the given"
    print "                 volume identifier string."
    print "  -c             Check the checksum in a branded ISO image."
    print "  -l             List the fields of the primary volume descriptor."
    print "  -z             Zero out the checksum (for debugging)."
    print
    print "Options:"
    print "  -h             Print this help message."
    print "  -v             Increase verbosity."
    print
    print "Example:"
    print "  $ %s -c newiso.iso" % argv[0]
    print ("  : FAILED recorded 20202020202020202020202020202020 != "
           "actual 6eb7d639e6605dc187179d3bcabd9de2")
    print "  $ %s -b 'My ISO v1.0' newiso.iso" % argv[0]
    print "  $ %s -c newiso.iso" % argv[0]
    print "  My ISO v1.0: OK"
    
#
# init code
#

fill_fields()

if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvb:clz")

        if len(args) != 1:
            raise getopt.error("expecting ISO path")

        isoPath = args[0]

        modeFunction = None
        for opt, arg in opts:
            if opt == "-h":
                usage()
                sys.exit()
            elif opt == "-v":
                VERBOSE += 1
            elif opt == "-b":
                _id_off, id_len, _ = fields[ID_FIELD]
                if len(arg) > id_len:
                    raise getopt.error(
                        "volume identifier must be <= %d characters" % id_len)
                modeFunction = lambda: brand_iso(isoPath, arg)
            elif opt == "-c":
                modeFunction = lambda: verify_iso(isoPath)
            elif opt == "-l":
                modeFunction = lambda: list_iso(isoPath)
            elif opt == "-z":
                modeFunction = lambda: zfill_iso(isoPath)

        if not modeFunction:
            raise getopt.error("expecting mode argument (i.e. -b, -l, -c, -z)")

        modeFunction()
    except IOError, ioe:
        sys.stderr.write("error: %s\n" % str(ioe))
        sys.exit(1)
    except getopt.error, e:
        sys.stderr.write("error: %s\n" % str(e))
        usage(sys.argv)
        sys.exit(1)
