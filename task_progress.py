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
Asynchronous, decoupled notification module
'''

from log import log
from weakref import WeakKeyDictionary

_listeners = WeakKeyDictionary()
_runningTasks = {}
_lock = False # not threadsafe, of course.
_pendingEvents = []

#------------------------------------------------------------------------------
def taskStarted(taskTitle, estimatedAmount=None):
    newTask = Task(taskTitle, estimatedAmount)
    _runningTasks[taskTitle] = newTask
    _broadcastTaskStarted(newTask.title)

#------------------------------------------------------------------------------
def subtaskStarted(taskTitle, supertaskTitle, estimatedAmount=None, share=0):
    newTask = Task(taskTitle, estimatedAmount)
    _runningTasks[taskTitle] = newTask
    if supertaskTitle not in _runningTasks:
        log.warn('no supertask found for subtask')
        return
    else:
        supertask = _runningTasks[supertaskTitle]
        supertask.addSubtask(newTask, share)
    _broadcastTaskStarted(newTask.title)

#------------------------------------------------------------------------------
def reviseEstimate(taskTitle, estimate):
    if taskTitle not in _runningTasks:
        log.warn('No task found. Could not revise estimate.')
        return
    task = _runningTasks[taskTitle]
    task.reviseEstimate(estimate)

#------------------------------------------------------------------------------
def taskProgress(taskTitle, amountCompleted=1):
    if taskTitle not in _runningTasks:
        log.debug('Progress happened on a task that has not started')
        return
    task = _runningTasks[taskTitle]
    task.progress(amountCompleted)

#------------------------------------------------------------------------------
def taskFinish(taskTitle):
    if taskTitle not in _runningTasks:
        log.warn('A task finished that has not started')
        return
    task = _runningTasks[taskTitle]
    task.finish()

#------------------------------------------------------------------------------
def getAmountOfWorkRemaining(taskTitle=None):
    if taskTitle == None:
        total = 0
        for task in _runningTasks:
            total += task.amountRemaining
        return total
    if taskTitle not in _runningTasks:
        log.warn('Can not get amount of work remaining for unknown task')
        return 0
    return _runningTasks[taskTitle].amountRemaining

#------------------------------------------------------------------------------
def getPercentageOfWorkRemaining(taskTitle=None):
    if taskTitle == None:
        total = 0
        remaining = 0
        for task in _runningTasks:
            remaining += task.amountRemaining
            total += task.estimatedTotal
        return float(remaining)/total
    if taskTitle not in _runningTasks:
        log.warn('Can not get percentage of work remaining for unknown task')
        return 0
    return _runningTasks[taskTitle].percentRemaining()


#------------------------------------------------------------------------------
def addNotificationListener(listener):
    enqueueEvent('_addNotificationListener', (listener,))
    consumeEvents()

def _addNotificationListener(listener):
    global _listeners
    _listeners[listener] = 1

#------------------------------------------------------------------------------
def removeNotificationListener(listener):
    enqueueEvent('_removeNotificationListener', (listener,))
    consumeEvents()

def _removeNotificationListener(listener):
    global _listeners
    del _listeners[listener]

#------------------------------------------------------------------------------
def _broadcastTaskStarted(taskTitle):
    enqueueEvent('notifyTaskStarted', (taskTitle,))
    consumeEvents()

#------------------------------------------------------------------------------
def _broadcastTaskProgress(taskTitle, amountCompleted):
    enqueueEvent('notifyTaskProgress', (taskTitle,amountCompleted))
    consumeEvents()

#------------------------------------------------------------------------------
def _broadcastTaskFinish(taskTitle):
    enqueueEvent('notifyTaskFinish', (taskTitle,))
    consumeEvents()

#------------------------------------------------------------------------------
def consumeEvents():
    global _lock
    global _pendingEvents
    if _lock:
        # tried to recursively enter consumeEvents
        return

    listenerMethods = ['notifyTaskStarted',
                       'notifyTaskProgress',
                       'notifyTaskFinish']
    _lock = True
    while _pendingEvents:
        currentEvents = list(_pendingEvents)
        _pendingEvents = []
        for funcName, args in currentEvents:
            if funcName in listenerMethods:
                # copy to ensure size doesn't change during iteration
                listenersCopy = _listeners.keys()
                for listener in listenersCopy:
                    method = getattr(listener, funcName)
                    method(*args)
            else: #else it is a module function
                func = globals()[funcName]
                func(*args)
                
    _lock = False

#------------------------------------------------------------------------------
def enqueueEvent(methodName, args):
    _pendingEvents.append((methodName, args))

#------------------------------------------------------------------------------
class Task(object):
    def __init__(self, title, estimatedTotal=None):
        self.title = title
        self.subtasks = {}
        self.subtaskShares = {} #maps the subtask name to amount
        if estimatedTotal != None:
            assert estimatedTotal > 0, 'estimated total work must be > 0'
        self.estimatedTotal = estimatedTotal
        self._amountRemaining = estimatedTotal

    def reviseEstimate(self, newEstimate):
        percentRemaining = self.percentRemaining()
        self._amountRemaining = percentRemaining * newEstimate
        self.estimatedTotal = newEstimate
        _broadcastTaskProgress(self.title, 0)

    def addSubtask(self, subtask, share=0):
        addNotificationListener(self)
        self.subtasks[subtask.title] = subtask
        self.subtaskShares[subtask.title] = share

    def notifyTaskStarted(self, taskTitle):
        '''A subtask has started'''
        if taskTitle not in self.subtasks:
            return
        self.progress(0) # "touch" myself
        
    def notifyTaskProgress(self, taskTitle, amountCompleted):
        '''Progress has been made on a subtask'''
        if taskTitle not in self.subtasks:
            return
        self.progress(0) # "touch" myself
        # ignore subtask progress until it finishes

    def notifyTaskFinish(self, taskTitle):
        '''A subtask has completed'''
        if taskTitle not in self.subtasks:
            return
        subtask = self.subtasks[taskTitle]
        if taskTitle in self.subtaskShares:
            share = self.subtaskShares[taskTitle]
            self.progress(share)
            del self.subtasks[taskTitle]
            del self.subtaskShares[taskTitle]
            if not self.subtasks:
                removeNotificationListener(self)

    def progress(self, amountCompleted=1):
        if self._amountRemaining != None and amountCompleted:
            self._amountRemaining -= amountCompleted
        _broadcastTaskProgress(self.title, amountCompleted)

    def finish(self):
        self._amountRemaining = 0
        _broadcastTaskFinish(self.title)
        global _runningTasks
        del _runningTasks[self.title]

    def percentRemaining(self):
        if self.estimatedTotal == None:
            return 1.0
        if self._amountRemaining <= 0:
            return 0.0
        else:
            return float(self._amountRemaining)/self.estimatedTotal

    def getAmountRemaining(self):
        if self.estimatedTotal == None:
            return 1
        elif self._amountRemaining <= 0:
            return 0
        else:
            return self._amountRemaining
    amountRemaining = property(getAmountRemaining)

