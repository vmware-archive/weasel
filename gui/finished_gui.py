
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

# display the finished window
import gtk
import tidy

import userchoices

class FinishedWindow:
    SCREEN_NAME = 'finished'
    
    def __init__(self, controlState, xml):
        controlState.displayBanner = False

        alignment = xml.get_widget("FinishedEventBox")
        alignment.modify_bg(gtk.STATE_NORMAL,
                            alignment.get_colormap().alloc_color('white'))
        controlState.setBackButtonEnabled(False)
        controlState.setNextButtonEnabled(False)
        controlState.setFinishButtonShow(True)
        controlState.setCancelButtonShow(False)

        self.networkLabel = xml.get_widget("FinishedNetworkLabel")
        self.setIpAddress()

    def setIpAddress(self):
        cosNics = userchoices.getCosNICs()

        assert cosNics

        if cosNics[0]['ip']:
            self.networkLabel.set_text("http://%s/" % cosNics[0]['ip'])
