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


'''A module for faking the standard input and output streams.
'''

import sys, os

for lib in [ '.', '..', '../..' ]:
    if os.path.isdir(lib+'/../weasel/textui'):
        sys.path.insert(0, os.path.abspath(lib))
        sys.path.insert(0, os.path.abspath(lib+'/textui'))
        break

import textengine

# Fake stdio buffers; we don't capture stderr.
# Each element of FAUXIO is a list of strings.
fauxStdin, fauxStdout = [], []

oldConsIO = ( textengine._cons_input, textengine._cons_output)

def newConsInput(prompt):
    if len(fauxStdin) > 0:
        # read a single string
        return fauxStdin.pop(0)
    else:
        raise SystemExit()

textengine._cons_input = newConsInput

def newConsOutput(*args):
    outstr = "%s" % args
    if outstr[-1] != '\n':
        outstr += '\n'
    fauxStdout.append(outstr)

def newConsOutputOob(*args):
    outstr = 'OOB:'
    for a in args:
        s = "<%s:%s>" % (type(a), str(a))
        outstr += s
    outstr += '\n'
    fauxStdout.append(outstr)


textengine._cons_output = newConsOutput
textengine._cons_output_oob = newConsOutputOob

import password_ui

def fauxPswdInput(_prompt):
    textengine._cons_input = newConsInput
    return ("mypass", "mypass")

password_ui._pswd_cons_input = fauxPswdInput

if __name__ == "__main__":
    # simple test
    fauxStdin = ['first', 'second', 'third' ]
    content = { 'title': 'sample page',
        'body': 'Here are a\ncouple of lines of text' }
    textengine.render(content)
    instr = raw_input('a prompt')

    print fauxStdin
    print instr
    print fauxStdout

# vim: set sw=4 tw=80 :
