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
#

from dispatch import DISPATCH_NEXT, DISPATCH_BACK

'''
textengine.py

Basic rendering and interaction engine for text user interface.
Returns tuple [ menuchoice, userinput ]
'''

import os, sys
import getpass
import readline         # needed for prompts

# pseudo-control codes
CLEARSCREEN =   0x01    # clear entire screen
CLEARLINE =     0x02    # clear line
CLEARTOEOL =    0x03    # clear to end of line

# real control codes
BEL =           "\x07"  # audible beep

# _ESC = 0x1b     # escape character

readline.set_completer(lambda x, y: None)  # turn off default completer

class InvalidUserInput(Exception):
    "invalid user input"

def render(content):
    "standard text screen rendering function"
    # TODO: clear here if we want to clear before every screen.
    #_cons_output_oob(CLEARSCREEN)
    if 'title' in content:
        _cons_output(content['title'].ljust(64, '-'))
    _cons_output(content['body'])

def render_oob(cmd):
    """non-text "out-of-band" rendering functions.
    , e.g., clear screen, clear line."
    """
    _cons_output_oob(cmd)

def render_status(msg):
    sys.stdout.write(msg)
    sys.stdout.flush()

def waitinput(menu=None, prompt="> "):
    userinput = _cons_input(prompt).strip()

    if not menu:
        # no choices or state change, just return input
        return [ None, userinput ]

    try:
        menuchoice = menu[userinput]
    except KeyError:
        if '*' in menu:
            menuchoice = menu['*']
        else:
            menuchoice = 'unmatched choice'
            raise InvalidUserInput("Unrecognized option: '%s'" % userinput)
    return [ menuchoice, userinput ]

def waitpasswords(menu=None, prompts=None, short=None):
    """Get password input twice; input values not echoed to screen.
    'prompt' is a pair of prompts, e.g., "Password: " and "Again: ".
    'short' is an input which, if recognized after the first input,
    short-circuits (takes the short way out), and passes back only
    the shorting input; this is useful for things like '<' for
    go-back functions.
    """
    assert len(prompts) == 2, "'prompt' for waitpassword was not a pair."
    assert '*' in menu, "waitpasswords missing menu['*']"
    trial1 = _password_cons_input(prompts[0])
    if short and (trial1 in short):
        menuchoice = menu[trial1]
        return (menuchoice, trial1)
    trial2 = _password_cons_input(prompts[1])
    trials = [trial1, trial2]

    if not menu:
        # no choices or state change, just return input
        return (None, trials)

    menuchoice = menu['*']  # typically a password comparator

    return (menuchoice, trials)

def _cons_output(*args):
    "module-internal output routine.  Can be overridden for testing."
    outstr = "%s" % args
    if outstr[-1] != '\n':
        outstr += '\n'
    print outstr,

def _cons_output_oob(arg):
    """module-internal output routine for out-of-band rendering.
    Can be overridden for testing.
    """
    if arg == CLEARSCREEN:
        os.system('clear > /dev/tty6')      # POSIX only
    elif arg == CLEARLINE:
        # <esc>[2k -- erase entire current line
        pass                    # TODO: implement
    elif arg == CLEARTOEOL:
        # <esc>[k -- erase to end of line
        pass                    # TODO: implement

def _cons_input(prompt):
    "module-internal input routine.  Can be overridden for testing."
    # TODO: perhaps use readline rather than raw_input.
    return raw_input(prompt)

def _password_cons_input(prompt):
    "module-internal password input routine.  Can be overridden for testing."
    return getpass.getpass(prompt)


# vim: set sw=4 tw=80 :
