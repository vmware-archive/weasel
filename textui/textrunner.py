
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

import sys
from log import log
import exception
import textengine
import tidy
from consts import ExitCodes


def _buildSSXnMenu(*args):
    """Build menu from item mnemonics."""
    menu = '\n' + '\n'.join(args) + '\n\n'
    return menu

class SubstepTransitionMenu:
    """Substate transition menus.
    Members computed when textrunner module is loaded.
    For example, 'THX' creates menu item for Continue/Help/Exit.
    """
    _continue = ' 1) Continue'
    _keep     = ' 1) Keep'
    _change   = ' 2) Change'
    _ok       = ' 1) OK'
    _yes      = ' 1) Yes'
    _no       = ' 2) No'
    _back     = ' <) Back'
    _help     = ' ?) Help'
    _exit     = ' !) Exit'

    Back = _buildSSXnMenu(_back)
    BackHelp = _buildSSXnMenu(_back, _help)
    ContHelpExit = _buildSSXnMenu(_continue, _help, _exit)
    KeepChangeHelpExit = _buildSSXnMenu(_keep, _change, _help, _exit)
    KeepChangeBackHelpExit = _buildSSXnMenu(_keep, _change, _back, _help, _exit)
    OkBack = _buildSSXnMenu(_ok, _back)
    YesNo = _buildSSXnMenu(_yes, _no)
    YesNoBack = _buildSSXnMenu(_yes, _no, _back)
    YesNoBackHelp = _buildSSXnMenu(_yes, _no, _back, _help)
    YesNoHelpExit = _buildSSXnMenu(_yes, _no, _help, _exit)

TransMenu = SubstepTransitionMenu

class TextRunner(object):
    """A base class for text user interface steps.
    TextRunner provides a framework for a step and its substeps (i.e.,
    states).  Key characteristics:
    * 'run' function to sequence through substeps
    * transitions to next or previous step
    * nesting of substeps
    * displayable and non-display substeps
    * scrolling of text which exceed screen height
    Other notes:
    * Scrolling steps currently need to provide their own display
      substeps; UI menu tends to be unique, but determining the bounds
      of what to display appears to have a common pattern.
    * TextRunner possibly should be combined with module 'textengine'.
    TODO:
    * In some cases, nested substeps might warrant separate classes.  There is
      currently, no cross-class stack support.  (Unclear if this is even
      needed if these are just function calls.)
    """

    def __init__(self, substepLookup=None):
        # self.substep should initialized  in subclass __init__.
        self.userinput = None
        self.substepEnv = None
        self.substepStack = []
        self.substepPrev = None
        log.debug("*** CLASS %s ***" % self.__class__.__name__)

        # TODO: remove after migration
        self.cancelConfirmed = self.exitConfirmed
        self.cancel = self.exit

        self.dispatch = None

    # ---- hooks to next or previous step ----
    def stepForward(self):
        "Transition forward to next Dispatcher step."
        self.setSubstepEnv( {'nextstep': textengine.DISPATCH_NEXT } )

    def stepBack(self):
        "Transition backward to previous Dispatcher step."
        self.setSubstepEnv( {'nextstep': textengine.DISPATCH_BACK } )

    def exit(self):
        "Did the user really mean to exit?"
        ui = {
            'title': 'Exit installation',
            'body': 'Do you really want to exit installation and reboot?\n' +
                TransMenu.YesNo,
            'menu': {
                '1': self.exitConfirmed,
                '2': self.popSubstep2
            }
        }
        if self.substep not in (self.topSubstepStack(), self.substepPrev):
            self.pushSubstep()
        self.setSubstepEnv(ui)

    def exitConfirmed(self):
        """Terminate installer execution and reboot.
        Was named 'cancelConfirmed'.  Use both names while migrating.
        """
        tidy.doit()
        sys.exit(ExitCodes.IMMEDIATELY_REBOOT)

    # ---- substep environment ----
    def setSubstepEnv(self, env):
        "Assign substep for execution by run()."
        self.substepEnv = env

    def pushSubstep(self):
        "Push previous substep onto stack; will return there on pop."
        self.substepStack.append(self.substepPrev)

    def popSubstep(self):
        "Assign substep from stack, and pop."
        self.setSubstepEnv( {'next': self.substepStack[-1] } )
        del self.substepStack[-1]

    def popSubstep2(self):
        "Assign substep from stack, and pop."
        self.setSubstepEnv( {'next': self.substepStack[-1] } )
        self.substepPrev = self.substepStack[-1]        # copy top to prev
        del self.substepStack[-1]
        # self.printSubstepStack()      # for debugging


    def topSubstepStack(self):
        "Get top of stack."
        if self.substepStack:
            top = self.substepStack[-1]
        else:
            top = None
        return top

    def printSubstepStack(self):
        "Print content of substep stack; for debugging purposes."
        print "vvvv stack vvvv"
        for i, item in enumerate(self.substepStack):
            print '%d: %s' % (i, item)
        print "^^^^ stack ^^^^"

    # ---- scrollable text ----
    # NICE TODO: factor out scrollable properties to a separate class
    def setScrollEnv(self, scrollable, stride):
        "Assign text list to scroll and line limit."
        self.scrollable = scrollable
        self.stride = stride
        self.startStride = 0

    def scrollForward(self):
        "Scroll forward."
        self.startStride = min(self.startStride+self.stride,
            len(self.scrollable))
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def scrollBack(self):
        "Scroll backward."
        self.startStride = max(self.startStride-self.stride, 0)
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def buildScrollDisplay(self, scrollable, title,
        acceptor, acceptGuide, addHelp=True, addCancel=True,
        allowStepBack=False, allowStepRestart=False, prolog=''):
        """Implement scrolling display with one-line guide menu.
        Invoked by self.scrollDisplay().
        When scrolling back at the front of a list:
            allowStepBack goes to previous step.
            allowStepRestart goes to start of current step.
        """

        lo = self.startStride
        hi = self.startStride + self.stride

        guides = [acceptGuide,]
        menu = {'*': acceptor}

        # check for scroll forward
        if hi < len(scrollable):
            guides.append("<enter>: more")
            menu[''] = self.scrollForward

        # check for scroll back or step back
        if lo != 0:
            menu['<'] = self.scrollBack
        elif allowStepBack:     # lo == 0
            menu['<'] = self.stepBack
        elif allowStepRestart:
            menu['<'] = self.start
        # else we're just stuck at the beginning of the scrolling list.
        if '<' in menu:
            guides.append("'<': back")

        # check for help
        if addHelp:
            guides.append("'?': help")
            menu['?'] = self.help

        if addCancel:
            guides.append("'!': exit")
            menu['!'] = self.cancel

        # assemble guides, body, ui
        guideText = "[%s]" % ', '.join(guides)
        scrollContent = '\n'.join(scrollable[lo:hi])
        if not scrollContent:
            scrollContent = '(list is empty)'
        body = ''
        for elem in (prolog, scrollContent, guideText):
            if elem:
                body += elem + '\n'

        ui = {'title': title, 'body': body, 'menu': menu}

        self.setSubstepEnv(ui)

    # ---- input from scrollable text ----

    def getScrollChoice(self, maxValue=0):
        """Get numeric index of choice in self.scrollable.
        Caller should handle IndexError and ValueError from this
        function.
        """
        try:
            selected = int(self.userinput)-1    # revert to 0-indexed
        except ValueError, msg:
            if self.userinput == '':
                raise ValueError, "no input selection entered"
            elif not self.userinput.isdigit():
                raise ValueError, \
                    "Expected decimal number as input, but got '%s'." % \
                    self.userinput
            else:
                raise ValueError, msg
        # We really shouldn't just check on # of lines in the scrolling window.
        scrollValue = len(self.scrollable)
        if maxValue:
            scrollValue = maxValue
        if selected < 0 or selected >= scrollValue:
            raise IndexError, \
                "Number %s is out of range.  Expecting a value between 1 and %d." % \
                (self.userinput, scrollValue)

        return selected

    def getScrollMultiChoices(self):
        """Get numeric indices of multiple choices of self.scrollable.
        Caller should handle IndexError and ValueError from this
        function.
        """
        try:
            inputs = self.userinput.split(',')
        except AttributeError, msg:
            raise ValueError, "unexpected input problem: " + str(msg)

        numberList  = []
        for nibble in inputs:
            try:
                number = int(nibble)-1    # revert to 0-indexed
            except ValueError, msg:
                if nibble == '':
                    raise ValueError, "no input selection entered"
                elif not self.userinput.isdigit():
                    raise ValueError, \
                        "Expected decimal numbers as input, but got '%s'." % \
                        self.userinput
                else:
                    raise ValueError, msg
            if (0 <= number < len(self.scrollable)):
                numberList.append(number)
            else:
                raise IndexError, \
                    "Number %s is out of range.  Expecting values between 1 and %d." % \
                    (nibble, len(self.scrollable))

        # Lets make sure we return only unique values.
        return list(set(numberList))


    # ---- error handling ----
    def errorPushPop(self, title, body):
        errorUI = {
             'title': title,
             'body': textengine.BEL + body,
             'menu': {'<': self.popSubstep},
        }
        if self.substep not in (self.topSubstepStack(), self.substepPrev):
            self.pushSubstep()
        self.setSubstepEnv(errorUI)

    # ---- help handling ----
    def helpPushPop(self, title, body):
        helpUI = {
             'title': title,
             'body': body,
             'menu': {'<': self.popSubstep},
        }
        if self.substep not in (self.topSubstepStack(), self.substepPrev):
            self.pushSubstep()
        self.setSubstepEnv(helpUI)

    # ---- development aides ----
    def notifyNotYetImplemented(self, shortmsg):
        print 64*'-'
        print 'NOT YET IMPLEMENTED: ', shortmsg
        print 64*'-'
        print ''
        self.setSubstepEnv({'next': self.start})

    # run - the intra-step main loop
    def run(self):
        """main loop of the class.  General substep runs:
        * displayable have 'body' and 'menu' attributes.
        * non-displayable as a 'next' target.
        * transitions to Dispatcher steps have 'nextstep' value.
        """

        # Generic substep stream start-up
        # If step doesn't have self.start, then it has to explicitly
        # assign self.substep.  Furthermore, step is not re-startable.
        if not hasattr(self,'substep') and  hasattr(self, 'start'):
            self.substep = self.start

        while True:
            try:
                substep = self.substep
            except Exception, ex:
                log.warn(str(ex))
                substep = self.start
            if substep:
                substep()   # execute the substep
            else:
                log.warn("returning from TextRunner.run()")
                return textengine.DISPATCH_NEXT
            if 'body' in self.substepEnv:
                # This is a user interface (ui) step.
                ui = self.substepEnv
                textengine.render(ui)

                inputType = ui.get("input", "default")
                assert inputType in ['default', 'passwords'], \
                     'unknown inputType: %s' % inputType

                self.substepPrev = self.substep  # save in case push/pop

                # build parameter lists and invoke
                if inputType == 'default':
                    prompt = ui.get('prompt', '> ')
                elif inputType == 'passwords':
                    # plural because we always want two trials of passwords
                    prompts = ui.get('prompts',
                        ['Password: ','Confirm password: '])
                    short = ui.get('short', None)
                else:
                    raise ValueError, 'unrecognized type of input'

                try:
                    ui['menu'].setdefault('!', self.cancel)
                    if inputType == 'default':
                        nextstate, self.userinput = \
                            textengine.waitinput(ui['menu'], prompt=prompt)
                        log.debug('substep %s - input:  %s' %
                            (self.substep.im_func.__name__, self.userinput))
                    elif inputType == 'passwords':
                        nextstate, self.userinput = \
                            textengine.waitpasswords(ui['menu'], prompts, short)
                        log.debug('substep %s - password' % self.substep)
                    else:
                        raise ValueError, 'unrecognized type of input'
                except Exception, ex:
                    msg = str(ex)
                    if msg:
                        log.warn(msg)
                        if msg[-1] != '\n':
                            msg += '\n'
                    if isinstance(ex, textengine.InvalidUserInput):
                        print msg, textengine.BEL
                        nextstate = self.substep   # do not change substep
                    elif isinstance(ex, EOFError):
                        print textengine.BEL
                        nextstate = self.substep   # do not change substep
                    else:
                        log.error('unknown step error')
                        print msg, textengine.BEL
                        assert hasattr(self, 'start'), 'step restart failure'
                        nextstate = self.start

                self.substep = nextstate  # where to go next

            elif 'next' in self.substepEnv:
                self.substep = self.substepEnv['next']
            elif 'nextstep' in self.substepEnv:
                return self.substepEnv['nextstep']
            else:
                log.error('undetermined substep.  exiting.')
                raise SystemExit, 'undetermined substep.'


