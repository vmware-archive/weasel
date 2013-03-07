
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

import userchoices
import exception
import networking.utils

from packages import checkMediaRootIsValid
from log import log
from common_windows import MessageWindow

class NFSInstallMediaWindow:
    SCREEN_NAME = 'nfsmedia'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'network_media.png'
        controlState.windowTitle = "Network Filesystem (NFS) Installation"
        controlState.windowText = \
            "Enter the Network File System (NFS) server and path of the " + \
            "ESX installation media"

        self.xml = xml

        self._setupUrl()

    def _setupUrl(self):
        if not userchoices.getMediaLocation():
            return

        url = userchoices.getMediaLocation()['mediaLocation']
        protocol, user, passwd, host, port, path =\
                                    networking.utils.parseFileResourceURL(url)

        self.xml.get_widget('NfsServerEntry').set_text(host)
        self.xml.get_widget('NfsDirectoryEntry').set_text(path)

    def getNext(self):
        serverName = self.xml.get_widget('NfsServerEntry').get_text().strip()
        serverDir = self.xml.get_widget('NfsDirectoryEntry').get_text().strip()

        if not serverDir:
            MessageWindow(None, 'NFS Server Directory Error',
                          'NFS server directory must not be empty')
            raise exception.StayOnScreen

        if not serverDir.startswith('/'):
            serverDir = '/' + serverDir

        try:
            networking.utils.sanityCheckIPorHostname(serverName)
        except ValueError, msg:
            MessageWindow(None, 'NFS Server Name Error', msg[0])
            raise exception.StayOnScreen

        url = 'nfs://%s%s' % (serverName, serverDir)

        if not checkMediaRootIsValid(url):
            MessageWindow(None, 'Network Error',
                'There was an error trying to connect to the network server.')
            raise exception.StayOnScreen

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(url)

