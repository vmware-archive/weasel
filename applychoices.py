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

'''Performs the actual installation based on the data in userchoices.

See userchoices.py
'''

import sys
import exception
from log import log

import userchoices

class StopProgress(Exception):
    '''Exception thrown by ProgressCallback.popStatus() when progress has been
    stopped.  XXX Unused'''
    pass

class StdoutProgressDelegate:
    '''Basic output delegate for the ProgressCallback that writes to stdout.'''

    def __init__(self):
        self.lastmsg = None
        
    def reportit(self, code, callback):
        """Prepare status message for text installer delivery.
        Keep 'code' as a back door selector... just in case we get
        into trouble.
        """
        pct = callback.getProgress()
        msg = callback.getLastMessage()
        if msg:  # The message will be empty when everything completes.
            msg = "- %s" % msg
        text = "%3d%% Complete %s" % (pct * 100.0, msg)
        if msg == self.lastmsg:
            return      # Don't repeat identical message.
        sys.stdout.write("%s\n" % text)     # TODO: may need finer control later
        sys.stdout.flush()

        self.lastmsg = msg

    def progressStatusStarted(self, callback):
        self.reportit("SS", callback)

    def progressStatusFinished(self, callback):
        self.reportit("SF", callback)

    def progressStatusGroupStarted(self, callback):
        self.reportit("GS", callback)

    def progressStatusGroupFinished(self, callback):
        self.reportit("GF", callback)


class ProgressCallback(object):

    '''Callback class used by worker code to signal progress to the
    UI code.  Before starting their processing, the worker code adds
    their status information to the callback.  The status consists of
    a descriptive string and the number of units-of-work they will
    accomplish when finished.  The total amount of work to be
    performed across different workers is recorded by a "status
    group".  So, progress is computed as the number of units-of-work
    completed so far by the workers versus the total recorded by the
    group.  For example, the following code performs three
    units-of-work broken down into two tasks:

    >>> pc = ProgressCallback()
    >>> pc.pushStatusGroup(3) # three units-of-work will be done overall
    >>> pc.pushStatus("First Thing", 2) # This task will do two units
    >>> # ... do two units-of-work here ...
    ... pc.popStatus() # Signal completion of work.
    >>> "%0.2f" % pc.getProgress() # Check how much progress has been made.
    '0.67'
    >>> pc.pushStatus("Second Thing")
    >>> # ... do one unit-of-work here ...
    ... pc.popStatus()
    >>> "%0.2f" % pc.getProgress()
    '1.00'

    As you might have guessed, the class presents a stack interface, so you
    can further subdivide a task by pushing another group and its sub-tasks.
    Overall progress is still updated when tasks are nested like this, just
    in fractional amounts relative to units-of-work higher up in the stack.
    For example, the following code breaks down installation into
    partitioning all of the hard drives and then further subdivides it for
    the individual drives:

    >>> pc = ProgressCallback()
    >>> pc.pushStatusGroup(20) # 20 units-of-work will be done for the install
    >>> pc.pushStatus("Partitioning Hard Drives", 5) # 5 units for partitioning
    >>> pc.pushStatusGroup(2)
    >>> pc.pushStatus("Partitioning /dev/sda")
    >>> pc.popStatus()
    >>> # Check overall progress.  We have done half of the partitioning work
    ... # and partitioning is 1/4th of the overall work, so we have done
    ... # 1/8th of the overall work.
    ... "%0.2f" % pc.getProgress()
    '0.12'
    >>> # Pop the partitioning task.  Even though we did not do the other
    ... # partitioning task, the overall progress should be correct anyways.
    ... pc.popStatusGroup()
    >>> pc.popStatus()
    >>> "%0.2f" % pc.getProgress()
    '0.25'


    XXX In the future, pushStatus should return a context manager.
    '''

    def __init__(self, delegate=None):
        '''Construct a ProgressCallback with an optional delegate object.  The
        delegate can implement any or all of the following methods:

            progressStatusStarted(progressCallback)
                Called when a new task has been pushed onto the stack.
            progressStatusGroupStarted(progressCallback)
                Called when a new task group has been pushed onto the stack.
            progressStatusFinished(progressCallback)
                Called when a task has been popped off of the stack.
            progressStatusGroupFinished(progressCallback)
                Called when a task group has been popped off of the stack.

        For example:

        >>> class MyDelegate:
        ...     def progressStatusFinished(self, callback):
        ...         print "%3d%% Completed" % (callback.getProgress() * 100)
        >>> pc = ProgressCallback(MyDelegate())
        >>> pc.pushStatusGroup(20)
        >>> pc.pushStatus("Hello, World!")
        >>> pc.popStatus()
          5% Completed
        '''
        
        self.statusStack = []
        self.delegate = delegate
        self.stopped = False
        return

    def _isStatusGroup(self, index):
        '''Return True if the given index is for a task group.'''
        
        return index % 2 == 0

    def _isStatus(self, index):
        '''Return False if the given index is for a task.'''
        
        return index % 2 == 1

    def _tellDelegate(self, method):
        '''Call the given delegate method, if there is a delegate and it
        implements the method.'''

        if method == 'progressStatusStarted':
            log.info("status: progress=%0.2f; messageID=%s; %s" % (
                self.getProgress(),
                self.getLastMessageID(),
                self.getLastMessage()))
        if hasattr(self.delegate, method):
            getattr(self.delegate, method)(self)

    def stop(self):
        '''Stop progress.  XXX Unused'''
        self.stopped = True

    def pushStatusGroup(self, totalPortions):
        '''Push a task group onto the stack.  The totalPortions value
        should be the sum of all the sub-task portions.

        Note: only a single group should be pushed for the higher-level task.
        So, do not do this:

        >>> pc = ProgressCallback()
        >>> pc.pushStatusGroup(1)
        >>> pc.pushStatus("Nested")
        >>> pc.pushStatusGroup(1)
        >>> pc.popStatusGroup()
        >>> pc.pushStatusGroup(1) # NO!
        Traceback (most recent call last):
          . . .
        AssertionError: only one sub-group allowed per-task
        '''

        assert self._isStatusGroup(len(self.statusStack)), "top is not a task"
        assert (not self.statusStack or
                self.statusStack[-1]['remaining'] == 1.0), \
               "only one sub-group allowed per-task"

        self.statusStack.append({
            'portion' : float(totalPortions),
            'remaining' : 1.0,
            })

        self._tellDelegate('progressStatusGroupStarted')

    def pushStatus(self, msg, portion=1, msgID='NONE'):
        '''Push a new task onto the stack with the given values:

        msg       The english message to show to the user.
        portion   The number of units-of-work that this task accomplishes
                  compared to its peer tasks.
        msgID     "Enumerated value" for the message, intended for use by
                  clients that need to do localization.

        Note: You must push a group before adding your actual tasks.  The
        root group is used to track the overall progress.
        '''

        assert self._isStatus(len(self.statusStack)), "top is not a group"
        assert portion >= 0

        self.statusStack.append({
            'msg' : msg,
            'msgID' : msgID,
            'portion' : float(portion),
            'remaining' : 1.0,
            })

        self._tellDelegate('progressStatusStarted')

    def _pop(self, delegateMethod):
        '''Pop the top task off of the stack and update the amount of work
        remaining in the tasks higher up in the stack.  The delegateMethod
        is the name of the method in the delegate to execute after updating
        the progress values, but before popping the task off the stack.
        '''
        
        assert self.statusStack, "no tasks/groups on the stack"

        # Subtract the units-of-work remaining in this task from the upper
        # levels, scaling the value along the way.
        ratio = self.statusStack[-1]['remaining']

        for taskIndex in reversed(range(1, len(self.statusStack))):
            child = self.statusStack[taskIndex]
            parent = self.statusStack[taskIndex - 1]
            if not self._isStatusGroup(taskIndex):
                # Scale the remaining value based on the task's portion within
                # the group.  The scale between a group and its higher-level
                # task is the same we there's no scaling.
                ratio *= child['portion'] / parent['portion']
            parent['remaining'] -= ratio

        if len(self.statusStack) == 1:
            # XXX sillyness to get around rounding errors and show 100%...
            self.statusStack[0]['remaining'] = 0.0
            log.info("status: progress=1.0; messageID=None;")
        
        self._tellDelegate(delegateMethod)
        self.statusStack.pop()

        if self.stopped and len(self.statusStack) >= 2:
            raise StopProgress, "Stopped while %s" % self.getLastMessage()

    def popStatus(self):
        assert self._isStatus(len(self.statusStack) - 1), "top is not a task"

        self._pop('progressStatusFinished')

    def popStatusGroup(self):
        assert self._isStatusGroup(len(self.statusStack) - 1), \
               "top is not a group"

        self._pop('progressStatusGroupFinished')

    def getProgress(self):
        '''Return the current progress through the tasks as a floating point
        value between zero and one.
        '''
        
        assert self.statusStack, "no active tasks"
        
        return 1.0 - self.statusStack[0]['remaining']

    def getLastMessageID(self):
        # XXX Merge this with getLastMessage()?
        if len(self.statusStack) >= 2:
            for status in reversed(self.statusStack):
                if 'msgID' in status and status['msgID'] != 'NONE':
                    return status['msgID']
        return "NONE"

    def getLastMessage(self):
        '''Return the message from the last task pushed onto the stack.  If a
        group was the last thing pushed onto the stack, the message will be
        from the task above it.

        >>> pc = ProgressCallback()
        >>> pc.pushStatusGroup(10)
        >>> pc.pushStatus("Hello, World!")
        >>> pc.getLastMessage()
        'Hello, World!'
        >>> pc.pushStatusGroup(20)
        >>> pc.getLastMessage()
        'Hello, World!'
        '''
        
        if len(self.statusStack) < 2:
            return ""
        else:
            return self.statusStack[-1 - len(self.statusStack) % 2]['msg']


class Context:
    def __init__(self, cb=None):
        if not cb:
            cb = ProgressCallback()
        self.cb = cb


def _loadDriverSteps():
    import customdrivers

    # XXX - don't add any steps after LOADDRIVERS since a non-critical
    #       exception can handle there which is passed up through to the
    #       gui.

    retval = [
        (5, 'Unpack Drivers', 'UNPACK', 
         customdrivers.hostActionUnpackDrivers),
        (1, 'Rebuilding Map File', 'MAPFILE', 
         customdrivers.hostActionRebuildSimpleMap),
        (80, 'Loading Drivers', 'LOADDRIVERS', 
         customdrivers.hostActionLoadDrivers),
    ]

    return retval

def _installSteps():
    '''Returns a list of steps needed to perform a complete installation.'''
    
    import partition
    import fsset
    import packages
    import services
    import workarounds
    import users
    import bootloader
    import script
    import networking
    import firewall
    import esxlicense
    import devices
    import timezone
    import timedate
    import systemsettings
    import fstab
    import esxconf
    import scriptwriter
    import log as logmod
    
    # Map of installation steps.  Each step has a name and a tuple conntaining
    # the following values:
    #
    #   portion     The units-of-work done by this step, relative to the others
    #   desc        A human-readable description of what the step is doing.
    #   msgID       A machine-readable description of the step.
    #   func        The function that implements the step.
    retval = [
        (10, 'Clearing Partitions', 'CLEARPART',
         partition.hostActionClearPartitions),

        (1, 'Removing Unwanted VMDK Files', 'CLEARVMDK',
         esxconf.hostActionRemoveVmdk),

        (10, 'Partitioning Physical Hard Drives', 'PARTPHYS',
         partition.hostActionPartitionPhysicalDevices),
        (10, 'Partitioning Virtual Hard Drives', 'PARTVIRT',
         partition.hostActionPartitionVirtualDevices),

        (5, 'Mounting File Systems', 'MOUNT',
         partition.hostActionMountFileSystems),
        (1, 'Mounting File Systems', 'MOUNT',
         fsset.hostActionMountPseudoFS),

        (1, 'Copy Installer Log', 'LOG', logmod.hostActionCopyLogs),

        (80, 'Installing Packages', 'PACKAGES',
         packages.hostActionInstallPackages),
        
        (1, 'Service Settings', 'SERVICES', services.hostAction),
        
        (1, 'Setup Module Loading', 'MODPROBE',
         workarounds.hostActionRedirectLKMLoading),
        
        (1, 'Create fstab', 'FSTAB', fstab.hostActionWriteFstab),
        (1, 'Boot Location', 'BOOTLOADER', devices.hostActionSetupVmdk),
        
        # networking.hostAction destroys the network setup for our installation
        # environment, so we have to do this here.  :-/
        (1, 'Updating esxupdate Database', 'ESXUPDATEDB',
         workarounds.hostActionUpdateEsxupdateDatabase),

        (1, 'Installing Network Configuration', 'NETWORKING',
         networking.hostAction), #used to be workarounds.copynetconfig

        (1, 'Setting Timezone', 'TIMEZONE', timezone.hostActionTimezone),
        (1, 'Setting Time and Date', 'TIMEDATE', timedate.hostActionTimedate),
        (1, 'Setting Keyboard', 'KEYBOARD', systemsettings.hostActionKeyboard),
        (1, 'Setting Language', 'LANGUAGE', systemsettings.hostActionLang),

        (1, 'Set Console Memory', 'CONSOLEMEM',
         workarounds.hostActionSetCosMemory),

        (1, 'Copying ESX Configuration', 'ESXCONF',
         esxconf.hostActionCopyConfig),

        # Firewall depends on esx.conf being installed.
        (1, 'Firewall Settings', 'FIREWALL', firewall.hostAction),

        (1, 'Configuring Authentication', 'AUTH',
         users.hostActionAuthentication),

        (1, 'Setting License', 'LICENSE', esxlicense.hostAction),

        (1, 'Configuring User Accounts', 'ROOTPASS',
         users.hostActionSetupAccounts),
        
        (5, 'Boot Setup', 'BOOTLOADER', bootloader.hostAction),
        
        (1, 'Running "%post" Script', 'POSTSCRIPT',
         script.hostActionPostScript),

        (1, 'Writing ks.cfg', 'KS_SCRIPT',
         scriptwriter.hostAction),

        (1, 'Boot Setup', 'BOOTLOADER', bootloader.hostActionRebuildInitrd),
        
        (1, 'Checking esx.conf consistency', 'VALIDATE',
         esxconf.validateAction),
        ]

    return retval

def _upgradeSteps():
    '''Returns a list of steps needed to perform an upgrade.'''

    import partition
    import fsset
    import fstab
    import devices
    import packages
    import workarounds
    import migrate
    import users
    import networking
    import esxlicense
    import bootloader
    import script
    import esxconf
    import log as logmod
    
    retval = [
        (1, 'Add Upgrade Log', 'LOG', logmod.hostActionAddUpgradeLogs),

        (10, 'Partitioning Virtual Hard Drives', 'PARTVIRT',
         partition.hostActionPartitionVirtualDevices),
        
        (5, 'Mounting File Systems', 'MOUNT',
         partition.hostActionMountFileSystems),
        (1, 'Mounting File Systems', 'MOUNT',
         fsset.hostActionMountPseudoFS),

        (1, 'Copy Installer Log', 'LOG', logmod.hostActionCopyLogs),

        (1, 'Create fstab', 'FSTAB', fstab.hostActionWriteFstab),
        (1, 'Boot Location', 'BOOTLOADER', devices.hostActionSetupVmdk),
        
        (1, 'Migrating Configuration', 'MIGRATING',
         migrate.hostActionPrePackages),
        
        (80, 'Installing Packages', 'PACKAGES',
         packages.hostActionInstallPackages),

        (1, 'Setup Module Loading', 'MODPROBE',
         workarounds.hostActionRedirectLKMLoading),
        
        (1, 'Migrating fstab', 'MIGRATE_FSTAB', fstab.hostActionMigrateFstab),
        (1, 'Migrating Configuration', 'MIGRATING', migrate.hostAction),
        (1, 'Migrating Groups', 'MIGRATING',
         users.hostActionMigrateGroupFile),
        (1, 'Migrating Users', 'MIGRATING',
         users.hostActionMigratePasswdFile),

        # networking.hostAction destroys the network setup for our installation
        # environment, so we have to do this here.  :-/
        (1, 'Updating esxupdate Database', 'ESXUPDATEDB',
         workarounds.hostActionUpdateEsxupdateDatabase),

        (1, 'Updating Network Configuration', 'NETWORKING',
         networking.hostActionUpdate),

        (1, 'Setting License', 'LICENSE', esxlicense.hostAction),

        (1, 'Set Console Memory', 'CONSOLEMEM',
         workarounds.hostActionSetCosMemory),
        
        (1, 'Copying ESX Configuration', 'ESXCONF',
         esxconf.hostActionCopyConfig),
        
        (1, 'Writing Cleanup Script', 'MIGRATING',
         migrate.hostActionCleanupScripts),
        
        (1, 'Running "%post" Script', 'POSTSCRIPT',
         script.hostActionPostScript),

        # Do this after the %post script in case it fails, we want to boot back
        # into the old cos.
        (5, 'Boot Setup', 'BOOTLOADER', bootloader.hostAction),

        (1, 'Checking esx.conf consistency', 'VALIDATE',
         esxconf.validateAction),
        ]

    return retval

def doit(context, stepListType='install'):
    '''Executes the steps needed to do the actual install or upgrade.'''

    if stepListType == 'install':
        if userchoices.getUpgrade():
            steps = _upgradeSteps()
        else:
            steps = _installSteps()
    elif stepListType == 'loadDrivers':
        steps = _loadDriverSteps()

    assert steps

    try:
        context.cb.pushStatusGroup(sum([step[0] for step in steps]))
        for portion, desc, msgID, func in steps:
            context.cb.pushStatus(desc, portion, msgID=msgID)
            func(context)
            context.cb.popStatus()
        context.cb.popStatusGroup()
        
        if stepListType == 'install':
            log.info("installation complete")
        elif stepListType == 'loadDrivers':
            log.info("driver loading complete")
    except exception.InstallCancelled:
        pass

    return

def ensureDriversAreLoaded(func):
    '''Load all of the drivers'''
    import customdrivers
    
    def _wrapper(*args, **kwargs):
        if not customdrivers.DRIVERS_LOADED:
            context = Context(ProgressCallback(StdoutProgressDelegate()))
            sys.stdout.write("Loading system drivers...\n")
            try:
                doit(context, stepListType='loadDrivers')
            except customdrivers.ScriptLoadError, msg:
                # one or more of the init scripts failed to load however
                # not in a critical manner.  we've already logged it, so
                # just keep on truckin'
                pass

        return func(*args, **kwargs)

    return _wrapper

if __name__ == "__main__":
    import doctest
    doctest.testmod()
