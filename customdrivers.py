
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

import xml.dom.minidom
import os
import textwrap
import userchoices
import shutil
import pciidlib
import util

from log import log
from util import XMLGetText, XMLGetTextInUniqueElement, execCommand
from xml.parsers.expat import ExpatError

SIMPLE_MAP_FILE = '/etc/vmware/simple.map'
DRIVER_DEPOT_DIR = '/tmp/driver-depot/'
DRIVER_UNPACK_DIR = '/tmp/drivers/'
PCIID_DIR = '/usr/share/hwdata/pciids'
PCIID_CUSTOM_DIR = '/usr/share/hwdata/pciids/custom'
PCIID_FILE = '/usr/share/hwdata/pci.ids'
HWDATA_DIR = '/usr/share/hwdata/'
DRIVER_DIR = '/usr/lib/vmware/vmkmod/'

DRIVER_ERROR_MSG = "Driver entries must contain a name, version, filename " + \
                   "and the pci table and driver binary entries."
DRIVER_MALFORMED_MSG = "The driver disk provided had a malformed " + \
                       "drivers.xml file and can not be used."
DRIVER_DUPLICATE_MSG = "More than one driver entry with the same " + \
                       "file name was found."

INIT_DIR = '/etc/vmware/init/init.d/'
INIT_START_LEVEL = 12
INIT_WRAPPER = '/init'
DRIVER_XML_VERSION = 1.1

DRIVERS_LOADED = False

DRIVER_NAME = 0
DRIVER_VERSION = 1
DRIVER_DESCRIPTION = 2
DRIVER_BINLIST = 3
DRIVER_SNIPPETLIST = 4
DRIVER_REMOVELIST = 5

SCRIPT_ERROR_MSG = \
    "The following scripts failed to execute correctly:\n%s\n\n" + \
    "This may prevent the installation from completing successfully. " + \
    "Please consult the Knowledge Base."

NO_NIC_MSG = '''\
No network adapters were detected. Either no network adapters are \
physically connected to the system, or a suitable driver could not be \
located. A third party driver may be required.

ESX cannot be installed without a valid network adapter. Ensure that \
there is at least one network adapter physically connected to the system \
before attempting installation again. If the problem persists, consult \
the VMware Knowledge Base.
'''

FIND_INIT_SCRIPTS = """INIT_DIR="%s"
for script in $(ls ${INIT_DIR} | grep -e '^[0-9]\+\.' | sort -n) ; do
    echo $script
done
""" % INIT_DIR

class InvalidVersion(Exception):
    '''Invalid drivers.xml version'''

class InvalidDriversXml(Exception):
    '''Invalid drivers.xml file'''

class InvalidCustomDriverError(Exception):
    '''Invalid custom driver'''

class ScriptLoadError(Exception):
    '''Init script failed to load correctly.'''

class CriticalScriptLoadError(Exception):
    '''Init script failed critically.'''
    def getDetails(self):
        # sometimes this is due to no NICs being detected.  In that case
        # getDetails will return a friendly, verbose message
        try:
            import networking
            networking.init()
            pnics = networking.getPhysicalNics()
            # GUI has its own way to handle this prettily
            notGUI = userchoices.getRunMode() != userchoices.RUNMODE_GUI
            if len(pnics) == 0 and notGUI:
                paras = NO_NIC_MSG.split('\n')
                paras = ['\n'.join(textwrap.wrap(x, 70)) for x in paras]
                return '\n'.join(paras)
        except (Exception, networking.HostCtlException), ex:
            pass
        return ''


class CustomDriversXML(object):
    def __init__(self, fullPath="drivers.xml", setUserchoices=True):
        self.readDriverXml(fullPath)

    def readDriverXml(self, fullPath):
        def _parseVersionHeader(doc):
            driverDisk = doc.getElementsByTagName('driver_disk')
            if util.XMLTagLen(driverDisk) != 1:
                error = "Got more than one driver_disk entry."
                log.error(error)
                raise InvalidDriversXml, error
            driverDisk = driverDisk[0]

            try:
                version = float(driverDisk.getAttribute('version'))
            except ValueError:
                version = 0

            if version != DRIVER_XML_VERSION:
                error = "Got an unexpected version type for the driver disk."
                log.error(error)
                raise InvalidVersion, error

            return driverDisk

        def _findFileTag(tag, tagTitle, fileSuffix=''):
            fileList = []
            for targetFile in tag.getElementsByTagName(tagTitle):
                fileName = XMLGetText(targetFile)

                # files should be relative to the tmp directory path
                if tagTitle != 'remove_file' and fileName.startswith('/'):
                    fileName = fileName.lstrip('/')

                if fileSuffix and not fileName.endswith(fileSuffix):
                    log.warn("The file '%s' does not end with %s" %
                        (fileName, fileSuffix))

                if not fileName:
                    raise InvalidCustomDriverError
                fileList.append(fileName)
            return fileList

        log.debug("Reading drivers.xml...")
        getTagText = XMLGetTextInUniqueElement # handy alias

        try:
            doc = self.parse(fullPath, shouldRaise=True)
        except:
            raise InvalidDriversXml, DRIVER_MALFORMED_MSG

        driverDist = _parseVersionHeader(doc)

        self.driverDict = {}

        driverList = driverDist.getElementsByTagName('driverlist')
        error = ''
        if util.XMLTagLen(driverList) > 1:
            error = "More than one driverlist found."
        elif util.XMLTagLen(driverList) == 0:
            error = "The driverlist tag wasn't found."

        if error:
            log.error(error)
            raise InvalidDriversXml, error

        driverList = driverList[0]

        for driver in driverList.getElementsByTagName('driver'):
            driverBinList = []
            driverName = ''
            version = ''
            fileName = ''

            # if we're missing entries, return an error
            try:
                driverName = getTagText(driver, 'name').lstrip('/')
                version = getTagText(driver, 'version')
                fileName = getTagText(driver, 'filename').lstrip('/')
                description = getTagText(driver, 'description')
            except ValueError, msg:
                raise InvalidDriversXml, DRIVER_ERROR_MSG

            if '' in [driverName, version, fileName]:
                raise InvalidDriversXml, DRIVER_ERROR_MSG

            # Only allow single entries
            if fileName in self.driverDict:
                raise InvalidDriversXml, DRIVER_DUPLICATE_MSG

            # XXX - raise an error here if the file isn't on the driver
            #       disk.

            try:
                driverBinList = _findFileTag(driver, 'kernel_module', '.o')
                snippetList = _findFileTag(driver, 'pci_snippet', '.xml')
                removeFileList = _findFileTag(driver, 'remove_file')
            except InvalidCustomDriverError:
                raise InvalidCustomDriverError, driverName

            if not driverBinList or not snippetList:
                raise InvalidDriversXml, DRIVER_ERROR_MSG

            self.driverDict[fileName] = \
                (driverName,
                 version,
                 description,
                 driverBinList,
                 snippetList,
                 removeFileList)


    def parse(self, fullPath, shouldRaise=False):
        try:
            return xml.dom.minidom.parse(fullPath)
        except (IOError, ExpatError), ex:
            log.error('XML parsing error on file: %s' % fullPath)
            log.error('Expat exception details: %s' % str(ex))
            if shouldRaise:
                raise
            else:
                return None

def extractDriver(fileName):
    args = 'cd "%s" && rpm2cpio "%s" | cpio -id' % \
        (DRIVER_UNPACK_DIR, fileName)
    log.debug("extracting %s" % fileName)
    rc, stdout, stderr = execCommand(args, raiseException=True)
    return rc


def hostActionUnpackDrivers(context):
    uiHook = context.cb
    if not os.path.exists(DRIVER_UNPACK_DIR):
        os.makedirs(DRIVER_UNPACK_DIR)
    if not os.path.exists(PCIID_CUSTOM_DIR):
        os.makedirs(PCIID_CUSTOM_DIR)

    drivers = userchoices.getSupplementaryDrivers()

    if not drivers:
        return

    log.debug("Parsing pci.ids")
    pcidevs = pciidlib.PciDeviceSet(allowDuplicates=True)
    pcidevs.parsePciids(PCIID_FILE)

    for driver in drivers:
        fileName = os.path.basename(driver['filename'])
        extractDriver(os.path.join(DRIVER_DEPOT_DIR, fileName))

        for fileName in driver['removeList']:
            if os.path.exists(fileName):
                log.debug("Removing file %s" % fileName)
                os.unlink(fileName)
            else:
                log.warn("Couldn't find file %s to remove." % fileName)

        for fileName in driver['driverList']:
            fullPath = os.path.join(DRIVER_UNPACK_DIR, fileName)
            if os.path.exists(fullPath):
                shutil.copy(fullPath, DRIVER_DIR)
            else:
                # XXX - raise an error here?
                log.error("Couldn't find file %s" % fullPath)

        for fileName in driver['snippetList']:
            fullPath = os.path.join(DRIVER_UNPACK_DIR, fileName)
            if os.path.exists(fullPath):
                shutil.copy(fullPath, PCIID_CUSTOM_DIR)
                log.debug("Parsing %s" % fileName)
                pcidevs.parse(
                    os.path.join(PCIID_CUSTOM_DIR, os.path.basename(fileName)))
            else:
                # XXX - raise an error here?
                log.error("Couldn't find file %s" % fullPath)

    # rebuild pci.ids so that vmkctl will pick up the correct device names
    log.debug("Rebuilding pci.ids file")
    pciIds = pciidlib.makePciIdsFile(HWDATA_DIR, pcidevs)
    pciIds = pciIds.encode('latin-1')

    f = open(PCIID_FILE, 'w')
    f.write(pciIds)
    f.close()


def hostActionRebuildSimpleMap(context):
    log.debug("Rebuilding simple.map file")
    pciSet = pciidlib.PciDeviceSet(allowDuplicates=True)
    pciSet.scan(PCIID_DIR)
    pciSet.scan(PCIID_CUSTOM_DIR)

    f = open(SIMPLE_MAP_FILE, 'w')
    f.write(pciidlib.makeSimpleMapFile(pciSet))
    f.close()

def _findBaseInitLevel(script):
    level = script.split('.')[0]
    assert level.isdigit()

    return int(level)

def hostActionLoadDrivers(context):
    global DRIVERS_LOADED

    if DRIVERS_LOADED:
        return

    uiHook = context.cb
    
    # when in rome...
    f = open('/tmp/initscripts.sh', 'w')
    f.write(FIND_INIT_SCRIPTS)
    f.close()

    initScripts = util.execWithCapture('/bin/bash', ['/bin/bash', '/tmp/initscripts.sh'])
    initScripts = initScripts.split()

    units = len(initScripts)
    uiHook.pushStatusGroup(units)

    criticalFailure = False

    scriptsFailed = []
    log.info("Starting driver load ...")
    for script in initScripts:
        script = os.path.basename(script)

        if _findBaseInitLevel(script) < INIT_START_LEVEL:
            continue

        log.info("Loading %s" % script)
        uiHook.pushStatus("Loading %s" % script)
        rc, stdout, stderr = \
            execCommand("cd / && INSTALLER=1 %s %s" % (INIT_WRAPPER, script))

        if rc == 1:
            warningMessage = "The script %s returned status 1" % script
            log.warning(warningMessage)
        elif rc == 2:
            errorMessage = "A non-critical error has happened in the " + \
                    "script %s.  The installation can continue " % script + \
                    "but you may experience reduced functionality."
            log.error(errorMessage)
            scriptsFailed.append(script)
        elif rc == 3:
            errorMessage = "The script %s failed to execute " % (script) + \
                           "and the installation can not continue."
            criticalFailure = True
            break
        elif rc:
            errorMessage = "An unexpected error occurred in the " + \
                           "script %s." % script
            criticalFailure = True
            break

        uiHook.popStatus()

    if criticalFailure:
        log.error(errorMessage)
        uiHook.popStatus()
        uiHook.popStatusGroup()
        raise CriticalScriptLoadError(errorMessage)
        

    # XXX should be done by the init scripts...  the device nodes will get
    # created implicitly by devices.DiskSet() but not everything that needs
    # a device node goes through there.
    import partition
    partition.createDeviceNodes()
    
    DRIVERS_LOADED = True

    uiHook.popStatusGroup()

    if scriptsFailed:
        messageText = SCRIPT_ERROR_MSG  % ", ".join(scriptsFailed)
        raise ScriptLoadError(messageText)

