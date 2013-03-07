'''Support module for executing doctest-based end-to-end installer tests in
caged weasel.

To use this module for scripted install testing, write the kickstart file at
the top of the file and the doctest prompts at the end, like so:

  autopart --firstdisk
  clearpart --firstdisk

  ...


  >>> import docage
  >>> docage.run()

The "docage.run()" call will take care of setting up the cage and running the
installer.  You can add additional prompts to verify expected output.
'''

import os
import sys
import stat
import string
import pprint
import inspect
import thread, threading

THIS_DIR = os.path.dirname(__file__)
TEST_DIR = THIS_DIR

while not os.path.exists(os.path.join(TEST_DIR, "good-config.1")):
    TEST_DIR = os.path.join(TEST_DIR, os.pardir)

sys.path += [
    TEST_DIR,
    os.path.join(TEST_DIR, os.path.pardir),
    os.path.join(TEST_DIR, os.path.pardir, "scriptedinstall"),
    ]

sys.path.insert(0, os.path.join(TEST_DIR, 'faux'))
import rpm
import vmkctl
import parted
import fauxroot

import textui.textengine

# For pciidlib
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))

DEFAULT_CONFIG_NAME = "good-config.1"

WEASEL_THREAD = None
STEPPER = None
LAST_OUTPUT = ""
NEXT_INPUT = None

class Stepper:
    """Class used to stop/start the main weasel thread as it waits for input."""
    
    STATE_INIT, STATE_BLOCKED, STATE_RUNNING, STATE_DEAD = range(4)
    
    def __init__(self):
        self.cond = threading.Condition()
        self.state = self.STATE_INIT

    def block(self):
        """Called by the weasel thread to block and wait to run again."""
        
        self.cond.acquire()
        self.state = self.STATE_BLOCKED
        self.cond.notify()
        attempts = 0
        while self.state == self.STATE_BLOCKED:
            self.cond.wait(1.0)
            attempts += 1
            if self.state == self.STATE_BLOCKED:
                oldStderr.write("weasel still blocked waiting for input...\n")
                if attempts > 3:
                    thread.exit()
        self.cond.release()

    def waitForBlock(self):
        """Called by the controlling thread to wait for the weasel thread to
        block."""
        
        self.cond.acquire()
        while self.state == self.STATE_RUNNING:
            self.cond.wait()
        self.cond.release()

        if self.state == self.STATE_DEAD:
            raise Exception("weasel thread died")

    def unblock(self):
        """Called by the controlling thread to let the main weasel thread run
        again."""
        
        self.cond.acquire()
        while self.state == self.STATE_INIT:
            self.cond.wait()
        self.state = self.STATE_RUNNING
        self.cond.notify()
        self.cond.release()

    def died(self):
        """Called by the weasel thread when it has exited."""
        
        self.cond.acquire()
        self.state = self.STATE_DEAD
        self.cond.notify()
        self.cond.release()

def openInFauxRoot(path, mode="r"):
    return open(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME, path.lstrip('/')),
                mode)
    
def setup():
    '''Setup the cage, but do not enable the faux chroot.'''

    global STEPPER, LAST_OUTPUT, NEXT_INPUT
    global oldStdout, newStdout, oldStderr, newStderr
    
    fauxroot.resetLogs()
    rpm.reset()
    vmkctl.reset()

    sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
    import fauxconfig
    sys.path.pop()

    reload(fauxconfig)

    # XXX Need to reload modules with global data.
    import userchoices
    reload(userchoices)

    import remote_files
    remote_files.__cacher = None
    remote_files.__nfsMounter = None
    remote_files.NFSMounter._nfsUp = False

    import customdrivers
    reload(customdrivers)

    import media
    reload(media)

    import scui
    reload(scui)

    import networking
    reload(networking.networking_base)

    import boot_cmdline
    reload(boot_cmdline)

    import packages
    packages.__transactionSet = None
    
    textui.textengine._cons_input = _auto_input
    textui.textengine._password_cons_input = _auto_input
    textui.textengine._cons_output_oob = lambda x: x
    textui.textengine._cons_output = _auto_output

    STEPPER = Stepper()
    LAST_OUTPUT = ""
    NEXT_INPUT = None
    
    # Find the name of the doctest file that is being run.  XXX Evil
    st = inspect.stack()

    oldStdout = sys.stdout
    newStdout = fauxroot.CopyOnWriteFile()
    oldStderr = sys.stderr
    newStderr = fauxroot.CopyOnWriteFile()
    
    doctestName = None
    for frame in st:
        if frame[1].endswith("doctest.py"):
            doctestName = frame[0].f_locals['test'].filename
            break

    if doctestName:
        testContents = open(doctestName).read()

        # Get the kickstart commands from the top of the file.
        ksEnd = testContents.find(">>>")
        ksFile = testContents[:ksEnd]

        fauxroot.WRITTEN_FILES["/ks.cfg"] = fauxroot.CopyOnWriteFile(ksFile)

oldStdout = None
oldStderr = None
newStdout = None
newStderr = None
exitCode = None

def waitAndFeed(data):
    """Wait for output from weasel and then feed it another input."""
    
    global STEPPER, LAST_OUTPUT, NEXT_INPUT

    sys.stdout = newStdout
    STEPPER.unblock()
    STEPPER.waitForBlock()
    sys.stdout = oldStdout

    retval = LAST_OUTPUT
    LAST_OUTPUT = ""
    NEXT_INPUT = data

    return retval

def wait():
    """Wait for the weasel thread to exit."""
    
    global STEPPER, LAST_OUTPUT

    sys.stdout = newStdout
    STEPPER.unblock()
    sys.stdout = oldStdout

    retval = LAST_OUTPUT
    LAST_OUTPUT = ""

    WEASEL_THREAD.join(3)

    return retval

def _auto_input(prompt):
    """Fake raw_input that returns inputs fed in by waitAndFeed."""
    
    global STEPPER, LAST_OUTPUT
    
    LAST_OUTPUT += prompt

    STEPPER.block()
    
    retval = NEXT_INPUT

    return retval

def _auto_output(*args):
    """Fake output function that saves output to be read by waitAndFeed."""
    
    global LAST_OUTPUT

    outstr = "%s" % args
    if outstr[-1] != '\n':
        outstr += '\n'

    LAST_OUTPUT += outstr

def doitInTheBackground(args=None, mainFunc=None):
    """Runs the weasel thread in the background so doctest can run in the
    foreground and feed it inputs."""
    
    global WEASEL_THREAD
    
    def _wrapper():
        STEPPER.block()
        try:
            doit(args, mainFunc)
        finally:
            STEPPER.died()
        
    WEASEL_THREAD = threading.Thread(target=_wrapper)
    WEASEL_THREAD.start()

def doit(args=None, mainFunc=None):
    '''Actually run the installer in the faux chroot environment.'''
    global exitCode
    
    if args is None:
        args = ["-s", "/ks.cfg"]
        
    try:
        try:
            try:
                fauxroot.FAUXROOT = [
                os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME)]
                
                import log
                log.log.removeHandler(log.stdoutHandler)
                log.log.removeHandler(log.fileHandler)

                sys.stdout = newStdout
                sys.stderr = newStderr

                log.addStdoutHandler()
                log.addLogFileHandler()
                
                import devices
                if '_the_only_instance' in devices.DiskSet.__dict__:
                    devices.DiskSet._the_only_instance = None

                if mainFunc is None:
                    import weasel
                    mainFunc = weasel.main

                args = ["weasel.py"] + args
                exitCode = mainFunc(args)
            except Exception:
                sys.excepthook(*sys.exc_info())
                exitCode = 1
        except SystemExit, e:
            exitCode = e.code
    finally:
        sys.stdout = oldStdout
        sys.stderr = oldStderr
        fauxroot.FAUXROOT = None

def run():
    '''Function that does the setup and doit functions in one step.'''
    setup()
    doit()

def printSystemLog():
    '''Print the log of executed commands for verification purposes.'''
    for cmd in fauxroot.SYSTEM_LOG:
        print cmd

def printPromptLog():
    '''Print the log of prompts for verification purposes.'''
    for prompt in fauxroot.PROMPT_LOG:
        print prompt

def printPartitions():
    '''Print the partition layout for verification purposes.'''
    for path, dev in parted.PARTED_DEV_CONFIG.items():
        print "%s PARTITIONS:" % path
        pprint.pprint(dev.committedPartitions)

FMODE_MAP = {
    stat.S_IFBLK : "b",
    stat.S_IFLNK : "l",
    stat.S_IFREG : "f",
    stat.S_IFDIR : "d",
    }

def _printFileDict(filesToPrint, include, desc):
    for path in sorted(filesToPrint):
        contents = filesToPrint[path]
        
        if include and path not in include:
            continue
        
        print "%s (%s %s %o)" % (
            path, desc, FMODE_MAP[contents.fmode], contents.mode)
        content = contents.getvalue().replace('\033', '\\033')
        nonPrintableChars = (char for char in content
                             if char not in string.printable)
        for char in nonPrintableChars:
            # hit one.  that means the content had non-printables
            content = "<Non-Printable File>" #perhaps repr..?
            break
        
        if not content:
            continue

        # XXX doctest does not work with tabs.
        content = content.replace('\t', '        ')
        print "  " + (content.replace('\n', '\n  '))
        
def printFiles(include=[]):
    '''Print the written files for verification purposes.'''
    _printFileDict(fauxroot.WRITTEN_FILES, include, "regular")
    _printFileDict(fauxroot.UMOUNTED_FILES, include, "unmounted")
