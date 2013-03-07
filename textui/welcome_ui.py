
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

import time
import textengine
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
import media
import task_progress
import vmkctl
import sys

from consts import HV_DISABLED_TEXT

welcomeHead = "ESX 4.1 -- Virtual Infrastructure for the Enterprise"

welcomeText = """\
Welcome to the ESX Text Installer
Release 4.1

This wizard will guide you through the installation of ESX.

ESX installs on most systems, but only systems on VMware's Hardware
Compatibility Guide (HCG) are supported. Please consult VMware's HCG on
vmware.com.
"""

welcomeHelpHead = "Welcome (Help)"

welcomeHelpText = """\
The ESX Text Installer uses these input conventions in many places:
  * For help, enter '?'.
  * To go to the previous step (or substep), enter '<'.
  * To cancel (exit) installation and reboot, enter '!'.
"""

mediaCheckText = """\n
Please wait... Checking the installation media.\n
"""

class ProgressDotPrinter(object):
    def __init__(self, watchedTasks):
        self.watchedTasks = watchedTasks
        task_progress.addNotificationListener(self)
        self.lastDot = 0
        # we don't want to pulse more often than once every 2/10 seconds
        self.hyperactivityThreshold = 0.2

    def notifyTaskStarted(self, taskTitle):
        pass

    def notifyTaskProgress(self, taskTitle, amount):
        if time.time() - self.lastDot < self.hyperactivityThreshold:
            return
        if taskTitle not in self.watchedTasks:
            return
        self.lastDot = time.time()
        textengine.render_status('.')

    def notifyTaskFinish(self, taskTitle):
        if taskTitle in self.watchedTasks:
            textengine.render_status('done.\n')

class WelcomeWindow(TextRunner):
    def __init__(self):
        super(WelcomeWindow, self).__init__()

        # Clear here to get rid previous logging on screen.
        textengine.render_oob(textengine.CLEARSCREEN)
        self.start = self.welcome
        self.substep = self.start

    def welcome(self):
        global welcomeText
        func = self.stepForward

        if media.needsToBeChecked():
            func = self.actionMediaCheck

        cpuInfo = vmkctl.CpuInfoImpl()
        if cpuInfo.GetHVSupport() == cpuInfo.HV_DISABLED:
            welcomeText = welcomeText + "\n%s" % HV_DISABLED_TEXT

        ui = {
            'title': welcomeHead,
            'body': welcomeText + TransMenu.ContHelpExit,
            'menu': {
                '1': func,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def actionMediaCheck(self):
        textengine.render_status(mediaCheckText)
        progressPrinter = ProgressDotPrinter('brandiso.calc_md5')
        media.runtimeActionMediaCheck()
        # just in case - don't wait for it to be garbage collected...
        task_progress.removeNotificationListener(progressPrinter)
        self.setSubstepEnv({ 'next': self.stepForward })

    def help(self):
        self.helpPushPop(welcomeHelpHead, welcomeHelpText + TransMenu.Back)

