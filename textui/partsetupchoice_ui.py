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

'''Partitioning Setup
Select between basic and advanced partitioning.
'''

import dispatch
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
from log import log

title = "Disk Setup"

askSetupChoiceText = """\
Specify the type of setup for this installation.
 1) Basic Setup
    Set up ESX on a single hard drive or LUN.
 2) Advanced Setup
    View and customize the individual ESX partitions.
 <) Back

"""

# step lists
basicPartList = ['basicesxlocation',]
advancedPartList = ['advesxlocation', 'datastore', 'setupvmdk',
    'bootloader']

class PartSetupChoiceWindow(TextRunner):
    """Choose between partitioning methods and execute step list.
    Use standard Weasel dispatcher to track steps.
    """

    def __init__(self):
        super(PartSetupChoiceWindow, self).__init__()
        self.substep = self.start

    def start(self):
        "Initial step."
        ui = {
            'title': title,
            'body': askSetupChoiceText,
            'menu': {
                '1': self.doStepList,   # basic
                '2': self.doStepList,   # advanced
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    def doStepList(self):
        """Choose and execute the appropriate steplist.
        Track via Weasel dispatcher.
        """
        if self.userinput == '1':
            steps = basicPartList
        else:  # assume self.userinput == '2'
            steps = advancedPartList

        # Warning:  Don't import main and stepToClass at top of file.
        # This module not known to main at that point.
        class Dispatcher2(dispatch.Dispatcher):
            """Parent dispatcher does not allow movement before first step.
            We want that so that we can exit the loop when going out of bounds.
            """
            def moveStep(self):
                self.step = self.step + self.direction

        dispatcher = Dispatcher2(stepList=steps)
        import main

        result = None
        while 0 <= dispatcher.currentStep() < len(steps):
            step = dispatcher[dispatcher.currentStep()]
            try:
                runner = main.stepToClass[step]
            except KeyError, badkey:
                errMsg = "unknown step in PartSetupChoiceWindow: %s" % badkey
                log.error(errMsg)
                raise RuntimeError(errMsg)      # something really bad happened

            result = runner().run()
            assert result in ( dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT)
            if result == dispatch.DISPATCH_NEXT:
                dispatcher.goNext()
            else:
                dispatcher.goBack()

        if result == dispatch.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.stepForward})
        else:
            self.setSubstepEnv({'next': self.start})

# vim: set sw=4 tw=80 :
