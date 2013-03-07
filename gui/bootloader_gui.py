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
TODO: docstring for the bootloader_gui module goes here
'''

import gtk
import exception
import userchoices
import bootloader
from common_windows import MessageWindow

class BootloaderWindow:
    SCREEN_NAME = 'bootloader'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'boot-loader.png'
        controlState.windowTitle = "Set Bootloader Options"
        controlState.windowText = "Enter options for the GRUB bootloader"

        self.controlState = controlState
        self.xml = xml

    def getKernelParams(self):
        kernelParamsWid = self.xml.get_widget("BootloaderKernelParamsEntry")
        kernelParams = kernelParamsWid.get_text().strip()
        return kernelParams

    def getPassword(self):
        password1Wid = self.xml.get_widget("BootloaderPassword1Entry")
        password2Wid = self.xml.get_widget("BootloaderPassword2Entry")
        password1 = password1Wid.get_text()
        password2 = password2Wid.get_text()

        if password1 != password2:
            MessageWindow(self.controlState.gui.getWindow(),
                "Password Input Error",
                "The two passwords entered did not match.")
            raise exception.StayOnScreen

        if password1 == '':
            return ''

        try:
            bootloader.validateGrubPassword(password1)
        except ValueError, msg:
            MessageWindow(self.controlState.gui.getWindow(),
                "Password Input Error", msg[0])
            raise exception.StayOnScreen

        return password1

    def getLocation(self):
        #TODO: add a popup warning when they toggle on the first partition 
        #      checkbox saying "This is normally for very obscure cases such
        #      as setting up a diagnostic partition"
        firstPartWid = self.xml.get_widget("CheckbuttonFirstPartition")
        if firstPartWid.get_active():
            location = userchoices.BOOT_LOC_PARTITION
        else:
            location = userchoices.BOOT_LOC_MBR
        return location

    def getNext(self):
        kernelParams = self.getKernelParams()
        password = self.getPassword()
        location = self.getLocation()

        #TODO: users.cryptPassword() ???

        userchoices.setBoot(False,
                            location=location,
                            kernelParams=kernelParams,
                            password=password,
                           )

        bootloader.runtimeAction()
