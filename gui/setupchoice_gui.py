
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

# display the bootloader window
import userchoices
from signalconnect import connectSignalHandlerByDict

class SetupChoiceWindow:
    SCREEN_NAME = 'setupchoice'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'setuptype.png'
        controlState.windowTitle = "Setup Type"
        controlState.windowText = \
            "Specify the type of setup for this installation"

        self.controlState = controlState
        self.xml = xml

        self.setupChoice = self.xml.get_widget("SetupchoiceBootloaderHBox")

        connectSignalHandlerByDict(self, SetupChoiceWindow, self.xml,
          { ('SetupchoicebasicRadioButton', 'toggled'): 'toggleSetupChoice',
        })


    # toggle the advanced setup checkboxes on/off depending on the value
    # of the radio button
    def toggleSetupChoice(self, widget, *args):
        self.setupChoice.set_sensitive(not widget.get_active())

    def getNext(self):
        widget = self.xml.get_widget("SetupchoicebasicRadioButton")
        if widget.get_active():
            # remove the advanced partitioning path and make certain the
            # install location screen is going to come up since we're
            # taking the basic setup path

            _removeSteps(["datastore", "esxlocation", "setupvmdk",
                          "bootloader"],
                         self.controlState)
            _addSteps([("installlocation", "timezone")], self.controlState)

            # There's a chance the user has already been down to the 
            # bootloader screen and Backed all the way up to here.  Since
            # the basic path implies no bootloader changes, wipe out any
            # bootloader userchoices that have been made
            userchoices.clearBoot()

        else:
            # if the advanced partitioning page was removed because the user
            # went down the basic setup path, we need to add it back

            _addSteps([("esxlocation", "timezone"),
                       ("datastore", "timezone"),
                       ("setupvmdk", "timezone"), ],
                      self.controlState)

            _removeSteps(["installlocation", "bootloader"], self.controlState)

            # If the bootloader checkbox isn't active, show the screen
            bootCheck = self.xml.get_widget("SetupchoicebootloaderCheckButton")
            if not bootCheck.get_active():
                _addSteps([("bootloader", "timezone")], self.controlState)
            else:
                # The user doesn't want to make any bootloader choices, so
                # wipe any that may have been made previously
                userchoices.clearBoot()



def _addSteps(stepList, controlState):
    for step, insertBeforeStep in stepList:
        if step not in controlState.gui.dispatch:
            controlState.insertStep(step, insertBeforeStep)

def _removeSteps(stepList, controlState):
    for step in stepList:
        if step in controlState.gui.dispatch:
            controlState.removeStep(step)

