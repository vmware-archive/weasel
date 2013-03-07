
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

class RegexLocator:
    bootloader = '((mbr)|(none)|(partition))'

    anywords = r'(\w+)'

    #
    # A valid md5 checksum starts with $1$, is up to 34 characters long, and
    # contains alpha-numeric characters plus some symbols.
    #
    md5 = r'(\$1\$[a-zA-Z0-9\.\$/]{22,31})'

    #
    # Root directory OR a repeating sequence of '/' followed by characters,
    # with an optional '/' at the end of the sequence.
    #
    directory = r'(/|(/[^/]+)+/?)'

    networkproto = '((static)|(dhcp))'

    serialnum = r'(\w{5}-\w{5}-\w{5}-\w{5}-\w{5})'

    preInterpreter = '((python)|(bash))'
    
    postInterpreter = '((perl)|(python)|(bash))'

    firewallproto = '((tcp)|(udp))'

    portdir = '((in)|(out))'

    # take first 128 characters
    portname = r'(\w\w{,127})'

    # we should limit this range
    port = r'(\d+)'

    # Combination of mount-point/vmfs-volume for the partition command.  Can be
    # 'None' for mountpoint if the partition is not to be mounted or 'swap'
    # if it is the swap partition.
    mountpoint = r'(([^/]+|(/|(/[^/]+)+/?)))'

    # vmfs volume labels
    vmfsvolume = r'([^/]+)'

    vmdkname = r'([^/]+)'

    vmdkpath = r'((?:[^/]+/)+)([^/]+\.vmdk)'

    uuid = r'(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})'
