#!/usr/bin/env python
#-*- coding: utf-8 -*-
"setup and teardown methods for sessions_test."

import os.path
import sys

def setup_package():
    addPath('../../faux')
    import fauxroot

    addPath('../../good-config.1')
    import fauxconfig
    sys.path.pop()

    addPath('../../../textui')  # the Stoat run-time code

def teardown_package():
    pass



def addPath(lib):
    absolutePath = os.path.abspath(os.path.join(os.path.dirname(__file__), lib))
    #print 'attempt to add', absolutePath
    if absolutePath not in sys.path:
        sys.path.insert(0, absolutePath)
        print 'added', absolutePath

# vim: set sw=4 tw=80 :
