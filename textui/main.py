#!/usr/bin/env python

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

import sys, os
import getopt

# insert at head; avoid dispatch in distutils RuleDispatch 
# This loop allows the current diretory to be 'weasel' or 'textui'.
for lib in [ '.', '..' ]:
    if os.path.isdir(lib+'/textui'):
        sys.path.insert(0, os.path.abspath(lib))
        sys.path.insert(0, os.path.abspath(lib+'/textui'))
        break

from log import log
from textrunner import TextRunner
from consts import ExitCodes
import dispatch
import exception
import media
from textengine import waitinput, DISPATCH_NEXT

# step modules
import welcome_ui
import eula_ui
import keyboard_ui
import customdrivers_ui
import cosnetworkadapter_ui
import installmedia_ui
import password_ui
import partsetupchoice_ui
import esxlocation_ui
import datastore_ui
import setupvmdk_ui
import bootloader_ui
import timezone_ui
import timedate_ui
import review_ui
import license_ui
import installation_ui
import finished_ui
import userchoices

stepToClass = {
    'welcome' : welcome_ui.WelcomeWindow,
    'keyboard' : keyboard_ui.KeyboardWindow,
    'eula' : eula_ui.EulaWindow,
    'customdrivers' : customdrivers_ui.CustomDriversWindow,
    'driverload' : installation_ui.DriverLoadWindow,
    'license' : license_ui.LicenseWindow,
    'media' : installmedia_ui.InstallMediaWindow,
    'esxlocation' : esxlocation_ui.EsxLocationWindow,
    'partsetupchoice' : partsetupchoice_ui.PartSetupChoiceWindow,
    'basicesxlocation': esxlocation_ui.BasicEsxLocationWindow,
    'advesxlocation': esxlocation_ui.AdvEsxLocationWindow,
    'datastore' : datastore_ui.DataStoreWindow,
    'timezone' : timezone_ui.TimezoneWindow,
    'timedate' : timedate_ui.TimedateWindow,
    'setupvmdk' : setupvmdk_ui.SetupVmdkWindow,
    'password' : password_ui.PasswordWindow,
    'cosnetworkadapter' : cosnetworkadapter_ui.CosNetworkAdapterWindow,
    'review' : review_ui.ReviewWindow,
    'installation' : installation_ui.InstallationWindow,
    'bootloader' : bootloader_ui.BootloaderWindow,
    'finished' : finished_ui.FinishedWindow,
}

installSteps = [
    'welcome',
    'keyboard',
    'eula',
    'customdrivers',
    'driverload',
    'license',
    'cosnetworkadapter',
    'media',
    'partsetupchoice',
    'timezone',
    'timedate',
    'password',
    'review',
    'installation',
    'finished',
]


class MountMediaDelegate:
    def mountMediaNoDrive(self):
        waitinput(prompt="error: The CD drive was not detected on boot up and "
                  "you have selected CD-based installation.\n"
                  "Press <enter> to reboot...")

    def mountMediaNoPackages(self):
        waitinput(prompt="Insert the ESX Installation media.\n"
                  "Press <enter> when ready...")

    def mountMediaCheckFailed(self):
        waitinput(prompt="Verification Failed: The ESX installation media "
                  "contains errors.\n"
                  "Press <enter> to reboot...")

    def mountMediaCheckSuccess(self):
        waitinput(prompt="Verification Success: No errors were found on the "
                  "ESX installation media.\n"
                  "Press <enter> to continue...")

media.MOUNT_MEDIA_DELEGATE = MountMediaDelegate()


def usage():
    print >>sys.stderr, """\
usage: %s
  -h            help
  -s step       run a single step (mostly for debugging)
  -o fname      save to output file fname
To run a step from caged weasel:
  python test/caged_weasel.py textui/main.py --debug <stepname>
"""


def parse_cmdline(args):
    # look into OptParse (optparse?)
    params = {}
    try:
        opts, args = getopt.getopt(args[1:], "dho:",
            ["askmedia", "debug", "help", "output=" ])
        print 'args', args
    except getopt.GetoptError, ex:
        log.error("can't parse command line options: %s" % ex[0])
        sys.exit(1)

    for o, a in opts:
        if o in ('-d', '--debug'):
            userchoices.setDebug(True)
        elif o in ('-o', '--output'):
            params['out'] = a           # output filename
        elif o in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif o == '--askmedia':
            userchoices.setShowInstallMethod(True)
        else:
            usage()

    if len(args) > 0:
        params['step'] = args[-1]       # execute a single step

    return params

exceptionText = """\
%s

 1) Reboot
 2) Debug

"""

class ExceptionWindow(TextRunner):
    def __init__(self, desc, details):
        super(ExceptionWindow, self).__init__()
        
        self.desc = desc
        if details:
            self.desc += "\n\nDetails:\n "
            detailLines = details.split('\n')
            if len(detailLines) > 9:
                self.desc += " ...\n "
            self.desc += "\n ".join(detailLines[-9:])
        self.desc += "\n\nSee /var/log/esx_install.log for more information."
        
    def start(self):
        ui = {
            'title' : 'An error has occurred during your ESX installation.',
            'body' : exceptionText % self.desc,
            'menu' : {
                '1': self.reboot,
                '2': self.dropIntoDebugger,
            }
        }
        self.setSubstepEnv(ui)

    def reboot(self):
        self.stepForward()

    def dropIntoDebugger(self):
        self.stepBack()

class TextUI:
    def __init__(self, params):
        sys.excepthook = lambda type, value, tb: \
            exception.handleException(self, (type, value, tb),
                                      traceInDetails=False)
        
        self.params = params

        self.dispatch = dispatch.Dispatcher(stepList=installSteps)

        # remove installmedia step unless askmethod was called
        if not userchoices.getShowInstallMethod():
            self.dispatch.remove('media')

        ##### WORKAROUND ####
        ## TODO: deal with this temporary workaround for async drivers
        #import applychoices
        #try:
        #    # load all of the drivers now since we don't support async drivers
        #    iw = installation_ui.InstallationWindow()
        #    iw.apply2('loadDrivers')
        #except IOError, e:
        #    log.error("error: cannot open file -- %s\n" % str(e))
        ##### WORKAROUND ####

    def exceptionWindow(self, desc, details):
        ew = ExceptionWindow(desc, details)
        direction = ew.run()

        return (direction == DISPATCH_NEXT)
        
    def run(self):
        params = self.params
        if 'step' in params:
            pstep = params['step']
            if userchoices.getDebug():
                stepclass = stepToClass[pstep]
                result = stepclass().run()
                return 0
            else:
                try:
                    stepclass = stepToClass[pstep]
                    result = stepclass().run()
                    return 0
                except:
                    log.error("unable to run step '%s'" % pstep)
                    return 1

        while 1:
            step = self.dispatch.currentStep()
            if step == len(self.dispatch):
                break
            stepclass = stepToClass[self.dispatch[step]]
            stepObject = stepclass()
            stepObject.dispatch = self.dispatch
            self.dispatch.direction = stepObject.run()
            self.dispatch.moveStep()

        return 0

    def __del__(self):
        # clean up the ui gracefully
        try:
            pass
        except:
            pass

def main(args):
    params = parse_cmdline(args)
    textui = TextUI(params)
    return textui.run()

if __name__ == "__main__":
    sys.exit(main(sys.argv))
