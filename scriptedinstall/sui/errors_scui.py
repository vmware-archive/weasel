
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

import snack
import string

import sys
sys.path.append("..")

import dispatch

class ErrorWindow:
    buttons = None
    title="Generic Error"
    descr="Some error occured"

    def __init__(self, screen, message="Generic Error"):

        self.message = message

        toplevelGrid = snack.GridFormHelp(screen, self.title, None, 1, 5)

        grid = snack.Grid(1, 3)
        grid.setField(snack.Label(self.descr), 0, 0, anchorLeft=1)
        grid.setField(snack.Label(""), 0, 1)
        grid.setField(snack.Label(self.message), 0, 2, anchorLeft=1)

        toplevelGrid.add(grid, 0, 0, (0, 0, 0, 1))

        toplevelGrid.add(self.buttons, 0, 1, growx=1)

        while 1:
           result = toplevelGrid.run()

	   # assume only a reboot button
           self.rc = dispatch.DISPATCH_NEXT
           screen.popWindow()
           break


class BumpstartErrorWindow(ErrorWindow):
   def __init__(self, screen, message="Unkown Bumpstart Error detected"):
      self.title = "Scripted Install Error"
      self.descr = "An error was detected in your bumpstart file"
      self.buttons = snack.ButtonBar(screen, ["Reboot"])
      ErrorWindow.__init__(self, screen, message)

class MediaDeviceErrorWindow(ErrorWindow):
   def __init__(self, screen, message="No CD-ROM or DVD-ROM detected"):
      self.title = "Media Error"
      self.descr = "The following media errors were detected"
      self.buttons = snack.ButtonBar(screen, ["Reboot"])
      ErrorWindow.__init__(self, screen, message)
     
class NetworkSetupErrorWindow(ErrorWindow):
   def __init__(self, screen, message="Error Configuring your network"):
      self.title = "Network Setup Error"
      self.descr = "The configruation of your network failed"
      self.buttons = snack.ButtonBar(screen, ["Reboot"])
      ErrorWindow.__init__(self, screen, message)
     
class RuntimeEnvironmentErrorWindow(ErrorWindow):
   def __init__(self, screen, message="Weasel Runtime Environment not found"):
      self.title = "Runtime Environment"
      self.descr = "The Weasel runtime environment could not be found"
      self.buttons = snack.ButtonBar(screen, ["Reboot"])
      ErrorWindow.__init__(self, screen, message)
     
if __name__ == "__main__":
    screen = snack.SnackScreen()
    RuntimeEnvironmentErrorWindow(screen)
    screen.finish()

