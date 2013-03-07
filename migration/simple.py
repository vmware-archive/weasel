
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

import os
import re
import sys
import util
import shlex
import shutil
import filecmp
import handlers

import time
import timedate
import consts
from log import log

def _ensureVmwarePath():
    '''We make use of the vmware.authentication package, so this function
    ensures that it is in the PYTHONPATH.'''
    vmwarePythonRoot = os.path.join(consts.HOST_ROOT,
                                    "usr/lib/vmware/python2.2/site-packages")
    if vmwarePythonRoot not in sys.path:
        sys.path.append(vmwarePythonRoot)

def _splitWhite(line):
    '''Split a line containing a key/value pair based on white space.

    Comments are handled only at the start of a line.
    '''
    m = re.match(r'\s*([^# \t]+)\s+(.+)', line)
    if m:
        return (m.group(1), m.group(2).strip())

    return None

def _splitShlex(line):
    '''Split a line using shlex and pay attention to comments.'''
    retval = None
    try:
        args = shlex.split(line, True)
        if len(args) > 1:
            retval = (args[0], args[1:])
    except ValueError:
        log.debug("could not split line -- %s" % line)
    
    return retval

def _matchPair(keyToFind, values):
    '''Find a key/value pair in a flat list of values.

    >>> _matchPair('key', ['foo', 'key', 'value'])
    'value'
    >>> _matchPair('foo', ['foo', 'key', 'value'])
    'key'
    >>> _matchPair('bar', ['foo', 'key', 'value'])
    >>> _matchPair('value', ['foo', 'key', 'value'])
    '''
    adjacentPairs = zip(values[:-1], values[1:])
    for key, value in adjacentPairs:
        if key == keyToFind:
            return value
    return None

def _findByContents(contentPath, dirToSearch):
    for root, _dirs, files in os.walk(dirToSearch):
        for filename in files:
            fullPath = os.path.join(root, filename)
            if not os.path.isfile(fullPath):
                continue
            try:
                if filecmp.cmp(contentPath, fullPath):
                    return fullPath
            except Exception, e:
                log.debug("exception while comparing files (%s, %s) -- %s" % (
                        contentPath, fullPath, str(e)))
                
    return None

def extractPairsFromLines(lines,
                          requestedKeys=None,
                          splitter=_splitWhite):
    '''Extract key-value pairs for a list of lines.

    >>> extractPairsFromLines(['key value', ' key2\tvalue2'])
    [('key', 'value'), ('key2', 'value2')]
    >>> extractPairsFromLines(["#key value"])
    []
    >>> extractPairsFromLines(['key value'], requestedKeys=['key2'])
    []
    '''
    retval = []
    for line in lines:
        pair = splitter(line)
        if pair and (not requestedKeys or pair[0] in requestedKeys):
            retval.append(pair)

    return retval

def migrateActionIgnore(oldPath, newPath, _accum):
    log.debug("not migrating %s -> %s" % (oldPath, newPath))
    return False

def migrateActionSSH(oldPath, newPath, accum):
    '''Migrates any files referenced by the sshd_config file and turns on the
    UsePAM flag, which is needed for kerberos and LDAP to work.'''
    fileKeys = [ "HostKey", "Banner", ]
    confFile = open(oldPath, 'r')
    confPairs = extractPairsFromLines(confFile, requestedKeys=fileKeys + [
        "UsePAM",
        ])
    hasUsePAM = False
    for key, value in confPairs:
        if key in fileKeys:
            accum.append(value)
        elif key == "UsePAM":
            hasUsePAM = True

    if hasUsePAM:
        return True
    else:
        from migrate import cloneFile
        cloneFile(oldPath, newPath)
        log.debug("activating PAM authentication for sshd")
        newConfFile = open(newPath, 'a')
        newConfFile.write("UsePAM yes\n")
        newConfFile.close()
        return False

def migrateActionNsSwitch(oldPath, newPath, _accum):
    '''There's a "bug" in esx3 where LDAP was not added to the "shadow" service
    in nsswitch.conf.  You could still login in esx3, however, the same file
    won't work in esx4.  So, this migration handler will copy the file and
    ensure that ldap is turned on for the shadow service if it is turned on for
    passwd.'''
    from migrate import cloneFile
    cloneFile(oldPath, newPath)
    
    _ensureVmwarePath()
    from vmware.authentication.NSSManager import NSSManager
    man = NSSManager(newPath)
    if "ldap" in man.config.get("passwd", []):
        log.debug("enabling ldap for shadow service in nsswitch.conf")
        man.AddLookupOrder("shadow", "ldap")
    man.WriteConfig()
    return False
    
def migrateActionPamD(oldPath, newPath, _accum):
    '''The system-auth file was moved to system-auth-generic, also we need to
    add the try_first_pass flag, otherwise the user might get prompted with two
    password prompts on login.'''
    if newPath.endswith("/system-auth"):
        newPath = "%s-generic" % newPath
    from migrate import cloneFile
    cloneFile(oldPath, newPath)
    oldAuthFile = open(oldPath, "r")
    newAuthFile = open(newPath, "w")
    for line in oldAuthFile:
        strippedLine = line.lstrip()
        newLine = line
        # The following sub converts lines like:
        #   auth required pam_stack.so service=system-auth
        # to:
        #   auth include system-auth
        newLine = re.sub(r'(auth|account|password|session)(\s+)'
                         r'\S+(\s+)'
                         r'.*pam_stack.* service=(.*)',
                         r'\1\2include\3\4',
                         newLine)
        if newPath.endswith("/system-auth-generic") and \
                ((strippedLine.startswith("auth") or \
                      strippedLine.startswith("password")) and \
                     strippedLine.find("try_first_pass") == -1):
            log.debug("adding try_first_pass in system-auth for -- %s" % line)
            newLine = re.sub(r'(pam_unix\.so)',
                             r'\1 try_first_pass',
                             newLine)
        newLine = re.sub(r'/lib/security/([^\$])',
                         r'/lib/security/$ISA/\1',
                         newLine)
        newAuthFile.write(newLine)
    return False
    
def migrateActionNtp(oldPath, _newPath, accum):
    confFile = open(oldPath, 'r')
    filePairs = extractPairsFromLines(confFile,
                                      splitter=_splitShlex,
                                      requestedKeys=[
        "driftfile",
        "keys",
        "keysdir",
        "statsdir",
        "crypto",
        "includefile",
        ])
    for key, value in filePairs:
        valueStr = value[0]
        if key == "includefile":
            # includefile <path-to-file>
            handlers.MIGRATION_HANDLERS[valueStr] = migrateActionNtp
            accum.append(valueStr)
        elif key == "crypto":
            # crypto [cert <file>] [leap <file>] [randfile <file>] [host <file>]
            #   [sign <file>] [gq <file>] [gqpar <file>] [iffpar <file>]
            #   [mvpar <file>] [pw <password>]
            while len(value) >= 2:
                subKey, subValue = value[:2]
                if subKey in ["cert", "gq", "gqpar", "host", "iffpar",
                              "leap", "mvpar", "randfile", "sign",
                              "privatekey", "publickey", "dhparams",]:
                    accum.append(subValue)
                value = value[2:]
        else:
            accum.append(valueStr)
    return True

def migrateActionNtpd(oldPath, newPath, _accum):
    newFile = open(newPath, "w")
    for line in open(oldPath):
        if line.lstrip().startswith('OPTIONS'):
            # -U option changed to -u, controls the user that the daemon runs as
            line = re.sub(r'''(["'\s])-U\b''', r'\1-u', line)
            # -T option changed to -i, the chroot directory
            line = re.sub(r'''(["'\s])-T\b''', r'\1-i', line)
            # -e option was removed.
            line = re.sub(r'''(["'\s])-e\s+[^\s"']+''', r'\1', line)
        newFile.write(line)
    newFile.close()

def migrateClock(oldPath, newPath, accum):
    _rc, utc, _stderr = util.execCommand(". %s && echo $UTC" % oldPath)
    utc = utc.strip()
    
    isUTC = utc.lower() not in ["false", "0"]
    if isUTC:
        return migrateTimezone(oldPath, newPath, accum)

    shutil.copyfile(oldPath, oldPath + ".backup")
    
    # The vmkernel expects the hw clock to be set to UTC time, so we need
    # to update it.
    log.info("changing hardware clock to UTC time")
    newContents = ""
    for line in open(oldPath):
        if line.lstrip().startswith('UTC'):
            newContents += "# UTC changed to true during upgrade\n"
            newContents += "UTC=true\n"
        else:
            newContents += line
    # Change the file in 3.x, so the time is still right on rollback.
    open(oldPath, "w").write(newContents)

    retval = migrateTimezone(oldPath, newPath, accum)

    # migrateTimezone can write a new clock file with a different ZONE
    # value, so we have to read the new one in that case.
    if os.path.exists(newPath):
        clockPath = newPath
    else:
        clockPath = oldPath
    _rc, zoneName, _stderr = util.execCommand(
        ". %s && echo $ZONE" % clockPath)
    zoneName = zoneName.strip()

    # Change the timezone used by python.
    os.environ['TZ'] = zoneName
    time.tzset()

    # Get the current time in seconds, which is really in the current
    # timezone, and use the timezone to change the hwclock to UTC time.
    secsFromEpochLocal = time.time()
    secsFromEpochUTC = secsFromEpochLocal + time.timezone
    timeTuple = time.gmtime(secsFromEpochUTC)[:6]
    timedate.setHardwareClock(timeTuple)
    
    os.environ['TZ'] = ''
    time.tzset()
        
    return retval

def migrateTimezone(oldPath, newPath, _accum):
    zoneInfoPath = "/usr/share/zoneinfo/"

    # First, check to see if the clock file and localtime are in sync.
    _rc, zoneName, _stderr = util.execCommand(". %s && echo $ZONE" % oldPath)
    zoneName = zoneName.strip()
    
    zonePath = os.path.join(consts.HOST_ROOT,
                            consts.ESX3_INSTALLATION.lstrip('/'),
                            zoneInfoPath.lstrip('/'),
                            zoneName.lstrip('/'))
    oldLocaltime = os.path.join(consts.HOST_ROOT,
                                consts.ESX3_INSTALLATION.lstrip('/'),
                                "etc/localtime")

    if not os.path.lexists(oldLocaltime):
        log.debug("no /etc/localtime, assuming clock file is good")
        return True
    
    try:
        if filecmp.cmp(oldLocaltime, zonePath):
            log.debug("ZONE value in clock file matches /etc/localtime")
            return True
    except Exception, e:
        log.debug("unable to compare localtime with zoneinfo -- %s" % str(e))

    # Unlikely, but clock and localtime disagree, try to use localtime as the
    # authoritative setting.
    authoritativeZone = None
    if os.path.islink(oldLocaltime):
        # Prefer to figure it out from a link rather than the file contents
        # since files are duplicated and while the setting might be technially
        # correct, the name might be off.
        oldLocaltime = os.path.abspath(os.readlink(oldLocaltime))
        authoritativeZone = oldLocaltime[len(zoneInfoPath):]
        log.debug("/etc/localtime is a link to %s" % oldLocaltime)
    else:
        zoneInfoPath = os.path.join(consts.HOST_ROOT,
                                    consts.ESX3_INSTALLATION.lstrip('/'),
                                    zoneInfoPath.lstrip('/'))

        zonePath = _findByContents(oldLocaltime, zoneInfoPath)
        if zonePath:
            authoritativeZone = zonePath[len(zoneInfoPath):].lstrip('/')
            log.debug("found zone file matching /etc/localtime -- %s" %
                      zonePath)
            
    if not authoritativeZone:
        # Could not find the matching zone info, just copy the file.
        log.warn("could not find zone file matching /etc/localtime, using "
                 "ZONE setting in /etc/sysconfig/clock as authoritative "
                 "timezone setting")
        return True

    log.debug("  setting ZONE in clock to %s based on localtime" %
              authoritativeZone)
    
    newFile = open(newPath, "w")
    # Always write the zone, in case it was not in the file in the first place.
    newFile.write("ZONE=%s\n" % authoritativeZone)
    for line in open(oldPath):
        if line.lstrip().startswith('ZONE'):
            continue
        newFile.write(line)
    newFile.close()

    return False
