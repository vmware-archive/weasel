#!/usr/bin/env python
#-*- coding: utf-8 -*-
'''Check that the welcome text UI screen is generated.'''

if __name__ == "__main__":
    import __init__
    __init__.setup_package()

from main import TextUI
import welcome_ui
import fauxTextuiIO as xio

def test_welcome():
    xio.fauxStdin = [ '1' ]
    xio.fauxStdout = []
    welcome = welcome_ui.WelcomeWindow()
    welcome.run()

    # TODO:  both heading tests currently work; might just choose one.
    # heading
    if xio.fauxStdout[0].startswith("OOB:"):
        xio.fauxStdout.pop(0)
    screen = ''.join(xio.fauxStdout)
    print screen
    assert screen.find('ESX 4.0') >= 0
    # screen body
    assert screen.find(welcome_ui.welcomeText) >= 0
    assert screen.find('Continue') >= 0

if __name__ == "__main__":
    test_welcome()


# vim: set sw=4 tw=80 :
