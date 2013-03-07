#!/usr/bin/python

#
# This is a drop in replacement for esxcfg-nics.cpp written in python to test
# out the functionality of the swig interface.
# 2007.07.05 - patrickd@vmware.com
#
# Copywrite 2007 VMware Inc
# (put legalese here)
#

import sys
import getopt
import vmkctl

def PrintNics():
    info = vmkctl.NetworkInfoImpl()

    format = "% -10s % -8s % -13s % -4s % -9s % -6s % -4s %s"

    pnics = info.GetPnics()

    if pnics:
        print format % \
            ("Name", "PCI", "Driver", "Link", "Speed", "Duplex",
             "MTU", "Description")
    else:
        print "No nics found"
        return

    for nic in pnics:
        pciDev = nic.GetPciDevice()

        pci = "%02x:%02x.%02x" % \
            (pciDev.GetBus(), pciDev.GetBus(), pciDev.GetSlot())

        if nic.IsLinkUp():
            link = "Up"
        else:
            link = "Down"

        if nic.GetDuplex() == vmkctl.DUPLEX_MODE_FULL:
            duplex = "Full"
        else:
            duplex = "Half"

        print format % \
            (nic.GetName(), pci, nic.GetDriverName(), link,
             "%dMbps" % (nic.GetLinkSpeed()), duplex, nic.GetMTU(),
             "%s %s" % (pciDev.GetVendor(), pciDev.GetDevice()))
        

def Usage():
    print """esxcfg-nics <options> [nic]
   -s|--speed <speed>     Set the speed of this NIC to one of 10/100/1000/10000.
                          Requires a NIC parameter.
   -d|--duplex <duplex>   Set the duplex of this NIC to one of 'full' or 'half'.
                          Requires a NIC parameter.
   -a|--auto              Set speed and duplexity automatically.
                          Requires a NIC parameter.
   -l|--list              Print the list of NICs and their settings.
   -r|--restore           Restore the nics configured speed/duplex settings
                          (INTERNAL ONLY)
   -h|--help              Display this message.
"""
    sys.exit(0)

def Restore():
    info = vmkctl.NetworkInfoImpl()
    info.RestorePnics()


def SetSpeed(name, speed=0, duplex='auto'):

    try:
        speed = int(speed)
    except ValueError:
        print "Invalid speed parameter"
        sys.exit(1)

    if speed not in (0, 10, 100, 1000, 10000):
        print "Invalid speed parameter"
        sys.exit(1)

    if duplex == 'auto':
        duplex = vmkctl.DUPLEX_MODE_AUTO
    elif duplex == 'full':
        duplex = vmkctl.DUPLEX_MODE_FULL
    elif duplex == 'half':
        duplex = vmkctl.DUPLEX_MODE_HALF
    else:
        print "Invalid duplex"
        sys.exit(1)
    
    try:
        nic = vmkctl.PnicImpl(name)
        nic.Refresh()
        nic.SetLinkSpeedAndDuplex(speed, duplex)
    except vmkctl.HostCtlException, msg:
        print "Couldn't set speed/duplex for \"%s\"" % (name)
        sys.exit(1)


def Main():

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:d:alrh",
            ["speed=", "duplex=", "auto", "restore", "help"])
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    if not opts:
        Usage()
        sys.exit(2)

    speed = 0
    duplex = "auto"

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            Usage()
            sys.exit()
        elif opt in ("-a", "--auto"):
            if not args:
                Usage()
                sys.exit(2)
            SetSpeed(args[0], 0, "auto")
            sys.exit()
        elif opt in ("-l", "--list"):
            PrintNics()
            sys.exit()
        elif opt in ("-r", "--restore"):
            Restore()
            sys.exit()
        if opt in ("-s", "--speed"):
            speed = arg
        if opt in ("-d", "--duplex"):
            duplex = arg
  
    if speed and duplex != "auto":
        if not args:
            Usage()
            sys.exit(2)
        SetSpeed(args[0], speed, duplex)
    else:
        Usage()
        sys.exit(2)

Main()
