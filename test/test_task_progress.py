
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

import os
import sys

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
#sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))

from time import sleep
import task_progress

class TextListener(object):
    def notifyTaskProgress(self, taskTitle, amount):
        percentage = task_progress.getPercentageOfWorkRemaining(taskTitle)
        numDots = int(round(percentage*50))
        numOhs = 50 - numDots
        progressBar = ','*numDots + 'O'*numOhs
        self.write('Progress  ', taskTitle, progressBar)
    def notifyTaskStarted(self, taskTitle):
        self.write('Started   ', taskTitle, '.'*50)
    def notifyTaskFinish(self, taskTitle):
        self.write('Finish    ', taskTitle, 'X'*50)

class StdoutListener(TextListener):
    def write(self, *args):
        print ' '.join( [str(arg) for arg in args] )

class StringListener(TextListener):
    def __init__(self):
        self.buffer = ''
    def write(self, *args):
        self.buffer += ' '.join( [str(arg) for arg in args] )
        self.buffer += '\n'

class IndentedStringListener(StringListener):
    def getBuffer(self):
        ibuf = self.buffer.replace('\n', '\n    ')
        ibuf = '    '+ ibuf
        return ibuf

def test_null():
    listener = StringListener()
    task_progress.addNotificationListener(listener)
    assert listener.buffer == ''
    task_progress.removeNotificationListener(listener)

def test_simple_noamounts():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskA')
    task_progress.taskProgress('taskA')
    task_progress.taskProgress('taskA')
    task_progress.taskProgress('taskA')
    task_progress.taskFinish('taskA')
    assert listener.getBuffer() == '''\
    Started    taskA ..................................................
    Progress   taskA ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   taskA ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   taskA ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Finish     taskA XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_simple_nototal():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskB')
    task_progress.taskProgress('taskB', 5)
    task_progress.taskProgress('taskB', 25)
    task_progress.taskProgress('taskB', 5)
    task_progress.taskFinish('taskB')

    assert listener.getBuffer() == '''\
    Started    taskB ..................................................
    Progress   taskB ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   taskB ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   taskB ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Finish     taskB XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_simple_amounts():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskC', 15)
    task_progress.taskProgress('taskC', 5)
    task_progress.taskProgress('taskC', 5)
    task_progress.taskProgress('taskC', 5)
    task_progress.taskFinish('taskC')
    assert listener.getBuffer() == '''\
    Started    taskC ..................................................
    Progress   taskC ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOO
    Progress   taskC ,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   taskC OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Finish     taskC XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_undershoot():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskUndershoot', 100)
    task_progress.taskProgress('taskUndershoot', 5)
    task_progress.taskProgress('taskUndershoot', 5)
    task_progress.taskProgress('taskUndershoot', 5)
    task_progress.taskFinish('taskUndershoot')
    assert listener.getBuffer() == '''\
    Started    taskUndershoot ..................................................
    Progress   taskUndershoot ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OO
    Progress   taskUndershoot ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OOOOO
    Progress   taskUndershoot ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOO
    Finish     taskUndershoot XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_overshoot():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskOvershoot', 8)
    task_progress.taskProgress('taskOvershoot', 5)
    task_progress.taskProgress('taskOvershoot', 5)
    task_progress.taskProgress('taskOvershoot', 5)
    task_progress.taskFinish('taskOvershoot')
    assert listener.getBuffer() == '''\
    Started    taskOvershoot ..................................................
    Progress   taskOvershoot ,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   taskOvershoot OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   taskOvershoot OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Finish     taskOvershoot XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_interleaved():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('taskE', 15)
    task_progress.taskProgress('taskE', 5)
    task_progress.taskStarted('taskD', 15)
    task_progress.taskProgress('taskD', 5)
    task_progress.taskProgress('taskE', 5)
    task_progress.taskProgress('taskE', 5)
    task_progress.taskProgress('taskD', 5)
    task_progress.taskFinish('taskE')
    task_progress.taskProgress('taskD', 5)
    task_progress.taskFinish('taskD')
    assert listener.getBuffer() == '''\
    Started    taskE ..................................................
    Progress   taskE ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOO
    Started    taskD ..................................................
    Progress   taskD ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOO
    Progress   taskE ,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   taskE OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   taskD ,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Finish     taskE XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    Progress   taskD OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Finish     taskD XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)

def test_subtasks():
    listener = IndentedStringListener()
    task_progress.addNotificationListener(listener)
    task_progress.taskStarted('super', 10)
    task_progress.subtaskStarted('sub1', 'super', 10)
    task_progress.taskProgress('sub1', 5)
    task_progress.taskProgress('sub1', 5)
    task_progress.taskFinish('sub1')

    task_progress.subtaskStarted('sub2', 'super', 10, 5)
    task_progress.taskProgress('sub2', 5)
    task_progress.taskProgress('sub2', 5)
    task_progress.taskFinish('sub2')
    task_progress.taskFinish('super')
    assert listener.getBuffer() == '''\
    Started    super ..................................................
    Started    sub1 ..................................................
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   sub1 ,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   sub1 OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Finish     sub1 XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Started    sub2 ..................................................
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   sub2 ,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Progress   sub2 OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    Finish     sub2 XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    Progress   super ,,,,,,,,,,,,,,,,,,,,,,,,,OOOOOOOOOOOOOOOOOOOOOOOOO
    Finish     super XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    '''
    task_progress.removeNotificationListener(listener)


def main():
    listener1 = StdoutListener()
    task_progress.addNotificationListener(listener1)
    for func in globals():
        if func.startswith('test_'):
            globals()[func]()

if __name__ == '__main__':
    main()
