
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

DISPATCH_NEXT = 1
DISPATCH_BACK = -1

FIRST_STEP = 0

class Dispatcher(list):
    def __init__(self, stepList=None, firstStep=FIRST_STEP):
        self.direction = DISPATCH_NEXT
        if stepList:
            self.extend(stepList)
        self.step = firstStep

    def goBack(self):
        self.direction = DISPATCH_BACK
        self.moveStep()

    def goNext(self):
        self.direction = DISPATCH_NEXT
        self.moveStep()

    def moveStep(self):
        if self.step == FIRST_STEP and self.direction == DISPATCH_BACK:
            pass
        else:
            self.step = self.step + self.direction

    def currentStep(self):
        return self.step

    def sort(self):
        print "No sort for you."

