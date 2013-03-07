
###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
#
# Weasel is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation version 2 and no later version.
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

'''A module for faking chroot functionality.

This module overrides various functions and manipulates their arguments to
prepend the path to a fake root directory.  Obviously, this is not completely
transparent, but it gets the job done.

To set the root directory, you can call os.chroot or set fauxroot.FAUXROOT
directly.  This module also overrides util.getUuid() to return canned UUID
values for partitions.  The mapping of partition device name to UUID is
contained in the fauxroot.PART_UUID_CONFIG dictionary.

>>> import os
>>> os.path.exists("/fauxroot.py")
False
>>> os.chroot(".")
>>> os.path.exists("/fauxroot.py")
True
>>> glob.glob("/vmk*.py")
['/vmkctl.py']

See test/good-config.1/fauxconfig.py
'''

import re
import os
import sys
import glob
import stat
import statvfs
import time
import shlex
import shutil
import fnmatch
import urllib2
import datetime
import commands
import StringIO
import urlparse
import libxml2
import itertools
import fauxlocations
import tempfile
import random
import string
import __builtin__

from types import TupleType

# FAUXROOT controls whether the fake chroot functionality is enabled or not.
# When set to None, it is disabled.  Otherwise, it is a list of directories that
# describe the path to the fake root directory.  Calls to fake commands that do
# a chroot will push the directory onto the list before executing the emulated
# command and pop it off when finished.
FAUXROOT = None

EXCLUDE_FILES = []
EXCLUDE_PATHS = []
EMPTY_FILES = []
PART_UUID_CONFIG = {}
SYNC_COUNT = 0

PROMPTS = {}
PROMPT_LOG = []

# Map of executable paths to functions that imitate the executable.  The
# functions should accept a list, the command line arguments, and return either
# a tuple containing the output generated and exit status; or just the exit
# status.
EXEC_FUNCTIONS = {}

WRITTEN_FILES = {}

PROC_FILES = {}

DELETED_FILES = {}

UMOUNTED_FILES = {}

MASKED_FILES = {}

SLEEP_LOG = []

class CopyOnWriteFile(StringIO.StringIO):
    class StatResult(tuple):
        # XXX Silly fake stat result for things like os.path.getsize
        def __getattr__(self, key):
            if key == "st_mode":
                return self[stat.ST_MODE]
            elif key == "st_size":
                return self[stat.ST_SIZE]
            elif key == "st_dev":
                return self[stat.ST_DEV]
            elif key == "st_atime":
                return self[stat.ST_ATIME]
            elif key == "st_mtime":
                return self[stat.ST_MTIME]

            return object.__getattribute__(self, key)

    class StatvfsResult(tuple):
        def __getattribute__(self, key):
            if key == "f_frsize":
                return self[statvfs.F_FRSIZE]
            elif key == "f_bavail":
                return self[statvfs.F_BAVAIL]
            
            return object.__getattribute__(self, key)
        
    def __init__(self, contents="", mode=0700, fmode=stat.S_IFREG, rdev=0):
        StringIO.StringIO.__init__(self, contents)
        self.fmode = fmode
        self.mode = mode
        self.ino = 1
        self.dev = 8 << 8 | 1
        self.rdev = rdev
        self.nlink = 1
        self.uid = 0
        self.gid = 0
        self.atime = 0
        self.mtime = time.time()
        self.ctime = 0

        self.f_frsize = 4096
        self.f_bavail = 1000000

    def stat(self):
        retval = CopyOnWriteFile.StatResult((self.mode | self.fmode,
                                             self.ino,
                                             self.dev,
                                             self.nlink,
                                             self.uid,
                                             self.gid,
                                             len(self.getvalue()),
                                             self.atime,
                                             self.mtime,
                                             self.ctime))
        retval.st_rdev = self.rdev
        return retval

    def statvfs(self):
        return CopyOnWriteFile.StatvfsResult((4096,
                                              self.f_frsize,
                                              1000000,
                                              1000000,
                                              self.f_bavail,
                                              100,
                                              100,
                                              100,
                                              0,
                                              128))

    def printable(self):
        # ASCII chars 32 to 126 are more printable than string.printable
        printable = [chr(i) for i in range(32,127)]
        result = [byte for byte in self.getvalue() if byte in printable]
        return ''.join(result)

    def __repr__(self):
        return '<CopyOnWriteFile %s >' % self.printable()[:30]

    def fileno(self):
        return 22
    
    def close(self):
        return
    
def _startsWithOneOf(haystack, needles):
    '''return True if haystack starts with any of the needles
    this is equivalent to Python 2.5's haystack.startswith(tuple(needles))
    '''
    for needle in needles:
        if haystack.startswith(needle):
            return True

    return False

def _stripFauxRoot(path):
    if FAUXROOT:
        newPath = path[len("/".join(FAUXROOT)):]
        if not newPath.startswith("/"):
            newPath = "/" + newPath
        return newPath
    else:
        return path

# XXX
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                os.path.pardir,
                                os.path.pardir))
import util

def _excludedPath(path):
    for excludedPath in EXCLUDE_PATHS:
        if path.startswith(excludedPath):
            return True

    return False

def prepend_root(path):
    global FAUXROOT

    path = os.path.normpath(path)
    
    if (FAUXROOT and os.path.isabs(path) and
        not path.startswith("/".join(FAUXROOT)) and
        not _excludedPath(path) and (path not in EXCLUDE_FILES)):
        path = os.path.join("/".join(FAUXROOT), re.sub('/+', '', path, 1))
        pass

    return path

class PopenFile(StringIO.StringIO):
    def __init__(self, exitCode, contents=""):
        StringIO.StringIO.__init__(self, contents)
        self.exitCode = exitCode

    def close(self):
        return self.exitCode


oldChroot = os.chroot

def chroot_chroot(path):
    global FAUXROOT

    if FAUXROOT:
        FAUXROOT.append(path)
    else:
        FAUXROOT = [path]
    return

os.chroot = chroot_chroot


oldOpen = __builtin__.open

def chroot_open(path, mode='r', bufsize=1):
    global FAUXROOT, WRITTEN_FILES

    if FAUXROOT and os.path.isabs(path):
        path = os.path.normpath("/".join(FAUXROOT[1:]) + path)

        if path in PROC_FILES:
            return PROC_FILES[path]()

        if _startsWithOneOf(path, EMPTY_FILES):
            return StringIO.StringIO('')

        if path not in WRITTEN_FILES and (
            'w' in mode or 'a' in mode or '+' in mode):
            # Use oldExists so no munging/WRITTEN_FILES magic happens.
            if 'a' in mode and oldExists(prepend_root(path)):
                contents = oldOpen(prepend_root(path), 'r').read()
            else:
                contents = ""
            WRITTEN_FILES[path] = CopyOnWriteFile(contents)
        
        if path in WRITTEN_FILES:
            f = WRITTEN_FILES[path]
            if 'a' in mode:
                f.seek(0, 2)
            else:
                f.seek(0, 0)
                if 'w' in mode:
                    f.truncate()
            return f

        if path in MASKED_FILES:
            raise IOError("[masked] No such file or directory %s" % path)

    return oldOpen(prepend_root(path), mode, bufsize)

__builtin__.open = chroot_open
__builtin__.file = chroot_open

oldReadlink = os.readlink

def chroot_readlink(path):
    global FAUXROOT, WRITTEN_FILES

    if FAUXROOT and os.path.isabs(path):
        path = os.path.normpath("/".join(FAUXROOT[1:]) + path)

        if path in WRITTEN_FILES and WRITTEN_FILES[path].fmode == stat.S_IFLNK:
            return WRITTEN_FILES[path].getvalue()

    return oldReadlink(path)

os.readlink = chroot_readlink

oldRawInput = __builtin__.raw_input

def chroot_raw_input(prompt=None):
    PROMPT_LOG.append(prompt)
    if prompt in PROMPTS:
        return PROMPTS[prompt].next()

    return oldRawInput(prompt)

__builtin__.raw_input = chroot_raw_input


oldSystem = os.system
SYSTEM_LOG = []

def isplit(predicate, iterable):
    '''Make an iterator that splits up an iterable based on a predicate.

    The predicate should take a single argument and return True if the argument
    is a split-point.  Any objects collected from the iterable up to that point
    and the split-point will be returned in a pair.  If no objects in the
    iterable are split-points, the split-point in the pair will be None.

    >>> l = ["one", "two", "&&", "three", "||", "four"]
    >>> [t for t in isplit(lambda tok: tok in ('&&', '||'), l)]
    [(['one', 'two'], '&&'), (['three'], '||'), (['four'], None)]
    >>> l = ["one", "two"]
    >>> [t for t in isplit(lambda tok: tok in ('&&', '||'), l)]
    [(['one', 'two'], None)]
    '''
    retval = []
    for x in iterable:
        if predicate(x):
            yield retval, x
            retval = []
        else:
            retval.append(x)
    yield retval, None

def chroot_system(cmdline):
    tokens = shlex.split(cmdline)
    SYSTEM_LOG.append(tokens)

    # Split up the command-line based on the shell boolean operators.  We
    # execute each command ourselves and do the and'ing and or'ing ourselves.
    cmds = isplit(lambda tok: tok in ('&&', '||'), tokens)

    for cmd, oper in cmds:
        # Skip over environment vars (e.g. "NEWRD=1 esxcfg-boot")
        for tok in cmd:
            if "=" not in tok:
                cmdName = tok
                break

        if cmdName in EXEC_FUNCTIONS:
            # It's an simulated command.
            result = EXEC_FUNCTIONS[cmdName](cmd)
            if type(result) is TupleType:
                retval = result[1]
            else:
                retval = result
        else:
            # Try the real thing.  In case any of the arguments are paths, try
            # to prepend the fake root path so things actually work.
            retval = oldSystem(" ".join([
                '"%s"' % prepend_root(tok) for tok in cmd]))

        if oper == None:
            # No operators left to process.
            return retval
        elif retval != 0 and oper == '&&':
            # Command failed, do the "and" short-circuit.
            return retval
        elif retval == 0 and oper == '||':
            # Command succeeded, do the "or" short-circuit.
            return retval

        # More commands to process...

    assert False, "Shouldn't get here..."

os.system = chroot_system


oldPopen = os.popen

def chroot_popen(cmdline, mode='r', bufsize=8192):
    tokens = shlex.split(cmdline)
    SYSTEM_LOG.append(tokens)

    if tokens[0] in EXEC_FUNCTIONS:
        result = EXEC_FUNCTIONS[tokens[0]](tokens)
        if type(result) is TupleType:
            return PopenFile(result[1], result[0])
        else:
            return PopenFile(result)
    else:
        return oldPopen(" ".join([
            '"%s"' % prepend_root(tok) for tok in tokens]))

os.popen = chroot_popen


oldGetstatusoutput = commands.getstatusoutput

def chroot_getstatusoutput(cmdline):
    out = chroot_popen(cmdline, 'r')
    contents = out.read()
    rc = out.close()

    return (rc, contents)

commands.getstatusoutput = chroot_getstatusoutput


oldExecv = os.execv
EXECV_LOG = []

def chroot_execv(command, argv):
    EXECV_LOG.append((command, argv))

    if command in EXEC_FUNCTIONS:
        result = EXEC_FUNCTIONS[command](argv)
        if type(result) is TupleType:
            return result[1]
        else:
            return result
    else:
        return oldExecv(prepend_root(command), argv)

os.execv = chroot_execv


oldExists = os.path.exists

def chroot_exists(path):
    global FAUXROOT

    path = os.path.normpath(path)
    if FAUXROOT:
        if path in WRITTEN_FILES:
            return True
        elif path in MASKED_FILES:
            return False

    return oldExists(prepend_root(path))

os.path.exists = chroot_exists

oldLexists = os.path.lexists

def chroot_lexists(path):
    global FAUXROOT

    path = os.path.normpath(path)
    if FAUXROOT:
        if path in WRITTEN_FILES:
            return True
        elif path in MASKED_FILES:
            return False

    return oldLexists(prepend_root(path))

os.path.lexists = chroot_lexists


oldAccess = os.access

def chroot_access(path, mode):
    return oldAccess(prepend_root(path), mode)

os.access = chroot_access


oldChmod = os.chmod

def chroot_chmod(path, mode):
    global FAUXROOT
    
    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        WRITTEN_FILES[path].mode = mode
        return
    
    return oldChmod(prepend_root(path), mode)

os.chmod = chroot_chmod


oldChown = os.chown

def chroot_chown(path, uid, gid):
    global FAUXROOT

    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        WRITTEN_FILES[path].uid = uid
        WRITTEN_FILES[path].gid = gid
        return

    return oldChown(prepend_root(path), uid, gid)

os.chown = chroot_chown


oldIsdir = os.path.isdir

def chroot_isdir(path):
    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        if WRITTEN_FILES[path].fmode == stat.S_IFDIR:
            return chroot_glob(path)
    return oldIsdir(prepend_root(path))

os.path.isdir = chroot_isdir

oldIslink = os.path.islink

def chroot_islink(path):
    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        if WRITTEN_FILES[path].fmode == stat.S_IFLNK:
            return chroot_glob(path)
    return oldIslink(prepend_root(path))

os.path.islink = chroot_islink



oldUnlink = os.unlink

def chroot_unlink(path):
    global FAUXROOT
    
    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        DELETED_FILES[(time.time(), path)] = WRITTEN_FILES[path]
        del WRITTEN_FILES[path]
        return
    
    return oldUnlink(prepend_root(path))

os.unlink = chroot_unlink
os.remove = chroot_unlink


oldRename = os.rename

def chroot_rename(src, dst):
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if src in WRITTEN_FILES:
        WRITTEN_FILES[dst] = WRITTEN_FILES[src]
        del WRITTEN_FILES[src]
    else:
        f = open(dst, 'w')
        f.write(open(src, 'r').read())
        f.close()

os.rename = chroot_rename


oldMakedirs = os.makedirs

def chroot_makedirs(path, mode=0777):
    if FAUXROOT:
        path = os.path.normpath(path)
        WRITTEN_FILES[path] = CopyOnWriteFile("")
        WRITTEN_FILES[path].fmode = stat.S_IFDIR
    else:
        return oldMakedirs(path, mode)

os.makedirs = chroot_makedirs


oldListdir = os.listdir

def chroot_listdir(path):
    global FAUXROOT

    path = os.path.normpath(path)
    if FAUXROOT and path in WRITTEN_FILES:
        # We don't know if this path is ever used used.
        if WRITTEN_FILES[path].fmode == stat.S_IFDIR:
            return map(os.path.basename, chroot_glob(path + "/*"))
        raise NotImplementedError("chroot_listdir() on written files")

    if (FAUXROOT and os.path.isabs(path) and 
        not path.startswith("/".join(FAUXROOT))):
        path = prepend_root(path)
    content = oldListdir(path)


    return content

os.listdir = chroot_listdir


oldSymlink = os.symlink

def chroot_symlink(src, dst):
    if FAUXROOT:
        dst = os.path.normpath(dst)
        
        WRITTEN_FILES[dst] = CopyOnWriteFile(src)
        WRITTEN_FILES[dst].fmode = stat.S_IFLNK
    else:
        return oldSymlink(src, dst)

os.symlink = chroot_symlink


oldStat = os.stat

def chroot_stat(path):
    path = os.path.normpath(path)
    # If we're in the fake chroot and a fake file was written, get the stat
    # from it, otherwise go to the file system.
    if FAUXROOT and path in WRITTEN_FILES:
        return WRITTEN_FILES[path].stat()
    
    return oldStat(prepend_root(path))

os.stat = chroot_stat


oldStatvfs = os.statvfs

def chroot_statvfs(path):
    path = os.path.normpath(path)
    # If we're in the fake chroot and a fake file was written, get the stat
    # from it, otherwise go to the file system.
    if FAUXROOT and path in WRITTEN_FILES:
        return WRITTEN_FILES[path].statvfs()
    
    return oldStatvfs(prepend_root(path))

os.statvfs = chroot_statvfs


oldWalk = os.walk

def chroot_walk(top, topdown=True, onerror=None):
    if FAUXROOT:
        # XXX only does one level, which is enough for scanning /dev for uuids
        retval = []
        paths = [path for path in glob.glob(os.path.join(top, '*'))]
        dirs = [os.path.basename(path) for path in paths if os.path.isdir(path)]
        files = [os.path.basename(path)
                 for path in paths if not os.path.isdir(path)]
        return [(top, dirs, files)]
    
    return oldWalk(top, topdown, onerror)

os.walk = chroot_walk


oldPathWalk = os.path.walk

def chroot_pathWalk(top, visitor, arg):
    if FAUXROOT:
        for root, dirs, files in os.walk(top):
            visitor(arg, root, dirs + files)
        return

    return oldPathWalk(top, visitor, arg)

os.path.walk = chroot_pathWalk


oldGlob = glob.glob

def chroot_glob(path):
    path = os.path.normpath(path)
    retval = map(_stripFauxRoot, oldGlob(prepend_root(path)))
    fauxMatches = fnmatch.filter(WRITTEN_FILES.keys(), path)
    # note: fnmatch.filter will match paths with subdirectories, which doesn't
    # match with how glob works so we have to prune out any subtrees.  For
    # example, '/dev/cciss/c0d0' will match '/dev/*', which is not what we
    # want.
    retval.extend([match for match in fauxMatches
                   if os.path.dirname(match) == os.path.dirname(path)])

    return list(set(retval))

glob.glob = chroot_glob


def chroot_getUuid(part):
    global PART_UUID_CONFIG

    if part in PART_UUID_CONFIG:
        return PART_UUID_CONFIG[part]

    raise IOError("cannot get UUID for %s" % part)

util.getUuid = chroot_getUuid
util._util.getUuid = chroot_getUuid


def chroot_syncKernelBufferToDisk():
    global SYNC_COUNT

    SYNC_COUNT += 1

util.syncKernelBufferToDisk = chroot_syncKernelBufferToDisk


oldExecCommand = util.execCommand

def chroot_execCommand(command,
                       root='/',
                       ignoreSignals=False,
                       level=None,
                       raiseException=False):
    tokens = shlex.split(command)
    SYSTEM_LOG.append(tokens)

    # Split up the command-line based on the shell boolean operators.  We
    # execute each command ourselves and do the and'ing and or'ing ourselves.
    cmds = isplit(lambda tok: tok in ('&&', '||'), tokens)

    for cmd, oper in cmds:
        # Skip over environment vars (e.g. "NEWRD=1 esxcfg-boot")
        for tok in cmd:
            if "=" not in tok:
                cmdName = tok
                break

        if cmdName in EXEC_FUNCTIONS:
            if root != '/':
                FAUXROOT.append(root)
            
            result = EXEC_FUNCTIONS[cmdName](cmd)
            if type(result) is TupleType:
                output, status = result
            else:
                output = ""
                status = result

            if root != '/':
                FAUXROOT.pop()

            # only return if we have a failure
            if status and raiseException:
                raise util.ExecError(
                    command,
                    "Standard Out:\n%s\n\nStandard Error:\n%s" % (output, ''),
                    status)
            elif status:
                return status, output, ''

        else:
            return oldExecCommand(command,
                                  root=root,
                                  ignoreSignals=ignoreSignals,
                                  raiseException=raiseException
                                  #level=level,
                                 )
    return status, output, ''

util.execCommand = chroot_execCommand
util._util.execCommand = chroot_execCommand


oldExecWithCapture = util.execWithCapture

def chroot_execWithCapture(command, argv,
                           searchPath=False, root='/', stdin=util.STDIN,
                           catchfdList=None, closefd=-1,
                           returnStatus=False,
                           timeoutInSecs=0,
                           raiseException=False):
    global FAUXROOT
    
    SYSTEM_LOG.append(argv)

    if catchfdList is None:
        catchfdList = [util.STDOUT]

    if command in EXEC_FUNCTIONS:
        if root != '/':
            FAUXROOT.append(root)
        
        result = EXEC_FUNCTIONS[command](argv)
        if type(result) is TupleType:
            output, status = result
        else:
            output = ""
            status = result

        if root != '/':
            FAUXROOT.pop()

        if status and raiseException:
            raise util.ExecError(
                command,
                "Standard Out:\n%s\n\nStandard Error:\n%s" % (output, ''),
                status)
        
        if returnStatus:
            return (output, status)
        else:
            return output
    else:
        return oldExecWithCapture(command, argv,
                                  searchPath=searchPath,
                                  root=root,
                                  stdin=stdin,
                                  catchfdList=catchfdList,
                                  closefd=closefd,
                                  returnStatus=returnStatus,
                                  timeoutInSecs=timeoutInSecs,
                                  raiseException=raiseException)

util.execWithCapture = chroot_execWithCapture
util._util.execWithCapture = chroot_execWithCapture

oldCopy = shutil.copy

def chroot_copy(src, dst):
    global FAUXROOT, WRITTEN_FILES

    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if FAUXROOT:
        contents = open(src).read()
        WRITTEN_FILES[dst] = CopyOnWriteFile(contents)
        return
    
    return oldCopy(prepend_root(src), prepend_root(dst))

shutil.copy = chroot_copy


oldCopy2 = shutil.copy2

def chroot_copy2(src, dst):
    global FAUXROOT, WRITTEN_FILES

    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if FAUXROOT:
        contents = open(src).read()
        WRITTEN_FILES[dst] = CopyOnWriteFile(contents)
        return
    
    return oldCopy(prepend_root(src), prepend_root(dst))

shutil.copy2 = chroot_copy2


oldCopyTree = shutil.copytree

def chroot_copytree(src, dst, symlinks=False):
    # XXX implement when needed
    if FAUXROOT:
        os.makedirs(dst)
        return
    
    return oldCopyTree(src, dst, symlinks)

shutil.copytree = chroot_copytree


oldCopyStat = shutil.copystat

def chroot_copystat(src, dst):
    # XXX implement when needed
    if FAUXROOT:
        return
    
    return oldCopyStat(src, dst)

shutil.copystat = chroot_copystat


oldSleep = time.sleep

def logged_sleep(secs):
    SLEEP_LOG.append(secs)
    return

time.sleep = logged_sleep

oldLocaltime = time.localtime

_timeDelta = None
def setTimeDelta(timeDelta):
    global _timeDelta
    _timeDelta = timeDelta

def chroot_localtime(*args):
    if not _timeDelta or args:
        return oldLocaltime(*args)
    trueTime = datetime.datetime(*oldLocaltime()[:6])
    adjustedTime = trueTime + _timeDelta
    return adjustedTime.timetuple()

time.localtime = chroot_localtime


oldUrlOpen = urllib2.urlopen

def chroot_urlopen(urlRequest):
    location = urlRequest.get_full_url()
    fauxloc = fauxlocations.get(location)
    if fauxloc:
        return fauxloc

    _protocol, _host, fullpath, _unused, _unused, _unused = \
        urlparse.urlparse(location)

    return open(os.path.join("/mnt/source", fullpath.lstrip('/')))

urllib2.urlopen = chroot_urlopen


oldParseFile = libxml2.parseFile

def chroot_parseFile(path):
    try:
        xmlFile = open(path)
        contents = xmlFile.read()

        return libxml2.parseDoc(contents)
    except IOError, e:
        raise libxml2.parserError(str(e))

libxml2.parseFile = chroot_parseFile

SIMULATION_SLOWNESS = 0
def longRunningFunction(multiplier, name, times=1):
    duration = SIMULATION_SLOWNESS*multiplier
    import task_progress
    task_progress.taskStarted(name)
    for i in range(times):
        task_progress.taskProgress(name)
        #print 'stalling on', name, 'for', duration
        oldSleep(duration)
    task_progress.taskFinish(name)

oldGetuid = os.getuid

def chroot_getuid():
    if FAUXROOT:
        return 0

    return oldGetuid()

os.getuid = chroot_getuid


oldMkdtemp = tempfile.mkdtemp

def chroot_mkdtemp(suffix='', prefix='', dir='/tmp'):
    if FAUXROOT:
        dirName = (
            prefix + ''.join([
                    random.choice(string.letters + string.digits)
                    for x in range(6)]) + suffix)
        path = os.path.normpath(os.path.join(dir, dirName))
        WRITTEN_FILES[path] = CopyOnWriteFile("")
        WRITTEN_FILES[path].fmode = stat.S_IFDIR
        return path
    else:
        return oldMkdtemp(prefix=prefix, dir=dir)

tempfile.mkdtemp = chroot_mkdtemp

oldRmtree = shutil.rmtree

def chroot_rmtree(path):
    global FAUXROOT
    
    path = os.path.normpath(path)
    if FAUXROOT:
        for fileName in WRITTEN_FILES.keys():
            if fileName.startswith(path):
                print fileName
                DELETED_FILES[(time.time(), fileName)] = \
                    WRITTEN_FILES[fileName]
                del WRITTEN_FILES[fileName]
            pass

    else:
        return oldRmtree(prepend_root(path))

shutil.rmtree = chroot_rmtree

def resetLogs():
    global SLEEP_LOG, SYSTEM_LOG, WRITTEN_FILES, UMOUNTED_FILES, DELETED_FILES
    global MASKED_FILES, EXCLUDE_PATHS, PROMPT_LOG, EMPTY_FILES

    SLEEP_LOG = []
    SYSTEM_LOG = []
    WRITTEN_FILES = {}
    UMOUNTED_FILES = {}
    DELETED_FILES = {}
    MASKED_FILES = {}
    EXCLUDE_PATHS = []
    PROMPT_LOG = []
    EMPTY_FILES = []
  
if __name__ == "__main__": #pragma: no cover
   import doctest
   os.chdir(os.path.join(os.path.curdir, os.path.dirname(__file__)))
   doctest.testmod()
