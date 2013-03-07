
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


# import pychecker.checker # XXX Doesn't play with nosetests, stdout is lost

import re
import os.path
import sys
import glob
import doctest

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
import util

sys.path.append(os.path.join(TEST_DIR, "scriptedinstall", "files"))
sys.path.insert(0, os.path.join(TEST_DIR, 'faux'))
import fauxroot

# For pciidlib
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))

DEFAULT_CONFIG_NAME = "good-config.1"
sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

import os
sys.path.append(os.path.join(TEST_DIR, os.path.pardir, "scriptedinstall"))
import preparser
from preparser import ScriptedInstallPreparser
from scriptedinstallutil import Result
from scriptwriter import hostAction as writeAction

import devices
import userchoices

# These imports are not used in this file, but they are used in the verify
# sections of the '.bs' files.
import users
import fsset
from script import Script

BASE_SCRIPT_PATH = './scriptedinstall/files/'
#BASE_SCRIPT_PATH = './scriptedinstall/testbox/'

DISABLED_TESTS = [
    'complex.preparse.firewall.invalidService.bs',
    ]

def scriptChroot(argv):
    assert argv[1] == '/'
    assert argv[2] == '/tmp/ks-script'
    
    return 0

def preScript(argv):
    assert argv[1] == '/tmp/ks-script'
    assert len(argv) == 2
    
    return 0

def badPreScript(argv):
    assert argv[1] == '/tmp/ks-script'
    assert len(argv) == 2
    
    return 1

def testPreparse():
    # Generates testcases based on the contents of the BASE_SCRIPT_PATH
    # directory.

    # Each entry in BASE_SCRIPT_PATH is matched against a known file name
    # prefix and then routed to the appropriate validation function
    
    try:
        files = os.listdir(BASE_SCRIPT_PATH)
    except OSError, msg:
        print "Error grepping for files"
        return

    files = map((lambda x: BASE_SCRIPT_PATH + x), files)

    files.sort()
    for fileName in files:
        if os.path.basename(fileName) in DISABLED_TESTS:
            continue
        
        if not os.path.isfile(fileName):
            pass
        elif fileName.find('simple.preparse') > -1:
            yield validateComplexValidate, fileName
            pass
        elif fileName.find('complex.preparse') > -1:
            yield validateComplexValidate, fileName
        elif fileName.find('complex.validate') > -1:
            yield validateComplexValidate, fileName
        else:
            pass

def validateComplexValidate(fileName):
    (result, errors, warnings, verify) = \
             buildExpectedResultSet(fileName)
    validateScriptedInstallValidate(fileName, result, errors, warnings, verify)

    if False and not errors:
        # XXX The following should check the generated ks.cfg file, but it does
        # not work quite right.  Just checking the results is not enough and
        # any default settings will be filled so there won't be any warnings
        # about the defaults being used (same for deprecated commands, unknown
        # commands, and so on).  Checking userchoices does not quite work
        # because we don't have __str__ methods on all the objects and some
        # unrelated quirks cause other problems (unicode and shlex not getting
        # along).
        
        savedChoices = re.sub(r'0x\w+', 'XXX', userchoices.dumpToString())
        reload(userchoices)

        try:
            fauxroot.FAUXROOT = [DEFAULT_CONFIG_NAME]
            # XXX Need to force a reprobe since the disk config might change.
            devices.DiskSet(forceReprobe=True)
            si = ScriptedInstallPreparser("/mnt/sysimage/root/ks.cfg")
            (result, errors, warnings) = si.parseAndValidate()
            
            newChoices = re.sub(r'0x\w+', 'XXX', userchoices.dumpToString())

            import difflib
            for line in difflib.unified_diff(
                savedChoices.split('\n'), newChoices.split('\n')):
                print line
            assert savedChoices == newChoices
        finally:
            fauxroot.FAUXROOT = None

    # XXX Need to be nice to other tests, do another reload...
    reload(userchoices)


def testSCUI():
    for fileName in glob.glob(os.path.join(BASE_SCRIPT_PATH, 'scui.*.bs')):
        yield scuiValidate, fileName

def scuiValidate(fileName):
    failures, _total = doctest.testfile(fileName,
                                        report=True,
                                        optionflags=(doctest.REPORT_UDIFF|
                                                     doctest.ELLIPSIS))
    assert failures == 0

#
#   method parses the file passed as an argument to collect warnings 
#   and errors expected to be generated during the parse. Their 
#   values are later compared to the actual values returned by preparse.
#   In addition, inside the verify section you can write python expressions
#   that should evaluate to True after the test is executed.  The verifications
#   are useful for checking that values are actually making it all the way
#   from the kickstart file to the userchoices module.  The 'chroot' command
#   allows you to set the mock configuration to use.  The 'exec' command binds
#   a mock executable name to a builtin function that emulates the executable.
#
#   An example of the format of the scripted install file is as follows:
#      #
#      #     start_warnings
#      #     warning1
#      #     warning2
#      #     end_warnings
#      #     start_errors
#      #     error1
#      #     error2
#      #     end_errors
#      #     start_verify
#      #     checkexpr1
#      #     checkexpr2
#      #     end_verify
#      #     chroot <chroot-config>
#      #     exec <path> <function-name>
#      #
#      ... contents of scripted install file
#
#   The order of the warnings and errors are preserved and should be 
#   listed in the order by which they were encountered in the scripted 
#   install script.
#
#
def buildExpectedResultSet(fileName):
    warnings = []
    errors = []
    verify = []
    readWarnings = readErrors = readVerify = False
    rootPath = None

    if fauxroot.FAUXROOT:
        fauxroot.FAUXROOT = None
        reload(preparser)
    
    configToLoad = DEFAULT_CONFIG_NAME
    fauxroot.resetLogs()
    sys.path.append(os.path.join(os.path.dirname(__file__), configToLoad))
    reload(fauxconfig)
    sys.path.pop()
    
    fauxroot.EXEC_FUNCTIONS['chroot'] = scriptChroot
    fauxroot.EXEC_FUNCTIONS['/bin/bash'] = preScript
    
    f = open(fileName, 'r')
    lines = f.readlines()
    f.close()

    lineNum = 0
    try:
        line = lines.pop(0)
        while True:
            print "line: " + str(lineNum)
            if line.find("start_warnings") > -1:
                print "Collecting Warnings"
                readWarnings = True
                readErrors = False
                readVerify = False
                line = lines.pop(0)
                lineNum +=1
                print "Inspecting line" + str(lineNum)
            elif line.find("end_warnings") > -1:
                readWarnings = False
                print "No More Warnings"
            elif line.find("start_errors") > -1:
                print "Collecting Errors"
                readErrors = True
                readWarnings = False
                readVerify = False
                line = lines.pop(0)
                lineNum +=1
            elif line.find("end_errors") > -1:
                readErrors = False
                print "No More Errors"
            elif line.find("start_verify") > -1:
                print "Collecting Verification"
                readVerify = True
                readWarnings = False
                readErrors = False
                line = lines.pop(0)
                lineNum +=1
            elif line.find("end_verify") > -1:
                readVerify = False
                print "No More Verification"
            elif line.find("exec") > -1:
                # Capture the command to be overridden and the python function
                # name that imitates the cmd: 'exec <cmd-path> <python-func>'.
                # For example: # exec /bin/sh badPreScript
                m = re.match(r'^#\s+exec\s+([^\s]+)\s+(.+)', line)
                if m:
                    fauxroot.EXEC_FUNCTIONS[m.group(1)] = globals()[m.group(2)]
            else:
                m = re.match(r'^#\s+chroot\s+(.+)', line)
                if m:
                    rootPath = m.group(1)

            if not line.startswith('#'):
                pass
            elif readWarnings:
                line = line[1::] # remove leading comment token
                line = line.strip() #remove leading and trailing whitespace
                warnings.append(line)
                print "Warning Collected: " + line
            elif readErrors:
                line = line[1::] 
                line = line.strip()
                errors.append(line)
                print "Error Collected: " + line
            elif readVerify:
                line = line[1::] 
                line = line.strip()
                verify.append(line)
                print "Verify Collected: " + line

            line = lines.pop(0)
            lineNum +=1
    except IndexError:
        pass

    result = Result.SUCCESS
    if warnings:
        result = Result.WARN
    if errors:
        result = Result.FAIL

    return (result, errors, warnings, verify)


def validateScriptedInstallValidate(fileName, 
                                    expResult=Result.SUCCESS, 
                                    expErrors=[], expWarnings=[],
                                    expVerify=[]):
    configToLoad = DEFAULT_CONFIG_NAME
    
    # XXX Need to do a reload here to restore defaults since the tests will
    # update userchoices.
    reload(userchoices)

    try:
        fauxroot.FAUXROOT = [configToLoad]
        # XXX Need to force a reprobe since the disk config might change.
        devices.DiskSet(forceReprobe=True)
        si = ScriptedInstallPreparser(fileName)
        si.warnedPhysicalPartition = True # XXX Take this out
        (result, errors, warnings) = si.parseAndValidate()

        if not errors:
            writeAction(None)
    finally:
        # Leave the fauxroot turned on if it's needed by the test, mostly we
        # just need it for the device scan.
        fauxroot.FAUXROOT = None
    
    print "Expected...."
    print expResult.__str__()
    print expErrors.__str__()
    print expWarnings.__str__()

    print "Actuall...."
    print fileName
    print result.__str__()
    print errors.__str__()
    print warnings.__str__()

    assert result == expResult
    assert validateListContents(errors, expErrors) == 1
    assert validateListContents(warnings, expWarnings) == 1

    for v in expVerify:
        # Evaluate the verify expression, use the current globals and add a
        # local named 'sip' that contains a reference to the parser object.
        assert eval(v, globals(), { 'sip' : si }), v

def validateListContents( actList, expList ):
    if len(actList) != len(expList):
        return 0

    match = 1
    i = 0
    while i + 1:
        try:
            act = actList[i]
            exp = expList[i]
            if not act.find(exp) > -1:
                match = 0
        except IndexError:
            i = -2
        i += 1
    return match

if __name__ == "__main__":
#    validateComplexPreparse(BASE_SCRIPT_PATH + 'complex.preparse.xdisplay.bs')
    print 'You can run this test suite using nosetests'
    print 'Exiting'
    sys.exit(0)
