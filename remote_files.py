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

'''
remote_files

Convenience functions to deal with remote files.

This module knows that weasel is running and that the root filesystem
is in RAM, which will be limited, so we can't assume we can just download
every single file and dump them in /tmp. (there should be at least
1GB of physical memory, seeing as we're installing ESX. Check the
isolinux.cfg file to see if it sets some other maximum)
'''
import os
import shutil
import socket
import errno
import consts
import logging
import util
from time import sleep
from urllib2 import Request, urlopen, URLError, HTTPError
import urlparse
# !!!
# the urlparse that ships with python2.4 does not support nfs URLs.  That
# is, it does not recognize nfs urls as the kind of url that have a 
# network location component or as the kind that allow relative paths in
# the path part.  By changing this, any other file that imports urlparse 
# will be affected.
urlparse.uses_netloc.append('nfs')
urlparse.uses_relative.append('nfs')
# !!!

from log import log
from util import execCommand, execWithLog
import userchoices
import networking

NFS_MOUNTPOINT = '/mnt/nfs'

class RemoteFileError(Exception): pass

__cacher = None
#------------------------------------------------------------------------------
def getCacher():
    '''factory function'''
    global __cacher
    if not __cacher:
        __cacher = Cacher()
    return __cacher

#------------------------------------------------------------------------------
class Cacher(object):
    def __init__(self):
        self._cacheLocation = '/tmp/'
        if not os.path.exists(self._cacheLocation):
            raise RemoteFileError('Cacher error: /tmp/ does not exist')
        self._urlToLocalLocation = {}
        self._midstreamFiles = {}
        self._completedFiles = {}

    def getCacheLocation(self):
        return self._cacheLocation

    def setCacheLocation(self, dirpath, oldFileAction):
        '''Change the directory where cached files are stored.
        oldFileAction is a required string argument:
          'move' means copy all the previously cached files to the new dir
          'delete' means delete all the previously cached files
          'orphan' means leave the previously cached files where they are, but
                   they will not be usable by the Cacher in the future.
        raises RemoteFileError if the dir path does not exist.
        '''
        if not os.path.exists(dirpath):
            raise RemoteFileError('Directory does not exist: %s' % dirpath)

        self._cacheLocation = dirpath

        newMidstreamFiles = {}
        newCompletedFiles = {}
        newUrlToLocalLocation = {}
        for url, filepath in self._urlToLocalLocation.items():
            if oldFileAction == 'move':
                shutil.move(filepath, dirpath)
                filename = os.path.basename(filepath)
                newLocalLocation = os.path.join(dirpath, filename)
                newUrlToLocalLocation[url] = newLocalLocation
                if url in self._completedFiles:
                    newCompletedFiles[url] = newLocalLocation
                if url in self._midstreamFiles:
                    newMidstreamFiles[url] = newLocalLocation
            elif oldFileAction == 'delete':
                os.remove(filepath)
            elif oldFileAction == 'orphan':
                pass
            else:
                raise ValueError('Got invalid value (%s) for oldFileAction'
                                 % oldFileAction)
        self._midstreamFiles = newMidstreamFiles
        self._completedFiles = newCompletedFiles
        self._urlToLocalLocation = newUrlToLocalLocation

    def getLocalLocation(self, url):
        if url in self._urlToLocalLocation:
            return self._urlToLocalLocation[url]

        # we know our OS uses posix paths, so basename() will work
        basename = os.path.basename(url)
        tmpPath = os.path.join(self._cacheLocation, basename)
        return tmpPath

    def checkFileExists(self, url):
        if os.path.exists(self._urlToLocalLocation[url]):
            return True
        # it may have been deleted from under our noses
        self.clobber(url)
        return False

    def isComplete(self, url):
        if url in self._completedFiles:
            if self.checkFileExists(url):
                return True
        return False

    def setComplete(self, url):
        self._completedFiles[url] = self.getLocalLocation(url)
        if url in self._midstreamFiles:
            del self._midstreamFiles[url]

    def cachedCopy(self, url, default=None):
        if url in self._urlToLocalLocation:
            if self.checkFileExists(url):
                return self._urlToLocalLocation[url]
        return default

    def remoteClose(self, url, localFile):
        try:
            localFile.close()
        except IOError, ex:
            msg = 'IOError during local close of %s (%s)' % (url, str(ex))
            log.error(msg)
        if url in self._midstreamFiles:
            try:
                self._midstreamFiles[url].close()
            except IOError, ex:
                msg = 'IOError during remote close of %s (%s)' % (url, str(ex))
                log.error(msg)
            del self._midstreamFiles[url]

    def remoteOpen(self, url):
        #TODO: resolve the confusing naming with module-level remoteOpen
        '''It is the responsibility of the caller to close localFile and
        remoteFile.  That can be achieved by calling
        remoteClose(url, localFile)'''
        tmpPath = self.getLocalLocation(url)

        if url in self._midstreamFiles:
            localFile = open(tmpPath, 'ab')
            return self._midstreamFiles[url], localFile

        self._urlToLocalLocation[url] = tmpPath
        localFile = open(tmpPath, 'wb')
        remoteFile = remoteOpen(url)
        self._midstreamFiles[url] = remoteFile
        return remoteFile, localFile

    def clobber(self, url):
        log.debug('Cacher is clobbering %s' % url)
        if url in self._urlToLocalLocation:
            try:
                os.remove(self._urlToLocalLocation[url])
            except OSError, ex:
                if ex.errno != errno.ENOENT:
                    log.warn('Error deleting cached file during clobber')
                    log.warn(str(ex))
        try:
            del self._urlToLocalLocation[url]
        except KeyError:
            pass
        try:
            del self._completedFiles[url]
        except KeyError:
            pass
        try:
            self._midstreamFiles[url].close()
            del self._midstreamFiles[url]
        except KeyError:
            pass


__nfsMounter = None
#------------------------------------------------------------------------------
def getNFSMounter():
    '''factory function'''
    global __nfsMounter
    if not __nfsMounter:
        __nfsMounter = NFSMounter(NFS_MOUNTPOINT)
    return __nfsMounter

#------------------------------------------------------------------------------
class NFSMounter(object):
    '''The NFSMounter object can split nfs URLs like
    nfs://example.com/remote/exported/sub/path/ into 3 pieces of data:
    "example.com", the host,
    "/remote/exported/", the root exported directory, and
    "sub/path/", the subdirectory underneath the root exported directory.
    With this data, the NFSMounter can mount /remote/exported to the local
    directory /mnt/nfs.  It can then access the remote files with the local
    path /mnt/nfs/sub/path/...
    '''
    _nfsUp = False
    def __init__(self, mountpoint):
        self.mountedServer = None
        self.mountedRoot = None
        self.mountpoint = mountpoint
        if not os.path.exists(self.mountpoint):
            os.makedirs(self.mountpoint)

    def _checkNFSAvailable(self):
        if NFSMounter._nfsUp:
            return NFSMounter._nfsUp

        #TODO: this needs to change once these get sourced differently in scons
        execCommand('insmod /lib/sunrpc.ko')
        execCommand('insmod /lib/nfs_acl.ko')
        execCommand('insmod /lib/lockd.ko')
        execCommand('insmod /lib/nfs.ko')

        if not os.path.exists('/var/lock/subsys'):
            os.makedirs('/var/lock/subsys')
        NFSMounter._nfsUp = True
        return NFSMounter._nfsUp

    def getLocalLocation(self, url):
        '''
        assume the url points to a file, not a directory, so that the
        call to dirname makes sense
        '''
        self._checkNFSAvailable()
        host, fullDir, fname = self.parseURL(url)

        if not self.alreadyMounted(url):
            log.info('NFS source was not already mounted.  Mounting...')
            possibleRoots = self.getPossibleRoots(fullDir)
            success = False
            for possibleRoot in possibleRoots:
                # self.mount will set self.mountedRoot
                if self.mount(host, possibleRoot):
                    success = True
                    break
            if not success:
                raise Exception('NFS mount failure for URL %s' % url)

        normedMountedRoot = os.path.normpath(self.mountedRoot)
        subdir = fullDir.replace(normedMountedRoot, '', 1)
        subdir = subdir.lstrip('/')
        return os.path.join(self.mountpoint, subdir, fname)

    def unmount(self):
        if self.mountedServer:
            # Use the nfs specific umount, since the busybox one does not work
            # well with unreachable nfs servers.
            nfsMountPoint = self.mountpoint
            if self.mountedRoot.endswith('.iso'):
                util.umount(self.mountpoint)
                nfsMountPoint = "%s-isosrc" % self.mountpoint
            command = '/sbin/umount.nfs'
            argv = [command, nfsMountPoint, '-f']
            execWithLog(command, argv, level=logging.DEBUG)
        self.mountedServer = None
        self.mountedRoot = None

    def mount(self, host, root, options="nolock"):
        self._checkNFSAvailable()
        self.unmount()

        nfsMountPoint = self.mountpoint
        nfsRoot = root
        
        isoName = None
        if root.endswith('.iso'):
            nfsRoot, isoName = os.path.split(root)
            nfsMountPoint = "%s-isosrc" % self.mountpoint
            if not os.path.exists(nfsMountPoint):
                os.makedirs(nfsMountPoint)
                
        command = '/sbin/mount.nfs'
        argv = [command, '%s:%s' % (host, nfsRoot), nfsMountPoint,
                '-v', '-o', options]
        rc = execWithLog(command, argv)
        
        if rc == 0:
            self.mountedServer = host
            self.mountedRoot = root
            if isoName:
                if util.mount(os.path.join(nfsMountPoint, isoName),
                              self.mountpoint,
                              loopMount=True,
                              fsTypeName='iso9660') != 0:
                    self.unmount()
                    return False
            return True
        else:
            return False

    def alreadyMounted(self, url):
        if not (self.mountedServer and self.mountedRoot):
            return False
        host, fullDir, fname = self.parseURL(url)
        if host != self.mountedServer:
            return False
        if not fullDir.startswith(self.mountedRoot):
            return False
        return True

    def parseURL(self, url):
        '''Extracts the host, the full directory, and the filename from
        the URL.  Returns those elements in a tuple.
        The returned directory path will be normpathed.
        Also, this would be where the "/" characters of the URL would
        get turned into os.path.sep characters, if that were necessary.
        It's not, but after calling parseURL, you can breathe easy and
        treat the directory path as though it is an os.path.
        '''
        # Assumption: NFS URLs don't have users, passwords, or ports
        result = urlparse.urlparse(url)
        # We have to unpack like this because the python 2.4 version of
        # urlparse doesn't return an object with friendly keys or attributes
        protocol, host, fullpath, _unused, _unused, _unused = result
        assert protocol == 'nfs'
        fullpath = os.path.normpath(fullpath)
        fullDir, fname = os.path.split(fullpath)
        fullDir = self.customNormpath(fullDir)
        log.debug('NFS URL %s parsed into %s %s %s' 
                  % (url, host, fullDir, fname))
        return host, fullDir, fname

    def customNormpath(self, path):
        '''Like os.path.normpath, but it also strips any leading slashes,
        and it doesn't work on empty strings'''
        assert path != ''
        slash = os.path.sep
        path = os.path.normpath(path)
        if path.startswith(slash):
            # os.path.normpath might leave multiple leading slashes
            path = path.lstrip(slash) #remove leading slash(es)
            path = slash + path #now it has just one leading slash
        return path


    def getPossibleRoots(self, fullDir, deepestToShallowest=True):
        '''Given a directory, return the possible NFS exported roots
        >>> getPossibleRoots('/a/b/c')
        ['/a/b/c', '/a/b', '/a', '/']
        >>> getPossibleRoots('/a/b/c', deepestToShallowest=False)
        ['/', '/a', '/a/b', '/a/b/c']
        >>> getPossibleRoots('/a/b/c.iso/foo/bar')
        ['/a/b/c.iso']
        '''
        slash = os.path.sep
        if fullDir == slash:
            return [fullDir]

        possibleRoot = ''
        possibleRoots = [slash]
        for dirname in fullDir.lstrip(slash).split(slash):
            possibleRoot += slash + dirname
            if dirname.endswith('.iso'):
                return [possibleRoot]
            possibleRoots.append(possibleRoot)

        if deepestToShallowest:
            # reversing results in less mounting / unmounting in Weasel
            # (packages.xml is the first requested file, and everything
            #  is usually in a directory underneath that)
            possibleRoots.reverse()
        return possibleRoots



#------------------------------------------------------------------------------
def URLify(localPath):
    '''Turn a local path into a file URL.  This is useful to ensure that
    a "local" file on the CD (which may in fact be hosted over the network)
    gets treated like a URL.  ie, it is used to ensure that the file gets
    downloaded to /mnt/sysimage
    '''
    if isURL(localPath):
        return localPath
    return 'file://' + localPath

#------------------------------------------------------------------------------
def isURL(candidate):
    return '://' in candidate


#------------------------------------------------------------------------------
def openFileURL(url):
    filePath = url[7:]

    if filePath.startswith(consts.MEDIA_DEVICE_MOUNT_POINT):
        import media # Import here to avoid a loop.
        media.runtimeActionMountMedia()
    
    if not filePath.startswith('/'):
        log.warn('Do not support hosts specified in file:// URLs')
        log.warn('Assuming the user meant to put in a third /')
        filePath = '/' + filePath
    try:
        return open(filePath)
    except IOError, ex:
        log.error('File %s specified in URL %s could not be opened (%s)'
                  % (filePath, url, str(ex)))
        raise

#------------------------------------------------------------------------------
def checkNetworkUp():
    if networking.connected():
        return True
    try:
        networking.cosConnectForInstaller(failOnWarnings=False,
                                          onlyConfiguredNics=False)
    except networking.WrappedVmkctlException, ex:
        log.info('got WrappedVmkctlException (%s %s)' % (ex, ex.msg))
        #TODO: this needs to be fixed in vmkctl
        if 'returned with non-zero status' in ex.msg:
            log.warn('harmless exception '+ ex.msg)
        else:
            log.error('not a harmless exception '+ ex.msg)
            raise
    return True

#------------------------------------------------------------------------------
_activeProxySettings = {}
def checkProxySetUp():
    global _activeProxySettings
    proxyChoices = userchoices.getMediaProxy()
    if proxyChoices == _activeProxySettings:
        #if the proxy is already set as specified, or is not set, do nothing
        return
    _activeProxySettings = proxyChoices #works because userchoices made a copy

    if proxyChoices:
        networking.config.setupProxy(proxyChoices['server'],
                                     proxyChoices['port'],
                                     proxyChoices['username'],
                                     proxyChoices['password'],
                                    )
        networking.config.useProxy = True
    else:
        networking.config.useProxy = False
        

#------------------------------------------------------------------------------
def openHTTPURL(url):
    if '*' in url:
        log.error('WILDCARDS NOT ALLOWED FOR HTTP MEDIA. FIXME')
        log.error('WILDCARD URL: %s' % url)
        return
    try:
        checkNetworkUp()
    except Exception, ex:
        log.error('A network connection could not be made to fetch %s' % url)
        raise

    checkProxySetUp()

    httpErrorMsg = ('The remote server responded with an HTTP Error (%s) while'
                    ' requesting %s.')
    urlErrorMsg = ('The remote server could not be reached while requesting %s.'
                   '  Error: %s')
    otherErrorMsg = ('There was a problem requesting %s from the remote server.'
                     '  Error: %s')

    cookedUrl = networking.utils.cookPasswordInFileResourceURL(url)
    log.info('Connecting to the remote file %s' % cookedUrl)
    req = Request(url)
    for attempt in range(1, 4): #must not be empty or attempt will be undefined
        if attempt > 1:
            log.info('Making another attempt (%d)' % attempt)
        try:
            return urlopen(req)
        except HTTPError, ex:
            msg = httpErrorMsg % (str(ex), url)
            if ex.geturl() != url:
                msg += ' (Redirected to %s)' % ex.geturl()
            log.error(msg)
        except URLError, ex:
            log.error(urlErrorMsg % (url, str(ex)))
        except Exception, ex:
            log.error(otherErrorMsg % (url, str(ex)))
        sleep(2)
    log.error('File connection failed. Made %d attempts.' % attempt)
    raise ex

#------------------------------------------------------------------------------
def openNFSURL(url):
    try:
        checkNetworkUp()
    except Exception, ex:
        log.error('A network connection could not be made to fetch %s' % url)
        raise
    try:
        mounter = getNFSMounter()
        localLocation = mounter.getLocalLocation(url)
        return open(localLocation)
    except Exception, ex:
        log.error('Could not open file over NFS %s' % url)
        log.error('Exception: %s' % str(ex))
        raise


#------------------------------------------------------------------------------
#TODO: change the name to retrieveFile
def downloadLocally(url, requestAmount=None, clobberCache=False,
                    integrityChecker=None, maxAttempts=None):
    '''Downloads a file and returns the path to the local copy
    Arguments:
    requestAmount    - specifies how much more to download, in bytes. This
                       value is used as guidance, the actual amount downloaded
                       may be more or less (less only in the case of a
                       completed download).
    clobberCache     - Boolean. Specifies to not use the cached copy.
    integrityChecker - Callable. Optionally specify this to check if the
                       file has downloaded properly.  It should be a
                       function of the form:
                       integrityChecker(filename) -> bool
    maxAttempts      - How many times to attempt to download the file. If left
                       as None, this function will try to choose a good value
                       based on the type of URL.
    '''
    cacher = getCacher()
    if clobberCache:
        cacher.clobber(url)
    if cacher.cachedCopy(url):
        if cacher.isComplete(url):
            return cacher.cachedCopy(url)

    tmpPath = cacher.getLocalLocation(url)

    chunkSize = 100*1024 #100 kilobytes
    if requestAmount:
        if os.path.exists(tmpPath):
            amountDownloaded = os.path.getsize(tmpPath)
        else:
            amountDownloaded = 0
        targetAmount = amountDownloaded + requestAmount

    class IntentionalShortRead(Exception): pass #for breaking out of the loop
    class SocketEmpty(Exception): pass #for breaking out of the loop

    if maxAttempts == None:
        if url.startswith('file://') or url.startswith('nfs://'):
            maxAttempts = 2
        else: #http, https, ftp
            maxAttempts = 3
    if maxAttempts < 1:
        raise ValueError('maxAttempts must be 1 or greater')
        
    for attempt in range(1, maxAttempts+1):
        if attempt > 1:
            sleep(2)
        try:
            remoteFile, localFile = cacher.remoteOpen(url)
        except (HTTPError, URLError), ex:
            log.warn('Connection / HTTP error while downloading.')
            log.warn('Exception: %s' % str(ex))
            continue
        try:
            log.debug('Downloading file %s (attempt %d)' % (url, attempt))
            while True:
                chunk = remoteFile.read(chunkSize)
                localFile.write(chunk)
                if len(chunk) < chunkSize:
                    # either the download is done, or there was a short read
                    raise SocketEmpty()
                if requestAmount:
                    amountDownloaded += len(chunk)
                    if amountDownloaded >= targetAmount:
                        raise IntentionalShortRead()
        except SocketEmpty:
            cacher.remoteClose(url, localFile)
            remoteFile.close()
            if integrityChecker and not integrityChecker(tmpPath):
                log.warn('Apparent short read of file %s' % url)
                cacher.clobber(url)
                continue # try another attempt
            cacher.setComplete(url)
            break # successful download - no more attempts needed
        except IntentionalShortRead:
            cacher.remoteClose(url, localFile)
            remoteFile.close()
            break # successful partial download - no more attempts needed
        except (HTTPError, URLError, IOError, socket.error), ex:
            cacher.remoteClose(url, localFile)
            log.warn('Connection / HTTP error while downloading.')
            log.warn('Exception: %s' % str(ex))
    else:
        # the for loop didn't break
        msg = 'Could not download %s in %d attempts' % (url, attempt)
        log.error(msg)
        raise RemoteFileError(msg)

    return tmpPath


#------------------------------------------------------------------------------
def remoteOpen(url):
    '''Treat this like you would a call to open().  The return value is an
    open file-like object.  It is the caller's responsibility to close().
    '''
    if url.startswith('file://'):
        return openFileURL(url)
    elif url.startswith('http://'):
        return openHTTPURL(url)
    elif url.startswith('https://'):
        return openHTTPURL(url)
    elif url.startswith('ftp://'):
        return openHTTPURL(url)
    elif url.startswith('nfs://'):
        return openNFSURL(url)
    else:
        msg = ('URL scheme not supported for URL %s. Supported URL schemes'
               ' are file://, http://, https://, ftp://, nfs://.' % url)
        log.error(msg)
        raise RemoteFileError(msg)

def tidyAction():
    if __nfsMounter:
        getNFSMounter().unmount()
