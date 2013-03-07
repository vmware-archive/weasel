#!/usr/bin/env python
#-*- coding: utf-8 -*-
'''Check that the welcome text UI screen is generated.'''

if __name__ == "__main__":
    import __init__
    __init__.setup_package()

from main import TextUI
import welcome_ui
import fauxTextuiIO as xio
import sessions

_screens = None

def test_welcome_errs():
    xio.fauxStdin = [
        # start welcome screen
        'x',    # invalid input -> welcome 
        '2',    # invalid input -> welcome
        '?',    # help
        'x',    # invalid input -> help
        '<',    # welcome
        '!',    # exit confirmation
        '2',    # welcome
        '1',    # next step ...

    ]
    xio.fauxStdout = []
    welcome = welcome_ui.WelcomeWindow()
    welcome.run()

    # TODO:  both heading tests currently work; might just choose one.
    # heading
    if xio.fauxStdout[0].startswith("OOB:"):
        xio.fauxStdout.pop(0)
    _screens = sessions.setupScreens(xio.fauxStdout)
    print _screens

    iterScreens = iter(_screens)
    scr = iterScreens.next()
    assert welcome_ui.welcomeText in scr, 'initial welcome'
    scr = iterScreens.next()
    assert welcome_ui.welcomeText in scr, 'invalid input x, welcome'
    scr = iterScreens.next()
    assert welcome_ui.welcomeText in scr, 'invalid input 2, welcome'
    scr = iterScreens.next()
    assert welcome_ui.welcomeHelpText in scr, 'input ?, help'
    scr = iterScreens.next()
    assert welcome_ui.welcomeHelpText in scr, 'invalid input x, help'
    scr = iterScreens.next()
    assert welcome_ui.welcomeText in scr, 'input <, welcome'
    scr = iterScreens.next()
    assert "really want to exit" in scr, 'input !, exit confirmation'
    scr = iterScreens.next()
    assert welcome_ui.welcomeText in scr, 'input 2, welcome'

if __name__ == "__main__":
    test_welcome_errs()

# vim: set sw=4 tw=80 :
