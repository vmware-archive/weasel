#!/usr/bin/env python
#-*- coding: utf-8 -*-
'''Sanity tests to confirm that the test environment is being built up.
'''

def test_noop():
   assert True

def test_faux():
    import fauxroot
    assert fauxroot.FAUXROOT == None
    import fauxTextuiIO
    assert len(fauxTextuiIO.fauxStdin) >= 0

def test_goodconfig1():
    import fauxconfig
    assert fauxconfig.vmkctl
    assert fauxconfig.parted

# vim: set sw=4 tw=80 :
