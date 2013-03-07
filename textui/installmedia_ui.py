#!/usr/bin/env python
#-*- coding: utf-8 -*-

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

import re
import urllib
import userchoices
import remote_files
import media
import cdutil
import usbmedia
from log import log
from packages import checkMediaRootIsValid
import networking.utils as net_utils
import textengine       # for dispatch symbols
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

import networking.utils as netutils

title = "Install Media Selection"

askMediaChoiceText = """\
Choose the install media where ESX is located:
 1) CD-ROM or USB Storage
 2) Network File System (NFS)
 3) World Wide Web (HTTP)
 4) File Server (FTP)

Other actions:
 <) Back
 ?) Help

"""

usbDeviceText = """\
Select the ESX installation media:
%(medialist)s

Other action:
 <) Back
 ?) Help

"""

promptNfsServPathText = """\
Specify the Network File System (NFS) server and directory path
(or enter '<' to go back).

"""

promptHttpServText = """\
Specify the URL for the location of the ESX packages
(or enter '<' to go back).
Examples:
    http://myserver/path_to_packages_xml_dir
    https://myserver/isoroot

"""

promptFtpServText = """\
Specify the FTP location of the ESX packages.
(or enter '<' to go back).
(Non-anonymous user name and password will be prompted separately.)

"""

askProxyText = """\
Is a proxy server needed to access the server where the ESX
packages reside?
"""

promptProxyText = """\
Specify the name of the proxy server.
For example, proxy.mydomain.com
(The next screen will ask for a port number.)

"""

promptProxyPortText = """\
Specify the port number for the proxy server.

"""

askProxyUserText = """\
Does the proxy server require a user name and password?
"""

askNonAnonUserText = """\
Does the server require a user name and password?
"""

promptUserNamePasswordText = """\
Provide user name and password.

"""

promptProxyPortText = """\
Specify the port number for the proxy server.

"""

helpInstallMediaText = """\
Select one of the following install media:
  * CD-ROM (can be other than one currently in use)
  * USB storage or local hard drive 
  * Network File System (NFS) - server and directory path
  * World Wide Web (WWW) - HTTP or HTTPS
  * File Server (FTP)

WWW or FTP can go through a proxy server.
FTP may use an non-anonymous user and password.
"""

helpProxyText = """\
You may need to access installation files through a proxy server.
In that case, you will need the hostname or IP address of the proxy
server, and a port number.

For example, proxy.mydomain.com and port 8080.
"""

helpProxyUserText = """\
In some cases, accessing installation files through a proxy server may also
require a proxy user name and password.

Although the password is not visible in the installer session, it may be
visible on the network, depending on the protocol used.
"""

helpNonAnonUserText = """\
A user name and password may be required in some cases.

Although the password is not visible in the installer session, it may be
visible on the network, depending on the protocol used.
"""

usbHelpText = """\
Select the media to use for installing ESX.  Use 'rescan' to perform
another scan for packages and 'eject' with a number to eject the media.
"""

errNetConnectText = """\
Network Error
There was an error trying to connect to the network server.

"""

errNetLinkText = """\
Network Adapter Error
The network adapter must be connected in order to access
FTP, HTTP, or NFS sources.
"""

errMiscText =  """\
Error
There was an error requesting a file from the remote server.

"""

confirmMediaChoice = """\
Is the following information correct?

URL:   %(url)s
"""

proxyMediaChoice = """\
Proxy: %s"""

SCROLL_LIMIT = 20

# ================ InstallMediaWindow: The Top Class ================
class InstallMediaWindow(TextRunner):
    """Select an alternate installation media for ESX.
    """

    def __init__(self):
        super(InstallMediaWindow, self).__init__()
        self.start = self.askMediaChoice
        self.substep = self.start

        self.mediaLocation = userchoices.getMediaLocation()
        # TODO: populate existing state

    def askMediaChoice(self):
        "Initial step."
        ui = {
            'title': title,
            'body': askMediaChoiceText,
            'menu': {
                '1': self.setupUsb,
                '2': self.setupMedia,
                '3': self.setupMedia,
                '4': self.setupMedia,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def setupUsb(self):
        engine = SetupUsb()
        result = engine.run()

        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.stepForward})
        else:
            self.setSubstepEnv({'next': self.start})  # start of installmedia

    def setupMedia(self):
        """Set-up for currently implemented media.
        Includes:  NFS, HTTP, FTP.
        """
        setups = {     
            # engine is class for setup, tSuffix is title suffix.
            '2': {'engine': SetupNfs, 'tSuffix': "NFS"},
            '3': {'engine': SetupHttp, 'tSuffix': "HTTP"},
            '4': {'engine': SetupFtp, 'tSuffix': "FTP"},
        }
        # TODO: add title as parameter
        engineType = setups[self.userinput]['engine']
        title = 'Install Using ' + setups[self.userinput]['tSuffix']

        # check for network link
        chosenNics = userchoices.getCosNICs()
        assert len(chosenNics) == 1
        physicalNic = chosenNics[0]['device']

        if not physicalNic.isLinkUp:
            body = "%s\n%s" % (errNetLinkText, TransMenu.Back)
            self.errorPushPop(title, body)
            return

        engine = engineType(title)
        result = engine.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.stepForward})
        else:
            self.setSubstepEnv({'next': self.start})  # start of installmedia

    def help(self):
        "Emit help text."
        self.helpPushPop(title+' (Help)', helpInstallMediaText+TransMenu.Back)


# ================ USB ================
class SetupUsb(TextRunner):
    "Set-up for install media using USB."

    def __init__(self):
        super(SetupUsb, self).__init__()
        media.runtimeActionUnmountMedia()
        self.title = 'CD-ROM or USB Media'
        self.substep = self.start
        self.mediaFound = []
        self.rescan()

    def rescan(self):
        textengine.render({'body': 'Probing for installation media...'})
        self.mediaFound = (cdutil.findCdMedia(showAll=True) +
                           usbmedia.findUSBMedia(showAll=True))
        self.setSubstepEnv( {'next': self.start} )

    def start(self):
        mediaTextList = []
        for num, installMedia in enumerate(self.mediaFound):
            if not installMedia.hasPackages:
                contents = "No packages"
            elif installMedia.isoPath:
                contents = installMedia.isoPath
            else:
                contents = "Installation packages"
            mediaTextList.append("%2d) %s\n"
                                 "      Contents: %s\n"
                                 "      Version: %s" % (
                    num + 1,
                    installMedia.getName(),
                    contents,
                    installMedia.version))

        self.setScrollEnv(mediaTextList, SCROLL_LIMIT)
        self.setSubstepEnv({'next' : self.scrollDisplay})

    def scrollDisplay(self):
        self.buildScrollDisplay(self.scrollable,
                                self.title,
                                self.chooseDevice,
                                "<number>: media, 'rescan', 'eject <N>'",
                                allowStepBack=True,
                                allowStepRestart=True)

    def help(self):
        "Emit help text."
        self.helpPushPop(title+' (Help)', usbHelpText + TransMenu.Back)

    def chooseDevice(self):
        doEject = False
        
        textOption = self.userinput.strip().lower()
        if textOption == "rescan":
            self.setSubstepEnv( {'next': self.rescan} )
            return

        m = re.match(r'eject (\d+)', textOption)
        if m:
            self.userinput = m.group(1)
            doEject = True
            
        try:
            selected = self.getScrollChoice()
        except (IndexError, ValueError), msg:
            body = '\n'.join(['Input error', msg[0], TransMenu.Back])
            self.errorPushPop(self.title +' (Update)', body)
            return

        mediaDesc = self.mediaFound[selected]

        if doEject:
            mediaDesc.eject()
            self.setSubstepEnv( {'next': self.start} )
            return
        
        if mediaDesc.diskName:
            userchoices.addDriveUse(mediaDesc.diskName, 'media')
        userchoices.setMediaDescriptor(mediaDesc)
        userchoices.clearMediaLocation()

        try:
            mediaDesc.mount()
        except Exception, e:
            log.exception("unable to mount media")
            body = '\n'.join(['Unable to mount media.  '
                              'Rescan and select the media again',
                              TransMenu.Back])
            self.errorPushPop(self.title, body)
            return

        if not mediaDesc.hasPackages:
            body = '\n'.join(['Select a valid installation medium.',
                              TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        
        self.setSubstepEnv( {'next': self.stepForward } )


# ================ NFS ================
class SetupNfs(TextRunner):
    "Set-up for install media on Network File System (NFS)"

    def __init__(self, title):
        super(SetupNfs, self).__init__()
        self.start = self.getServer
        self.substep = self.start
        self.title = title

        self.serverName = None
        self.serverDir = None

    def getServer(self):
        ui = {
            'title': self.title,
            'body': promptNfsServPathText,
            'menu': {
                '*': self.checkServer,
                '<': self.stepBack, },
            'prompt': 'Server: ',
        }
        self.setSubstepEnv(ui)

    def checkServer(self):
        self.serverName = self.userinput
        try:
            net_utils.sanityCheckIPorHostname(self.serverName)
        except ValueError, msg:
            log.error(msg[0])
            body = '\n'.join(['NFS Server Name Error', msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.setSubstepEnv({'next': self.getPath})

    def getPath(self):
        ui = {
            'title': self.title,
            'body': promptNfsServPathText,
            'menu': {
                '*': self.checkPath,
                '<': self.stepBack, },
            'prompt': 'Directory: ',
        }
        self.setSubstepEnv(ui)

    def checkPath(self):
        self.serverDir = self.userinput
        if not self.serverDir.startswith('/'):
            self.serverDir = '/' + self.serverDir

        self.setSubstepEnv({'next': self.confirmSettings})

    def confirmSettings(self):
        ui = {
            'title': self.title,
            'body': confirmMediaChoice % {'url': self.serverName + \
                                                 self.serverDir} \
                    + TransMenu.YesNoBack,
            'menu': {
                '1': self.commit,
                '2': self.stepBack,
                '<': self.stepBack
            }
        }
        self.setSubstepEnv(ui)

    def commit(self):
        url = 'nfs://%s%s' % (self.serverName, self.serverDir)
        if not checkMediaRootIsValid(url):
            log.error('NFS textui failed on %s' % url)
            body = "%s\n%s" % (errNetConnectText, TransMenu.Back)
            self.errorPushPop(self.title, body)
            return

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(url)
        self.setSubstepEnv({'next': self.stepForward})
        # WE'RE DONE


# ================ HTTP ================
class SetupHttp(TextRunner):
    """Set-up for install media on World Wide Web via
    Hypertext Transfer Protocol (HTTP)
    """

    def __init__(self, title):
        super(SetupHttp, self).__init__()
        self.start = self.getHostURL
        self.substep = self.start
        self.title = title

    # -------- host --------
    def getHostURL(self):
        ui = {
            'title': self.title,
            'body': promptHttpServText,
            'menu': {
                '*': self.checkHostURL,
                '<': self.stepBack, },
        }
        self.setSubstepEnv(ui)

    def checkHostURL(self):
        self.url = self.userinput
        try:
            net_utils.sanityCheckUrl(self.url,
                                     expectedProtocols=['http', 'https'])
        except ValueError, msg:
            log.error(msg[0])
            body = '\n'.join(['Invalid URL', msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.setSubstepEnv({'next': self.askProxy})

    # -------- check for proxy --------
    def askProxy(self):
        userchoices.unsetMediaProxy()
        ui = {
            'title': self.title,
            'body': askProxyText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.doProxy,
                '2': self.confirmSettings,
                '<': self.start,
                '?': self.helpProxy,
            }
        }
        self.setSubstepEnv(ui)

    def doProxy(self):
        proxy = SetupProxy(self.title, 'HTTP')
        result = proxy.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.confirmSettings})
        else:
            self.setSubstepEnv({'next': self.start})  # start of installmedia

    # -------- general stuff + commit --------

    def confirmSettings(self):
        confirmText = confirmMediaChoice % {'url': self.url}

        try:
            mediaProxy = userchoices.getMediaProxy()
            proxyURL = mediaProxy['server'] + ':' + mediaProxy['port'] + '\n'
            proxyText = proxyMediaChoice % proxyURL
            confirmText += proxyText
        except KeyError:
            pass

        ui = {
            'title': self.title,
            'body': confirmText + TransMenu.YesNoBack,
            'menu': {
                '1': self.commit,
                '2': self.stepBack,
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    def commit(self):
        if not checkMediaRootIsValid(self.url):
            log.error('HTTP textui failed on %s' % self.url)
            body = "%s\n%s" % (errNetConnectText, TransMenu.Back)
            self.errorPushPop(self.title, body)
            return

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(self.url)
        self.setSubstepEnv({'next': self.stepForward})

    def helpProxy(self):
        "Emit help text."
        self.helpPushPop(self.title+' (Help)', helpProxyText + TransMenu.Back)


# ================ FTP ================
class SetupFtp(TextRunner):
    "Set-up for install media on FTP."

    def __init__(self, title):
        super(SetupFtp, self).__init__()
        self.start = self.getHostURL
        self.substep = self.start
        self.title = title
        self.nonanonUser = ''
        self.nonanonPass = ''

    def getHostURL(self):
        ui = {
            'title': self.title,
            'body': promptFtpServText,
            'menu': {
                '*': self.checkHostURL,
                '<': self.stepBack, },
            'prompt': 'ftp://',
        }
        self.setSubstepEnv(ui)

    def checkHostURL(self):
        self.hostpath = self.userinput
        self.url = "ftp://" + self.hostpath  # if no non-anon user, this is it.
        try:
            net_utils.sanityCheckUrl(self.url, expectedProtocols=['ftp'])
        except ValueError, msg:
            log.error(msg[0])
            body = '\n'.join(['Invalid URL', msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.setSubstepEnv({'next': self.askNonAnonUser})

    # -------- non-anonymous user --------

    def askNonAnonUser(self):
        ui = {
            'title': self.title,
            'body': askNonAnonUserText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.doNonAnonUser,
                '2': self.askProxy,
                '<': self.start,
                '?': self.helpNonAnonUser,
            }
        }
        self.setSubstepEnv(ui)

    def doNonAnonUser(self):
        userinfo = SetupUserInfo(self.title + ' (Non-Anonymous User)')
        result = userinfo.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_BACK:
            self.setSubstepEnv({'next': self.start})
            return

        self.nonanonUser, self.nonanonPass = userinfo.getInfo()
        encodedUser = urllib.quote(self.nonanonUser, '')
        encodedPass = urllib.quote(self.nonanonPass, '')
        self.url = "ftp://%s:%s@%s" % (encodedUser, encodedPass, self.hostpath)
        self.setSubstepEnv({'next': self.askProxy})

    # -------- check for proxy --------
    def askProxy(self):
        userchoices.unsetMediaProxy()
        ui = {
            'title': self.title,
            'body': askProxyText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.doProxy,
                '2': self.confirmSettings,
                '<': self.start,
                '?': self.helpProxy,
            }
        }
        self.setSubstepEnv(ui)

    def doProxy(self):
        proxy = SetupProxy(self.title, 'FTP')
        result = proxy.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.confirmSettings})
        else:
            self.setSubstepEnv({'next': self.start})  # start of installmedia

    # -------- general stuff + commit --------

    def confirmSettings(self):
        confirmText = confirmMediaChoice % \
                      {'url': netutils.cookPasswordInFileResourceURL(self.url)}

        try:
            mediaProxy = userchoices.getMediaProxy()
            proxyURL = mediaProxy['server'] + ':' + mediaProxy['port'] + '\n'
            proxyText = proxyMediaChoice % proxyURL
            confirmText += proxyText
        except KeyError:
            pass

        ui = {
            'title': self.title,
            'body': confirmText + TransMenu.YesNoBack,
            'menu': {
                '1': self.commit,
                '2': self.stepBack,
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    def commit(self):
        if not checkMediaRootIsValid(self.url):
            log.error('FTP textui failed on %s' % self.url)
            body = "%s\n%s" % (errNetConnectText, TransMenu.Back)
            self.errorPushPop(self.title, body)
            return

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(self.url)
        self.setSubstepEnv({'next': self.stepForward})

    def helpNonAnonUser(self):
        "Emit help text for non-anonymous user."
        self.helpPushPop(self.title+' (Help)',
                         helpNonAnonUserText + TransMenu.Back)

    def helpProxy(self):
        "Emit help text for proxy."
        self.helpPushPop(self.title+' (Help)',
                         helpProxyText + TransMenu.Back)


# ================ User Info ================
class SetupUserInfo(TextRunner):
    """Query user name and password.
    Used to get proxy user and FTP anonymous user info.
    """

    def __init__(self, title):
        super(SetupUserInfo, self).__init__()
        self.start = self.getUserName
        self.substep = self.start
        self.title = title

    def getInfo(self):
        """Allow parent to retrieve user info after dialog is
        completed."""
        return (self.userName, self.password)

    def getUserName(self):
        ui = {
            'title': self.title,
            'body': promptUserNamePasswordText,
            'menu': {
                '*': self.saveUserName,
                '<': self.stepBack, },
            'prompt': 'User name: '
        }
        self.setSubstepEnv(ui)

    def saveUserName(self):
        self.userName = self.userinput.strip()
        self.setSubstepEnv({'next': self.getPassword})

    def getPassword(self):
        ui = {
            'title': self.title,
            'body': promptUserNamePasswordText,
            'menu': {
                '*': self.savePassword,
                '<': self.stepBack, },
            'input': 'passwords',
            'short': ['<','?']
        }
        self.setSubstepEnv(ui)

    def savePassword(self):
        trial1, trial2 = self.userinput
        try:
            if trial1 != trial2:
                raise ValueError, "The two passwords entered do not match."
        except ValueError, msg:
            body = '\n'.join(['Password Input Error', msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.password = trial1
        self.setSubstepEnv({'next': self.checkUserNamePassword})

    def checkUserNamePassword(self):
        if not self.userName or not self.password:
            msg = "User name or password was empty."
            body = '\n'.join([msg, TransMenu.Back])
            ui = {
                'title': self.title,
                'body': body,
                'menu': {'*': self.getUserName},
            }
            self.setSubstepEnv(ui)
            return
        self.setSubstepEnv({'next': self.done})

    def done(self):
        self.setSubstepEnv({'next': self.stepForward})


# ================ Proxy Server ================
class SetupProxy(TextRunner):
    "Setup for proxy server."

    def __init__(self, parentTitle, parentWord):
        super(SetupProxy, self).__init__()
        self.start = self.getProxy
        self.substep = self.start
        self.title = parentTitle + ' (Proxy)'
        self.parentWord = parentWord

        self.proxyUser = ''
        self.proxyPass = ''

        self.proxy = None
        self.port = None

    def getProxy(self):
        ui = {
            'title': self.title,
            'body': promptProxyText,
            'menu': {
                '*': self.checkProxy,
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    def checkProxy(self):
        proxy = self.userinput
        try:
            net_utils.sanityCheckIPorHostname(proxy)
        except ValueError, msg:
            log.error(msg[0])
            subtitle = "%s Proxy Name Error" % self.parentWord
            body = '\n'.join([subtitle, msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.proxy = proxy
        self.setSubstepEnv({'next': self.getProxyPort})

    def getProxyPort(self):
        ui = {
            'title': self.title,
            'body': promptProxyPortText,
            'menu': {
                '*': self.checkProxyPort,
                '<': self.stepBack, },
        }
        self.setSubstepEnv(ui)

    def checkProxyPort(self):
        port = self.userinput
        try:
            net_utils.sanityCheckPortNumber(port)
        except ValueError, msg:
            log.error(msg[0])
            body = msg[0] + '\n' + TransMenu.Back
            subtitle = "%s Proxy Port Number Error" % self.parentWord
            body = '\n'.join([subtitle, msg[0], TransMenu.Back])
            self.errorPushPop(self.title, body)
            return
        self.port = port
        self.setSubstepEnv({'next': self.askProxyUser})

    def askProxyUser(self):
        ui = {
            'title': self.title,
            'body': askProxyUserText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.doProxyUser,
                '2': self.commit,
                '<': self.start,
                '?': self.helpProxyUser,
            }
        }
        self.setSubstepEnv(ui)

    def doProxyUser(self):
        userinfo = SetupUserInfo(self.title)
        result = userinfo.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_BACK:
            self.setSubstepEnv({'next': self.start})
            return

        self.proxyUser, self.proxyPass = userinfo.getInfo()
        self.setSubstepEnv({'next': self.commit})


    def commit(self):
        "Commit proxy info to userchoices."
        userchoices.setMediaProxy(self.proxy, self.port,
                self.proxyUser, self.proxyPass)
        self.setSubstepEnv({'next': self.stepForward})

    def helpProxyUser(self):
        self.helpPushPop(title+' (Help)', helpProxyUserText + TransMenu.Back)


# vim: set sw=4 tw=80 :
