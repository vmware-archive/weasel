
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

import exception
import userchoices
import networking.utils
import urlparse
import urllib
import remote_files
from packages import checkMediaRootIsValid
from signalconnect import connectSignalHandlerByDict
from common_windows import MessageWindow

def parseFTPURL(url):
    # we know that the protocol is 'ftp', so just return the last elements
    return networking.utils.parseFileResourceURL(url)[1:]
    
def unparseFTPURL(*args):
    return networking.utils.unparseFileResourceURL('ftp', *args)

#------------------------------------------------------------------------------
class FTPInstallMediaWindow:
    SCREEN_NAME = 'ftpmedia'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'network_media.png'
        controlState.windowTitle = "File System (FTP) Installation"
        controlState.windowText = "Enter the FTP settings for the ESX " + \
                                  "installation media"

        self.xml = xml

        connectSignalHandlerByDict(self, FTPInstallMediaWindow, self.xml,
          { ('FtpProxyCheckButton', 'toggled'): 'toggleProxy',
            ('FtpProxyUserCheckButton', 'toggled'): 'toggleUserProxy',
            ('FtpNonAnonLoginCheckButton', 'toggled'): 'toggleNonAnonLogin',
          })
            
        self._setupUrl()

    def _setupUrl(self):
        # since the user name / password are encoded in the url, we
        # need to remove them here to set them up in the widgets correctly
        if not userchoices.getMediaLocation():
            return
        
        mediaURL = userchoices.getMediaLocation()['mediaLocation']
        username, password, host, port, path = parseFTPURL(mediaURL)

        displayURL = unparseFTPURL('', '', host, port, path)
        self.xml.get_widget('FtpUrlEntry').set_text(displayURL)
        self.xml.get_widget('FtpNonAnonLoginUserEntry').set_text(username)
        self.xml.get_widget('FtpNonAnonPasswordEntry').set_text(password)

    def getNext(self):
        url = self.xml.get_widget('FtpUrlEntry').get_text().strip()

        try:
            networking.utils.sanityCheckUrl(url, expectedProtocols=['ftp'])
        except ValueError, msg:
            MessageWindow(None, 'Invalid URL', msg[0])
            raise exception.StayOnScreen

        if self.xml.get_widget('FtpNonAnonLoginCheckButton').get_active():
            # encode the username and password into the url
            ftpUser = self.xml.get_widget('FtpNonAnonLoginUserEntry').get_text()
            ftpUser = ftpUser.strip()
            ftpPass = self.xml.get_widget('FtpNonAnonPasswordEntry').get_text()

            if not ftpUser or not ftpPass:
                MessageWindow(None, 'Invalid User name or Password',
                    'You need to specify a User name and password')
                raise exception.StayOnScreen

            urlUser, urlPass, host, port, path = parseFTPURL(url)
            
            if urlUser or urlPass:
                MessageWindow(None, 'Duplicate User name or Password',
                              'User name or password was specified twice')
                raise exception.StayOnScreen

            url = unparseFTPURL(ftpUser, ftpPass, host, port, path)

        if self.xml.get_widget('FtpProxyCheckButton').get_active():
            errors, proxy, port, proxyUser, proxyPass = self.getProxyValues()
            if errors:
                title, detail = errors[0]
                MessageWindow(None, title, detail)
                raise exception.StayOnScreen
            userchoices.setMediaProxy(proxy, port, proxyUser, proxyPass)
        else:
            userchoices.unsetMediaProxy()

        if not checkMediaRootIsValid(url):
            MessageWindow(None, 'Network Error',
                'There was an error trying to connect to the network server.')
            raise exception.StayOnScreen

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(url)


    def getProxyValues(self):
        '''Returns errors, proxy, port, proxyUser, proxyPass.
        errors - a list of (title, detail) tuples.  Empty if input was valid
        '''
        errors = []
        proxy = self.xml.get_widget('FtpProxyEntry').get_text().strip()
        port = self.xml.get_widget('FtpProxyPortEntry').get_text().strip()
        try:
            networking.utils.sanityCheckIPorHostname(proxy)
        except ValueError, msg:
            errors.append(('FTP Proxy Name Error', str(msg)))

        try:
            networking.utils.sanityCheckPortNumber(port)
        except ValueError, msg:
            errors.append(('FTP Proxy Port Number Error', str(msg)))

        if self.xml.get_widget('FtpProxyUserCheckButton').get_active():
            proxyUser = self.xml.get_widget('FtpProxyUsernameEntry').get_text()
            proxyUser = proxyUser.strip()
            proxyPass = self.xml.get_widget('FtpProxyPasswordEntry').get_text()

            if not proxyUser:
                errors.append(('Invalid user name',
                    'You need to specify a proxy user name and password'))
        else:
            proxyUser = ''
            proxyPass = ''

        return errors, proxy, port, proxyUser, proxyPass


    def toggleProxy(self, widget, *args):
        proxyTable = self.xml.get_widget('FtpProxyTable')
        proxyTable.set_sensitive(widget.get_active())

    def toggleNonAnonLogin(self, widget, *args):
        proxyTable = self.xml.get_widget('FtpNonAnonymousLoginTable')
        proxyTable.set_sensitive(widget.get_active())

    def toggleUserProxy(self, widget, *args):
        proxyTable = self.xml.get_widget('FtpProxyUserTable')
        proxyTable.set_sensitive(widget.get_active())

