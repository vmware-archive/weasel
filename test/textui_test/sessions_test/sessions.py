#!/usr/bin/env python
#-*- coding: utf-8 -*-
'''Session support'''

def setupScreens(screenStream):
    """Assemble stream of heads and bodies into sequence of streams."""
    head = None
    body = None
    screens = []
    for fragment in screenStream:
        if head == None:
            if fragment.endswith('----\n'):
                head = fragment
                continue
            else:
                head = ""
        if body == None:
            body = fragment
            screen = head + body
            screens.append(screen)
            head = None
            body = None
    return screens

# vim: set sw=4 tw=80 :
