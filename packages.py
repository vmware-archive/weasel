#! /usr/bin/env python

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

''' packages.py

This module handles the representing, reading, and installing RPM packages

'''
import os
import rpm
import glob
import struct
import socket
import cPickle

import xml.dom.minidom
from xml.parsers.expat import ExpatError
from util import XMLGetText, XMLGetTextInUniqueElement
from urlparse import urljoin

import consts
import systemsettings
import userchoices
from remote_files import downloadLocally, isURL, URLify, getCacher
from remote_files import HTTPError, URLError, RemoteFileError
from log import log
from util import SIZE_MB
from exception import InstallationError

import workarounds

RPMCOLOR_32BIT = 1
RPMCOLOR_64BIT = 2
DB_PATH = os.path.join(consts.HOST_ROOT, "var/lib/rpm")

REQUIREMENT_OPTIONS = ("required", "recommended", "optional")

# Whiteout list for erasing dependencies to break dependency loops.  The format
# is:
#
#   package-with-requires>package-with-provides
#
# Details:
#   libtermcap>bash libtermcap>glibc - For bug 497654, the glibc-common %pre
#   script adds a dependency on /bin/sh and creates some dep loops that causes
#   other problems.  To get around this, we have to mess around with libtermcap
#   to get it installed early on.
WHITEOUT = """
libtermcap>bash
libtermcap>glibc
"""

# -----------------------------------------------------------------------------
class UnsatisfiedDependencyException(Exception):
    def __init__(self, unresolvedDeps):
        Exception.__init__(self, "Some packages have unresolved dependencies")

        self.unresolvedDeps = unresolvedDeps

    def getDetails(self):
        retval = "\nUnsatisfied dependencies:\n  "
        retval += "\n  ".join(self.unresolvedDeps)
        retval += "\n\n"
        return retval

# -----------------------------------------------------------------------------
__transactionSet = None
def getTransactionSet():
    '''Factory function for the module-level transaction set'''
    global __transactionSet
    if __transactionSet:
        return __transactionSet

    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    rpm.addMacro("_dependency_whiteout", WHITEOUT)

    #rpm.addMacro("_dbpath", DB_PATH)

    __transactionSet = rpm.TransactionSet(consts.HOST_ROOT)

    #Apply some rpm magic to tell the transaction set to not
    #check the signatures of the RPM files.
    #
    #NOTE: in future versions of the rpm python bindings, these flags will be 
    #rpm.RPMVSF_NOSIGNATURES, rpm.RPMVSF_NODIGESTS
    __transactionSet.setVSFlags(~(rpm.RPMVSF_NORSA|rpm.RPMVSF_NODSA))

    # XXX This needs to be fixed eventually.
    # we're using a 32bit rpm lib to install 64bit rpms.  The following
    # flag silences the resulting error.
    __transactionSet.setProbFilter(rpm.RPMPROB_FILTER_IGNOREARCH)
    return __transactionSet


# -----------------------------------------------------------------------------
def checkMediaRootIsValid(mediaRootURL):
    '''Verify that the given URL is actually an ESX Installation Media Root
    checking that it can be reached and that it contains an XML file
    named packages.xml
    '''
    #TODO: it would be nice to do some more incremental checking of the
    #      remote host - lookup the hostname, ping it, etc.
    log.info('Verifying that %s is an ESX Installation Media Root...' %\
             mediaRootURL)
    packagesXMLLocation = mediaRootURL +'/packages.xml'

    def integrityChecker(localPath):
        try:
            xml.dom.minidom.parse(localPath)
        except ExpatError, ex:
            log.warn('XML parsing error on file: %s' % packagesXMLLocation)
            return False
        return True

    oldTimeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(30) # 30 seconds
    success = False
    try:
        downloadLocally(packagesXMLLocation,
                        clobberCache=True,
                        integrityChecker=integrityChecker,
                        maxAttempts=1)
        success = True
    except Exception, ex:
        log.info('Media Root invalid.  Got exception: %s (%s)'
                 % (ex.__class__.__name__,str(ex)))
    socket.setdefaulttimeout(oldTimeout)
    return success

# -----------------------------------------------------------------------------
class PackageData(object):
    '''Container class for package header files and sizes of the unpacked
       directories.  This replaces the Primary.xml file.
       Accessible attributes:
           .fileDict : dictionary of unpacked directory sizes
           .headerSizes : dictionary of begin/end/header sizes for each pkg
    '''
    def __init__(self, baseLocation):
        self.headerDict = {}
        fileName = self._getLocalPath(baseLocation)

        self.getHeaderData(fileName)

    def getHeaderData(self, fileName):
        f = open(fileName, 'r')
        rpmDict = cPickle.load(f)
        f.close()

        self.headerDict = rpmDict['headerSizes']
        self.fileDict = rpmDict['fileSizes']

    def _getLocalPath(self, baseLocation):
        baseLocation = URLify(baseLocation)

        placesToTry = [urljoin(baseLocation, 'packageData.pkl')]

        for place in placesToTry:
            log.debug('Looking for %s' % place)
            try:
                filename = downloadLocally(place)
                return filename
            except (HTTPError, URLError, IOError, RemoteFileError):
                continue

        raise ValueError('Could not find packageData.pkl file under %s'
                         % baseLocation)

# -----------------------------------------------------------------------------
class PackagesXML(object):
    #TODO: change the interface from .rpmBasenames to something more intuitive
    #      maybe packageNames
    '''A class to read in packages.xml and provide a friendly interface
    Accessible attributes:
        .kernLabel
        .kernVersion
        .installDepot
        .fullInstallDepot
        .rpmBasenames
    '''
    def __init__(self, supportedPackageGroups, fullPath="packages.xml",
                 mediaRoot="."):
        '''Warning: the constructor can potentially raise remote_files
        exceptions.
        '''
        log.debug("Reading packages.xml...")
        getTagText = XMLGetTextInUniqueElement # handy alias

        if isURL(fullPath):
            # this can potentially raise HTTPError or URLError
            log.debug('Downloading the packages.xml file')
            fullPath = downloadLocally(fullPath, integrityChecker=self.parse)

        doc = self.parse(fullPath, shouldRaise=True)

        products = doc.getElementsByTagName("product")
        if len(products) != 1:
            log.warn('Expected to find only one <product> in packages.xml')
        product = products[0]

        self.name = getTagText(product, 'name')
        self.esxVersion = getTagText(product, 'esx_version')
        self.esxThirdPartyVersion = getTagText(product, 'esx_tp_version')
        self.esxThirdPartyCompatVersion = getTagText(product,
                                                     'esx_tp_compat_version')
        self.release = '%s.%s' % (getTagText(product, 'esx_release'),
                                  getTagText(product, 'release'))

        # bootloader.py needs these two
        self.kernLabel = getTagText(product, "kernel_name")
        self.kernVersion = getTagText(product, "kernel_version")

        self.installDepot = getTagText(product, 'install_depot')
        if isURL(mediaRoot):
            self.fullInstallDepot = urljoin(mediaRoot, self.installDepot)
        else:
            self.fullInstallDepot = os.path.join(mediaRoot, self.installDepot)
        log.info("Full install depot is %s" % (self.fullInstallDepot))

        self.rpmBasenames = []
        for depot in doc.getElementsByTagName("depot"):
            element = depot.getAttribute("name")

            if supportedPackageGroups != None: #NOTE: [] != None
                if element not in supportedPackageGroups:
                    log.debug("Skipping depot %s" % (element))
                    continue

            for rpmlist in depot.getElementsByTagName("rpmlist"):
               repo = rpmlist.getAttribute('repo')

               for node in rpmlist.getElementsByTagName("rpm"):
                   archOpt = node.getAttribute("arch")
                   #TODO: at some point 'both' should be 'i386,x86_64' and we 
                   #      should split on ','
                   if archOpt == "both":
                       archList = ['i386', 'x86_64']
                   else:
                       archList = [getTagText(depot, 'arch')]

                   reqOpt = node.getAttribute("requirement").lower()
                   if reqOpt not in REQUIREMENT_OPTIONS:
                       reqOpt = "required"

                   package = node.getAttribute('package')
                   changeset = node.getAttribute('changeset')

                   for arch in archList:
                       basename = XMLGetText(node)
                       basename = basename.replace("${esx_version}",
                                                   self.esxVersion)
                       basename = basename.replace("${esx_tp_version}",
                                                   self.esxThirdPartyVersion)
                       basename = basename.replace("${esx_tp_compat_version}",
                                                   self.esxThirdPartyCompatVersion)
                       basename = basename.replace("${release}", self.release)
                       basename = basename.replace("${driver_release}",
                                                   self.release)
                       basename = basename.replace("${arch}", arch)

                       basename = basename.replace('${repo}', repo)
                       basename = basename.replace('${package}', package)
                       basename = basename.replace('${changeset}', changeset)

                       self.rpmBasenames.append((basename, reqOpt))


    def parse(self, fullPath, shouldRaise=False):
        try:
            return xml.dom.minidom.parse(fullPath)
        except ExpatError, ex:
            log.error('XML parsing error on file: %s' % fullPath)
            log.error('Expat exception details: %s' % str(ex))
            if shouldRaise:
                raise
            else:
                return None

# -----------------------------------------------------------------------------
def getPackagesXML(supportedPackageGroups):
    mediaLocation = userchoices.getMediaLocation()
    if mediaLocation:
        mediaRoot = mediaLocation['mediaLocation']
        url = urljoin(mediaRoot, 'packages.xml')
    else:
        mediaRoot = consts.MEDIA_DEVICE_MOUNT_POINT
        url = urljoin(URLify(os.path.join(mediaRoot, '')), 'packages.xml')
    
    try:
        packagesXMLPath = downloadLocally(url, maxAttempts=3)
    except RemoteFileError:
        msg = 'packages.xml was not found on the remote server.'
        log.error(msg)
        raise

    return PackagesXML(supportedPackageGroups, packagesXMLPath, mediaRoot)

# -----------------------------------------------------------------------------
def dependencyCheckCallback(ts, tag, name, evr, flags):
    if tag == rpm.RPMTAG_REQUIRENAME:
        if evr:
            requires = "%s-%s" % (name, evr)
        else:
            requires = name
        log.warn("Unmet requirement: %s" % (requires,))
    elif tag == rpm.RPMTAG_CONFLICTNAME:
        pass
    else:
        log.warn("Unknown tag: %s" % (tag,))

    return 1


# -----------------------------------------------------------------------------
class Packages:
    '''A collection of (rpm) packages'''
    def __init__(self, initTS=True, uiHook=None, weaselConfig=None):
        self.ts = None
        self.totalSize = 0
        self.packages = []
        self.currentHeader = ""
        self.uiHook = None

        if initTS:
            self.ts = getTransactionSet()

        if uiHook:
            self.uiHook = uiHook

        # get the package groups we're going to support
        if not weaselConfig:
            weaselConfig = systemsettings.WeaselConfig()
        self.packageGroups = weaselConfig.packageGroups

    def initializeDB(self):
        # create the dir
        log.debug("Init database")
        self.ts.initDB()

    def readPackages(self, packagetype="iso",
                     release="", releasePrefix="", releaseType="beta"):
        packagesXML = getPackagesXML(self.packageGroups)

        packageData = PackageData(packagesXML.fullInstallDepot)
        

        for basename, requirement in packagesXML.rpmBasenames:
            #TODO: know which sep to use here, os.path.sep or '/'
            pkgPath = "%s/%s" % (packagesXML.fullInstallDepot, basename)
            log.debug('Creating Package object for %s' % pkgPath)

            if isURL(pkgPath) and '*' in basename:
                log.error('WILDCARDS CANNOT BE USED WITH REMOTE MEDIA. FIXME')
                continue
            elif not isURL(pkgPath) and not os.path.exists(pkgPath):
                # TODO: this glob stuff should die because wildcards make
                #       things unpredictable and make it so there are 
                #       different rules for local vs. remote packages.xml
                #       files.
                matches = glob.glob(pkgPath)
                if not matches:
                    log.debug("Couldn't find %s" % pkgPath)
                    continue
                if len(matches) > 1:
                    log.debug("More than one package matches %s using %s" 
                              % (pkgPath, matches[-1]))
                pkgPath = matches[-1]

            try:
                (pkgName, pkgSize, hdrStart, hdrEnd) = \
                    packageData.headerDict[basename]
                package = Package(pkgPath,
                                  requirement,
                                  hdrStart,
                                  hdrEnd,
                                  pkgSize,
                                  pkgName)
                self.packages.append(package)
            except KeyError:
                msg = ('Encountered an error while creating the packages list.'
                ' Metadata for a package (%s) listed in the packages.xml file'
                ' was not found in the packageData.pkl database in your RPM'
                ' repository.  Re-run createinstdepot.py and try'
                ' again' % (basename)
                )
                log.error(msg)
                raise Exception(msg)

        # include any supplementary packages
        for pkg in userchoices.getPackageObjectsToInstall():
            self.packages.append(pkg)

    def getPackageNames(self):
        return [pkg.name for pkg in self.packages]

    def getPackagesByName(self, name):
        return [pkg for pkg in self.packages if pkg.name == name]

    def _handleDependencies(self, deplist):
        '''Handle any unresolved dependencies returned by the
        TransactionSet.check() method.
        '''
        stillUnresolved = []
        for (unsatisfiedPkg, reqNameVer, _needsFlag, suggestedPkg, _sense) \
                in deplist:
            if reqNameVer[1]:
                reqString = "%s-%s" % reqNameVer
            else:
                reqString = reqNameVer[0]
            msg = "Package %s-%s-%s requires %s" % \
                  (unsatisfiedPkg + (reqString,))
            log.info(msg)
            if userchoices.getResolveDeps() and suggestedPkg:
                package = suggestedPkg[0]
                log.info("  resolving dependency with %s" % package.fullSrcPath)
                self.ts.addInstall(package.header, (package,), 'u')
                self.totalSize += (package.header[rpm.RPMTAG_SIZE] / SIZE_MB)
            elif userchoices.getIgnoreDeps():
                log.info("  ignoring dependency")
            else:
                log.error("unable to resolve dependency -- %s" % msg)
                stillUnresolved.append(msg)

        return stillUnresolved
        
    def installPackages(self):
        #self.ts.setProbFilter(rpm.RPMPROB_FILTER_DISKSPACE)

        # CPD - magic setColor(3) method which fixes all of your RPM woes.
        #       this actually tells rpmlib to allow both i386 and x86_64
        #       rpms.
        self.ts.setColor(RPMCOLOR_32BIT | RPMCOLOR_64BIT)

        for package in self.packages:
            rpmHeader = package.header
            # callbackArgs find their way into InstallCallback.runCallback
            callbackArgs = (package,)
            if (package.requirement == "required" or
                (package.requirement == "recommended" and
                 package.name not in userchoices.getPackagesNotToInstall()) or
                (package.requirement == "optional" and
                 package.name in userchoices.getPackagesToInstall())):
                self.ts.addInstall(rpmHeader, callbackArgs, 'u')
                self.totalSize += (rpmHeader[rpm.RPMTAG_SIZE] / SIZE_MB)
            elif userchoices.getResolveDeps():
                # Make the packages 'available' for automatic dependency stuff.
                self.ts.addInstall(rpmHeader, callbackArgs, 'a')
            else:
                log.info("skipping optional package %s" % package.name)

        cb = InstallCallback(self.totalSize, len(self.packages), self.uiHook)

        while True:
            unsatisfiedDeps = self.ts.check(dependencyCheckCallback)
            if not unsatisfiedDeps:
                break
            
            stillUnresolved = self._handleDependencies(unsatisfiedDeps)
            if stillUnresolved:
                raise UnsatisfiedDependencyException(stillUnresolved)
        
        self.ts.order()
        self.checkForProblems()

        buf = "Packages to install (post-check):"

        # XXX - rpm.ts objects aren't completely wrapped.  normally you'd
        #       want to check to see if there are any entries in it but there
        #       is no way to call len()
        for rpmPkg in self.ts:
            buf += " %s-%s-%s-%s" % \
                (rpmPkg.N(), rpmPkg.V(), rpmPkg.R(), rpmPkg.A())

        log.info(buf)

        if self.uiHook:
            self.uiHook.pushStatusGroup(self.totalSize)
        self.ts.run(cb.runCallback, 0)
        self.checkForProblems()
        if self.uiHook:
            self.uiHook.popStatusGroup()

    def checkForProblems(self):
        # XXX Do more than just logging here.
        problems = self.ts.problems()
        if problems:
            log.error('RPM transaction set problems:')
            for prob in problems:
                log.error(' %s' % prob)


# -----------------------------------------------------------------------------
class InstallCallback:
    def __init__(self, totalSize, totalCount, uiHook=None, scale=0.8):
        self.totalSize = totalSize
        self.totalCount = totalCount
        self.uiHook = uiHook
        self.scale = scale
        self.rpmFd = None
        self.packageCounter = 0


    def runCallback(self, reason, amount, total, callbackArgs, param):
        '''This method is called by the RPM installation backend.  It is
        mostly called as a means to report progress.  It also needs to
        download incomplete files and needs to open/close files.
        '''
        reasonDispatch = {
              rpm.RPMCALLBACK_INST_OPEN_FILE  : self.cbInstallOpenFile,
              rpm.RPMCALLBACK_INST_CLOSE_FILE : self.cbInstallCloseFile,
              rpm.RPMCALLBACK_UNPACK_ERROR    : self.cbFileError,
              rpm.RPMCALLBACK_CPIO_ERROR      : self.cbFileError,
              rpm.RPMCALLBACK_UNKNOWN         : self.cbUnknown,
              rpm.RPMCALLBACK_INST_PROGRESS   : self.cbNoop,
              rpm.RPMCALLBACK_INST_START      : self.cbNoop,
              rpm.RPMCALLBACK_TRANS_PROGRESS  : self.cbNoop,
              rpm.RPMCALLBACK_TRANS_START     : self.cbNoop,
              rpm.RPMCALLBACK_TRANS_STOP      : self.cbNoop,
        }
        try:
            return reasonDispatch[reason](callbackArgs)
        except KeyError:
            log.warn('No handler known for the RPM event %s' % str(reason))


    def cbInstallOpenFile(self, callbackArgs):
        package = callbackArgs[0]

        self.packageCounter += 1

        buf = "Installing package: %s (%d of %d)" % \
              (package.name, self.packageCounter, self.totalCount)
        log.debug(buf)

        if self.uiHook:
            amount =  package.header[rpm.RPMTAG_SIZE] / SIZE_MB
            self.uiHook.pushStatus(buf, amount)

        package.ensureFileDownloaded()
        self.rpmFd = os.open(package.localLocation, os.O_RDONLY)
        return self.rpmFd

    def cbInstallCloseFile(self, callbackArgs):
        package = callbackArgs[0]

        os.close(self.rpmFd)
        self.rpmFd = None
        package.deleteDownloadedFile() # recover space on /mnt/sysimage

        if self.uiHook:
            self.uiHook.popStatus()

    def cbFileError(self, callbackArgs):
        if callbackArgs:
            package = callbackArgs[0]
            msg = "Unpack or CPIO error installing package %s" % \
                  package.localLocation
        else:
            msg = "Unpack or CPIO error"
        #TODO: expand on the message of this error saying that there is a 
        #      problem with the local storage that the user is installing onto
        #      or the CD that they burned is likely scratched / bad
        log.error(msg)
        raise InstallationError(msg)

    def cbUnknown(self, callbackArgs):
        if callbackArgs:
            package = callbackArgs[0]
            msg = "Unknown problem with package %s" % package.localLocation
        else:
            msg = "Unknown RPM problem"
        log.error(msg)
        raise Exception(msg)

    def cbNoop(self, callbackArgs):
        pass

# -----------------------------------------------------------------------------
class Package(object):

    @staticmethod
    def readRPMHeader(fileName):
        log.debug("Reading header for: %s" % fileName)
        transactionSet = getTransactionSet()
        fd = os.open(fileName, os.O_RDONLY)
        header = transactionSet.hdrFromFdno(fd)
        os.close(fd)
        return header

    @staticmethod
    def readRPMHeaderInfo(fileName):
        log.debug("Reading header data for: %s" % fileName)

        fd = open(fileName, 'r')

        # read past lead and first 8 bytes
        fd.seek(104)
        (sigindex, ) = struct.unpack('>I', fd.read(4))
        (sigdata, ) = struct.unpack('>I', fd.read(4))

        # index is 4x32bit segments or 16 bytes
        sigsize = sigdata + (sigindex * 16)

        # round off to the next 8 byte boundary
        tail = 0
        if sigsize % 8:
            tail = 8 - (sigsize % 8)

        hdrstart = 112 + sigsize + tail

        # go to the start of the header
        fd.seek(hdrstart)
        fd.seek(8, 1)

        (hdrindex, ) = struct.unpack('>I', fd.read(4))
        (hdrdata, ) = struct.unpack('>I', fd.read(4))

        # add 16 bytes to account for misc data at the end of the sig
        hdrsize = hdrdata + (hdrindex * 16) + 16

        hdrend = hdrstart + hdrsize
        fd.close()

        return (hdrstart, hdrend)

    def __init__(self, fullSrcPath, requirement,
                 headerStartByte=0, headerEndByte=0, pkgSize=0,
                 name=''):

        # we want to download even the CD-ROM media to /mnt/sysimage/tmp so 
        # that we can avoid hassles with ILO/DRAC
        self.fullSrcPath = URLify(fullSrcPath)
        self.requirement = requirement
        self.pkgSize = pkgSize
        self.name = name
        self._headerLength = headerStartByte + headerEndByte

        # lookup the header info if we're missing the package name
        if not name:
            self._lookupHeaderInfo(fullSrcPath)

        # Don't download the headers yet, as /mnt/sysimage might not
        # have been mounted
        self._finishedDownloading = False
        self._localLocation = None

        self._header = None

    def _lookupHeaderInfo(self, fileName):
        pkgHeader = self.readRPMHeader(fileName)
        self.pkgSize = os.path.getsize(fileName)
        self.name = pkgHeader['name']

        headerStartByte, headerEndByte = self.readRPMHeaderInfo(fileName)
        self._headerLength = headerStartByte + headerEndByte

    def _getLocalLocation(self):
        if not self._localLocation:
            self._downloadHeaderFragment()
        return self._localLocation
    localLocation = property(_getLocalLocation)

    def _getHeader(self):
        if not self._header:
            self._downloadHeaderFragment()
        return self._header
    header = property(_getHeader)

    def integrityChecker(self, filename):
        # XXX - not sure if this applies to packageData.pkl
        # special case: VMware-hostd doesn't match in the primary.xml file.  
        # TODO: Need to investigate this.  Probably a build issue
        if 'VMware-hostd' in filename:
            if not os.path.getsize(filename) == self.pkgSize:
                log.error('Very strange!! filesize on disk != size in primary.xml file')
            return True
        return os.path.getsize(filename) == self.pkgSize

    def _getBasename(self):
        return os.path.basename(self.fullSrcPath)
    basename = property(_getBasename)

    def _downloadHeaderFragment(self):
        self._localLocation = downloadLocally(self.fullSrcPath,
                                              self._headerLength)
        self._header = self.readRPMHeader(self.localLocation)

    def ensureFileDownloaded(self):
        if self._finishedDownloading:
            return True
        self._localLocation = downloadLocally(self.fullSrcPath,
                                    integrityChecker=self.integrityChecker)
        self._finishedDownloading = True
        return True

    def deleteDownloadedFile(self):
        log.debug('Deleting temporary file %s' % self._localLocation)
        self._finishedDownloading = False
        os.remove(self._localLocation)
        self._localLocation = None


# -----------------------------------------------------------------------------
def hostActionInstallPackages(context):
    # since big RPM files may have to be downloaded, we must first change the
    # cache dir to one that's actually on the disk (ie, /mnt/sysimage/tmp)
    # instead of the ramdisk (ie, /tmp)
    cacher = getCacher()
    cacheDir = os.path.join(consts.HOST_ROOT, 'tmp/')
    if cacher.getCacheLocation() != cacheDir:
        assert os.path.exists(consts.HOST_ROOT)
        if not os.path.exists(cacheDir):
            os.makedirs(cacheDir)
        cacher.setCacheLocation(cacheDir, 'orphan')

    pkg = Packages(uiHook=context.cb)
    pkg.initializeDB()
    pkg.readPackages()

    rpmLog = open("/var/log/rpm.log", 'a+')
    try:
        # rpm.setVerbosity(rpm.RPMLOG_DEBUG)
        pkg.ts.scriptFd = rpmLog.fileno()
        rpm.setLogFile(rpmLog)
        pkg.installPackages()
    finally:
        rpmLog.flush()
        rpmLog.seek(0)

        log.debug("BEGIN rpm log ----")
        for line in rpmLog:
            log.debug("rpm: %s" % line.rstrip('\n'))
        log.debug("END rpm log ----")

        rpm.setLogFile(open("/dev/null", 'w+'))
        rpmLog.close()
        
    ts = getTransactionSet()
    ts.closeDB()

    # XXX - this should be removed after we switch to a 64 bit rpm
    workarounds.rebuildRpmDb()

def hostActionScanDiskForPackages():
    pass

