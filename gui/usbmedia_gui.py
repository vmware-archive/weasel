
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

import gtk
import gobject

import util
import media
import cdutil
import usbmedia
import exception
import userchoices

from log import log
from storage_widgets import DEVMODEL_LENGTH
from common_windows import MessageWindow

from common_windows import populateViewColumns
from signalconnect import connectSignalHandlerByDict

MEDIA_ENTRY = 3

class USBInstallMediaWindow:
    SCREEN_NAME = 'usbmedia'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'usb_cd_media.png'
        controlState.windowTitle = "CD-ROM or USB Installation"
        controlState.windowText = "Select the ESX installation source"

        connectSignalHandlerByDict(self, USBInstallMediaWindow, xml,
          { ('UsbRescan', 'clicked') : 'rescanMedia',
            ('UsbEject', 'clicked') : 'ejectMedia',
            })

        # Unmount any old media.
        media.runtimeActionUnmountMedia()
        
        self.mediaFound = []
        self.view = xml.get_widget("UsbMediaView")
        self.model = gtk.TreeStore(gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_PYOBJECT,
                                   gobject.TYPE_STRING)
        self.view.set_model(self.model)

        mediaViewColumns = (
            ("Device", 200),
            ("Contents", 150),
            ("ESX Version", 120),
            )

        if not self.view.get_columns():
            populateViewColumns(self.view, mediaViewColumns, foreground=4)

        self.rescanMedia()

    def rescanMedia(self, *_args):
        """Do a scan for any attached installation media."""
        selectedMedia = userchoices.getMediaDescriptor()
        
        self.mediaFound = (cdutil.findCdMedia(showAll=True) +
                           usbmedia.findUSBMedia(showAll=True))

        self.model.clear()
        for installMedia in self.mediaFound:
            foreground = "#000000"
            if not installMedia.hasPackages:
                # Mark devices without media as red.  We do not want to make
                # them insensitive since the user needs to be able to select
                # the device they want to eject.
                contents = "No packages"
                foreground = "#ff0000"
            elif installMedia.isoPath:
                contents = installMedia.isoPath
            else:
                contents = "Installation packages"
            mediaIter = self.model.append(None, [
                    util.truncateString(installMedia.getName(),
                                        DEVMODEL_LENGTH),
                    contents,
                    installMedia.version,
                    installMedia,
                    foreground])
            if installMedia.hasPackages and \
                    (not selectedMedia or
                     selectedMedia.diskName == installMedia.diskName):
                self.view.set_cursor(self.model.get_path(mediaIter))
                selectedMedia = installMedia

    def _getSelectedMedia(self):
        (model, mediaIter) = self.view.get_selection().get_selected()
        if not mediaIter:
            return None
        
        return model.get(mediaIter, MEDIA_ENTRY)[0]
    
    def ejectMedia(self, *_args):
        selectedMedia = self._getSelectedMedia()
        if selectedMedia:
            selectedMedia.eject()
        else:
            cdutil.ejectCdrom()

    def getBack(self):
        """Mark the media drive as not in-use anymore."""
        selectedMedia = userchoices.getMediaDescriptor()
        if selectedMedia and selectedMedia.diskName:
            userchoices.delDriveUse(selectedMedia.diskName, 'media')

    def getNext(self):
        selectedMedia = self._getSelectedMedia()
        if not selectedMedia or not selectedMedia.hasPackages:
            MessageWindow(None,
                          "Media Selection Error",
                          "Select a valid installation medium.")
            raise exception.StayOnScreen
        
        if selectedMedia.diskName:
            userchoices.addDriveUse(selectedMedia.diskName, 'media')
        userchoices.setMediaDescriptor(selectedMedia)
        userchoices.clearMediaLocation()

        try:
            # Mount the media in case it is needed later on.
            selectedMedia.mount()
        except Exception, e:
            log.exception("unable to mount media")
            MessageWindow(None,
                          "Media Error",
                          "Unable to mount media.  Rescan and select "
                          "the media again.")
            raise exception.StayOnScreen
