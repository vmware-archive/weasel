#!/usr/bin/env python
#-*- coding: utf-8 -*-
'''Check text installer EULA functions is generated.'''

if __name__ == "__main__":
    import __init__
    __init__.setup_package()

from main import TextUI
import eula_ui
import userchoices
import fauxTextuiIO as xio
import sessions

from nose.tools import raises

_LicenseTitles = [
    'VMWARE MASTER END USER LICENSE AGREEMENT',         # GA
    'MASTER SOFTWARE BETA TEST AGREEMENT',              # beta
]

def test_eula():
    "Check step name, license title."
    xio.fauxStdin = ['']
    xio.fauxStdout = []
    inputCount = len(xio.fauxStdin)
    eula = eula_ui.EulaWindow()
    raises(SystemExit)(eula.run)()

    sessionOutput = ''.join(xio.fauxStdout)

    # step name check
    assert xio.fauxStdout[0].find(
        'End User License Agreement'.ljust(64, '-')) >= 0
    # license title check
    found = False
    for title in _LicenseTitles:
        if title in sessionOutput:
            found = True
            print "Found license:", title
            break
    assert found

    # screen-count check -- not quite enough for a separate step
    screenCount = 0
    for text in xio.fauxStdout:
        if text.find('--------\n') >= 0:
            screenCount += 1
    assert screenCount == inputCount + 1

def test_eulaAccept():
    "Force EULA toggle in userchoice to False, run step to set to True."
    xio.fauxStdin = ['', '', '', '<', 'accept']
    xio.fauxStdout = []
    inputCount = len(xio.fauxStdin)
    eula = eula_ui.EulaWindow()

    userchoices.setAcceptEULA(False)
    assert userchoices.getAcceptEULA() == False
    eula.run()          # runs complete step; finishes before EOF.
    assert userchoices.getAcceptEULA() == True

    # lines below to assist debugging test
    #sessionOutput = ''.join(xio.fauxStdout)
    #print sessionOutput

if __name__ == "__main__":
    test_eula()
    test_eulaAccept()

# vim: set sw=4 tw=80 :
