
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

# display the welcome window
import gtk
import gobject
import media
from common_windows import ProgressWindowTaskListener, MountMediaDelegate
from common_windows import MessageWindow

from consts import HV_DISABLED_TEXT

class WelcomeWindow:
    SCREEN_NAME = 'welcome'
    
    def __init__(self, controlState, xml):
        alignment = xml.get_widget("WelcomeEventBox")
        alignment.modify_bg(gtk.STATE_NORMAL,
                            alignment.get_colormap().alloc_color('white'))
        controlState.backButtonEnabled = False
        controlState.displayBanner = False

        if media.needsToBeChecked():
            self.progressDialog = \
                ProgressWindowTaskListener(None, \
                           'Verifying Media', \
                           'Verifying media ... please wait.',
                           ['brandiso.calc_md5'],
                           )

            self.mediaCheckID = gobject.idle_add(self.startMediaCheck)
            #self.progressDialog.setCancelCallback(self.stopMediaCheck)

    def getNext(self):
        self.checkForVT()

    def checkForVT(self):
        import vmkctl
        cpuInfo = vmkctl.CpuInfoImpl()
        if cpuInfo.GetHVSupport() == cpuInfo.HV_DISABLED:
            MessageWindow(None, "VT Disabled", HV_DISABLED_TEXT, type="ok")

    # leave commented as a hint for what to do in next version
    #def stopMediaCheck(self):
        # TODO: stop the media check in the brandiso module
        #self.progressDialog.finish()
        #gobject.source_remove(self.mediaCheckID)

    def startMediaCheck(self):
        mediaDelegate = MountMediaDelegate()
        media.runtimeActionMediaCheck()
        self.progressDialog.finish()

