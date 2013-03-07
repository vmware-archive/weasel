
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

import select
import signal
import types
import struct
import os
import os.path
import glob
import re
import sys
import stat
import errno
from xml.dom.minidom import Node

try:
    from libutil import getUuid
except ImportError:
    pass
  
import logging
from log import log

from subprocess import PIPE
from subprocess import Popen

# These are in 1024K blocks
SIZE_MB = (1024.0)
SIZE_GB = (SIZE_MB * 1000)
SIZE_TB = (SIZE_GB * 1000)

STDIN = 0
STDOUT = 1
STDERR = 2

UUID_MOUNT_PATH = "/mnt/by-uuid"

class ExecError(Exception):
    def __init__(self, command, output, status):
        Exception.__init__(self, "Command '%s' exited with status %d" % (
                command, status))

        self.command = command
        self.output = output
        self.status = status

    def getDetails(self):
        retval = "Command '%s' exited with status %d.\n" % (
            self.command, self.status)
        # Only add command output if there's some non-whitespace text.
        if self.output.strip():
            indentedOutput = self.output.replace('\n', '\n  ')
            retval += "Output:\n  %s" % indentedOutput
        return retval

def formatValue(value):
    if value >= SIZE_TB:
        return "%.2f TB" % (value / SIZE_TB)
    elif value >= SIZE_GB:
        return "%.2f GB" % (value / SIZE_GB)
    elif value >= SIZE_MB:
        return "%d MB" % (value / SIZE_MB)
    else:
        return "0 MB"

def valueInMegabytesFromUnit(value, unit):
    assert unit in ["TB", "GB", "MB"]
    if unit == "TB":
        return value * SIZE_TB / SIZE_MB
    elif unit == "GB":
        return value * SIZE_GB / SIZE_MB
    else:
        return value

def formatValueInMegabytes(value):
    return "%d MB" % (value / SIZE_MB)

def getValueInSectorsFromMegabyes(value, sectorSize=512):
    return (SIZE_MB * value / sectorSize) * SIZE_MB

def getValueInMegabytesFromSectors(value, sectorSize=512):
    return (value / (SIZE_MB / sectorSize)) / SIZE_MB

def getValueInKilobytesFromSectors(value, sectorSize=512):
    return (value / (SIZE_MB / sectorSize))

def truncateString(fullString, length):
    '''Truncate a string to a desired length if it's too long.

       >>> myString = 'myreallylongstring'
       >>> truncateString(myString, 5)
       myrea...
    '''
    if len(fullString) > length and length >= 3:
        return fullString[:length - 3] + '...'
    return fullString

def getfd(filespec, readOnly=False):
    if type(filespec) == types.IntType:
        return filespec
    if filespec == None:
        filespec = "/dev/null"

    flags = os.O_RDWR | os.O_CREAT
    if (readOnly):
        flags = os.O_RDONLY
    return os.open(filespec, flags)



class FunctionList(list):
   def __init__(self):
      list.__init__(self)

   def append(self, func, *args, **kwargs):
      list.append(self, (func, args, kwargs))

   def run(self):
      for (func, args, kwargs) in self:
         func(*args, **kwargs)

def chroot(root):
    os.chroot(root)
    os.chdir('/')


def execCommand(command, root='/', ignoreSignals=False, level=logging.INFO,
                raiseException=False):
   '''execCommand(command, root='/', ignoreSignals=False, level=logging.INFO)
   command: string - The command you wish to execute
   root: string - The environment root (will chroot to this path before execution)
   ignoreSignals: bool - Should we ignore SIGTSTP and SIGINT
   level: logging level - The logging level that should be used
   raiseException: bool - Raise an ExecError exception if the commands exit code
     is non-zero.
   '''

   def ignoreStopAndInterruptSignals():
      signal.signal(signal.SIGTSTP, signal.SIG_IGN)
      signal.signal(signal.SIGINT, signal.SIG_IGN)

   env = {}
   commandEnvironmentSetupFunctions = FunctionList()

   env['PATH'] = '/sbin:/bin:/usr/sbin:/usr/bin:/usr/bin/vmware'

   if root and root != '/':
      commandEnvironmentSetupFunctions.append(chroot, root)

   if ignoreSignals:
      commandEnvironmentSetupFunctions.append(ignoreStopAndInterruptSignals)

   log.debug('Executing: %s' % command)
   process = Popen(command, shell=True, env=env,
                   preexec_fn=commandEnvironmentSetupFunctions.run, stdout=PIPE,
                   stderr = PIPE, close_fds = True)
   stdout = None; stderr = None

   try:
      (stdout, stderr) = process.communicate()
   except OSError, (errno, msg):
      log.error("%s failed to execute: (%d): %s\n" % (command, errno, msg))

   if stderr:
      log.error("stderr: %s\n" % (stderr,))
   else:
      log.log(level, stdout)

   if process.returncode and raiseException:
       raise ExecError(
           command,
           "Standard Out:\n%s\n\nStandard Error:\n%s" % (stdout, stderr),
           process.returncode)

   return (process.returncode, stdout, stderr)



def execWithRedirect(command, argv, stdin=STDIN, stdout=STDOUT, stderr=STDERR,
                     searchPath=False, root='/', ignoreTermSigs=False,
                     raiseException=True):
    '''This is borrowed from Anaconda
    '''

    stdin = getfd(stdin)
    if stdout == stderr:
        stdout = getfd(stdout)
        stderr = stdout
    else:
        stdout = getfd(stdout)
        stderr = getfd(stderr)

    if not searchPath and not os.access (root + command, os.X_OK):
        raise RuntimeError, command + " can not be run"

    childpid = os.fork()
    if not childpid:
        if root and root != '/':
            chroot(root)

        if ignoreTermSigs:
            signal.signal(signal.SIGTSTP, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)

        if type(stdin) == type("a"):
            stdin = os.open(stdin, os.O_RDONLY)
        if type(stdout) == type("a"):
            stdout = os.open(stdout, os.O_RDWR)
        if type(stderr) == type("a"):
            stderr = os.open(stderr, os.O_RDWR)

        if stdin != 0:
            os.dup2(stdin, 0)
            os.close(stdin)
        if stdout != 1:
            os.dup2(stdout, 1)
            if stdout != stderr:
                os.close(stdout)
        if stderr != 2:
            os.dup2(stderr, 2)
            os.close(stderr)

        try:
            if searchPath:
                os.execvp(command, argv)
            else:
                os.execv(command, argv)
        except OSError:
            # let the caller deal with the exit code of 1.
            pass

        sys.exit(1)

    status = -1
    try:
        (_pid, status) = os.waitpid(childpid, 0)
    except OSError, (errno, msg):
        print __name__, "waitpid:", msg

    if status and raiseException:
        raise ExecError(" ".join(argv), '', status)

    return status


def execWithCapture(command, argv, searchPath=False, root='/', stdin=STDIN,
                    catchfdList=None, closefd=-1, returnStatus=False,
                    timeoutInSecs=0, raiseException=False):
    '''This is borrowed from Anaconda
    '''

    if catchfdList is None:
        catchfdList = [STDOUT]

    if not os.access (root + command, os.X_OK):
        raise RuntimeError, command + " can not be run"

    (read, write) = os.pipe()

    childpid = os.fork()
    if not childpid:
        if root and root != '/':
            chroot(root)
        
        # Make the child the new group leader so we can killpg it on a timeout
        # and it'll take down the shell and all its children.
        os.setsid()

        for catchfd in catchfdList:
            os.dup2(write, catchfd)
        os.close(write)
        os.close(read)

        if closefd != -1:
            os.close(closefd)

        if stdin:
            os.dup2(stdin, STDIN)
            os.close(stdin)

        if searchPath:
            os.execvp(command, argv)
        else:
            os.execv(command, argv)

        sys.exit(1)

    os.close(write)
    
    def timeoutHandler(_signum, _frame):
        try:
            os.killpg(childpid, signal.SIGKILL) # SIGKILL to harsh?
        except:
            log.exception("timeoutHandler: kill")
        return

    if timeoutInSecs:
        oldHandler = signal.signal(signal.SIGALRM, timeoutHandler)
        signal.alarm(timeoutInSecs)

    rc = ""
    s = "1"
    while (s):
        try:
            select.select([read], [], [])
        except select.error, (err, msg):
            if err == errno.EINTR:
                # We'll get an EINTR on timeout...
                continue
            log.error("select -- %s" % msg)
            raise
        s = os.read(read, 1000)
        rc = rc + s
    os.close(read)

    status = -1
    try:
        (_pid, status) = os.waitpid(childpid, 0)
        if timeoutInSecs:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, oldHandler)
    except OSError, (err, msg):
        print __name__, "waitpid:", msg

    if status and raiseException:
        raise ExecError(" ".join(argv), rc, status)

    if returnStatus:
        return (rc, status)
    else:
        return rc

def execWithRedirectAndCapture(command, argv, catchfdList=(STDOUT,), root='/',
                               redirect=None, raiseException=False):
    '''This is borrowed from Anaconda
    '''

    (output, status) = execWithCapture(command, argv,
                                       catchfdList=catchfdList,
                                       root=root, returnStatus=True,
                                       raiseException=raiseException)

    if redirect:
        fd = os.open(redirect, os.O_RDWR)
        os.write(fd, output)
        os.close(fd)

    return (output, status)

def execWithLog(command, argv, root='/', level=logging.INFO,
                timeoutInSecs=0, raiseException=False):
    '''Execute the given command and log its output.'''

    cmdline = " ".join(argv)
    log.debug("executing: %s" % cmdline)
    (output, status) = execWithCapture(command, argv,
                                       root=root,
                                       returnStatus=True,
                                       catchfdList=[STDOUT,STDERR],
                                       timeoutInSecs=timeoutInSecs,
                                       raiseException=False)

    log.debug("command exited with status %d" % status)

    if status:
        log.error(output)
        if raiseException:
            raise ExecError(cmdline, output, status)
    else:
        log.log(level, output)

    return status


def GetWeaselXMLFilePath( filename ):
    # for now all the .xml files can be found in the local directory
    dirPath = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(dirPath, "..", filename))


def XMLTagLen(tags):
    '''Count the number of tags of a given TagName in a particular element.

       This should really be povided by minidom with __len__().
    '''
    count = 0
    for x in tags:
        count += 1
    return count


def XMLGetText(node):
    data = ""
    for subTag in node.childNodes:
        if subTag.nodeType == Node.TEXT_NODE:
            data = data + subTag.data
    return data

def XMLGetTextInUniqueElement(dom, tagName):
    ''' returns the text found inside the tag.
    dom - can be a true DOM or it can be a subnode, so long as there
    is only one element with the specified tagName underneath it
    '''
    elements = dom.getElementsByTagName(tagName)
    if XMLTagLen(elements) != 1:
        raise ValueError, "Number of elements was not equal to one."

    return XMLGetText(elements[0])

def XMLGetTextInFirstElement(dom, tagName):
    ''' returns the text found inside the tag.
    dom - can be a true DOM or it can be a subnode.
    '''
    elements = dom.getElementsByTagName(tagName)
    return XMLGetText(elements[0])

def uuidToDevicePath(uuid):
    '''Search through all the files and subdirectories in /dev for a block
    device with a matching UUID.'''
    
    # XXX switch to using findfs UUID=
    for root, _dirs, files in os.walk("/dev"):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                st = os.stat(path)
                if not stat.S_ISBLK(st.st_mode):
                    # Skip over non-block devices.
                    continue
            
                if uuid == getUuid(path):
                    return path
            except IOError:
                # getUuid throws IOError for non-disks.
                # log.exception("cannot get uuid for %s" % path)
                pass
    
    log.error("cannot find device with UUID: %s" % uuid)

    return None

def mount(device, mountPoint, readOnly=False, bindMount=False, loopMount=False, isUUID=False, options=None, fsTypeName=None):
    if not os.path.exists(mountPoint):
        os.makedirs(mountPoint)

    args = ["/usr/bin/mount"]

    if device.startswith("UUID="):
        # Be nice and accept a device name in the UUID=XXXXX format.
        isUUID = True
        device = device.replace("UUID=", '', 1)

    if readOnly:
        args.append("-r")

    if bindMount:
        args.append("--bind")

    allOptions = []
    if loopMount:
        allOptions += ["loop"]
        
    if options:
        allOptions += options

    if allOptions:
        args.extend(["-o", ",".join(allOptions)])

    if fsTypeName:
        args.extend(["-t", fsTypeName])

    if isUUID:
        uuid = device
        device = uuidToDevicePath(uuid)
        if not device:
            return 1

    args += [device, mountPoint]

    status = execWithLog(args[0], args, level=logging.DEBUG)

    return status

def umount(mountPoint):
    args = ["/usr/bin/umount", mountPoint]

    status = execWithLog(args[0], args, level=logging.DEBUG)

    return status

def mountByUuid(uuid):
    retval = os.path.join(UUID_MOUNT_PATH, uuid)
    if not os.path.exists(retval):
        os.makedirs(retval)
    if mount(uuid, retval, isUUID=True):
        log.error("cannot mount partition with UUID: %s" % uuid)
        os.rmdir(retval)
        return ""

    return retval

def eject(device):
    args = ["/usr/bin/eject", device]

    status = execWithLog(args[0], args)
    assert status == 0 # TODO: handle errors

    return status

def uuidStringToBits(uuid):
    m = re.match(r'(\w{8})-(\w{4})-(\w{4})-(\w{4})-(\w{12})', uuid)
    assert m, "invalid UUID string -- %s" % uuid
    retval = ''
    for group in m.groups():
        while group:
            hexByte, rest = (group[:2], group[2:])
            retval += struct.pack("B", int(hexByte, 16))
            group = rest
    return retval

def uuidBitsToString(uuidBits):
    retval = []
    # XXX I'm sort of abusing unpack to break up the bits into a list.
    for subBytes in struct.unpack("4s2s2s2s6s", uuidBits):
        retval.append("".join(
            ["%02x" % struct.unpack("B", byte)[0] for byte in subBytes]))
    return "-".join(retval)

def splitInts(stringWithNumbers):
    '''Break up a string with numbers so it can be sorted in natural order.

    >>> splitInts("foo")
    ["foo"]
    >>> splitInts("foo 123")
    ["foo", 123]
    '''

    def attemptIntConversion(obj):
        try:
            return int(obj)
        except ValueError:
            return obj

    retval = []
    for val in re.split(r'(\d+)', stringWithNumbers):
        if not val:
            # Ignore empty strings
            continue

        retval.append(attemptIntConversion(val))

    return retval

def writeConfFile( fname, content ):
    dirname = os.path.dirname( fname )
    try:
        os.makedirs(dirname)
    except OSError, ex:
        if ex.errno != errno.EEXIST:
            raise
    fp = open( fname, 'w' )
    fp.write( content )
    fp.close()

def rawInputWithTimeout(prompt, timeoutInSecs):
    class TimeoutException(Exception):
        pass
    
    def timeoutHandler(_signum, _frame):
        raise TimeoutException()
    
    oldHandler = signal.signal(signal.SIGALRM, timeoutHandler)
    signal.alarm(timeoutInSecs)

    try:
        retval = raw_input(prompt)
    except TimeoutException:
        retval = None
    signal.alarm(0)
    signal.signal(signal.SIGALRM, oldHandler)

    return retval

def rawInputCountdown(prompt, totalTimeout):
    try:
        for seconds in range(totalTimeout):
            retval = rawInputWithTimeout(prompt % (totalTimeout - seconds), 1)
            if retval is not None:
                return retval
    finally:
        sys.stdout.write("\n")
    
    return None

if __name__ == "__main__":
    print "OK"
    args = ["/bin/echo", "foo"]
    x = execWithCapture(args[0], args)
    print "x = %s" % (x,)

