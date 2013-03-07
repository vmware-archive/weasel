
import sys
import vmkctl
import string

def PrintVSwitch():
    info = vmkctl.VirtualSwitchInfoImpl()
    vswitches = info.GetVirtualSwitches()

    format = "% -14s % -9s % -6s % -10s % -5s %s"
    pgFormat = "  % -14s % -6s % -7s %s"

    if not vswitches:
        print "No virtual switches."
        sys.exit()

    print format % \
        ("Switch Name", "# Ports", "Used", "Cfg Ports", "MTU", "Uplinks")

    for vswitch in vswitches:
        if vswitch.GetUplinks():
            uplinks = string.join(vswitch.GetUplinks(), ', ')
        else:
            uplinks = "None"

        print format % \
            (vswitch.GetName(), vswitch.GetNumPorts(),
             vswitch.GetPortsInUse(), vswitch.GetNumConfiguredPorts(),
             vswitch.GetMTU(), uplinks)

        portgroups = vswitch.GetPortGroups()

        if portgroups:
            print "\n" + pgFormat % \
                ("Portgroup Name", "VLAN", "Used", "Uplinks")

            for portgroup in portgroups:
                print pgFormat % \
                    (portgroup.GetName(), portgroup.GetVlanId(), "Unknown",
                     "Unknown")
                     


def AddPortgroup(vswitchName, portgroupName):
    vswitch = GetVSwitchByName(vswitchName)
    if vswitch:
        try:
            vswitch.AddPortGroup(portgroupName)
        except vmkctl.HostCtlException, msg:
            print msg
            print "Couldn't add portgroup \"%s\" to switch \"%s\"." % \
                (portgroupName, vswitchName)
            sys.exit(1)
    else:
        print "Couldn't find vswitch \"%s\"." % (vswitchName,)
        sys.exit(1)

def RemovePortgroup(vswitchName, portgroupName):
    vswitch = GetVSwitchByName(vswitchName)
    if vswitch:
        try:
            vswitch.RemovePortGroup(portgroupName)
        except vmkctl.HostCtlException, msg:
            print msg
            print "Couldn't remove portgroup \"%s\" from switch \"%s\"." % \
                (portgroupName, vswitchName)
    else:
        print "Couldn't find vswitch \"%s\"." % (vswitchName,)
        sys.exit(1)

def GetVSwitchByName(name):
    info = vmkctl.VirtualSwitchInfoImpl()
    if not info.SwitchExists(name):
        return None

    for vswitch in info.GetVirtualSwitches():
        if vswitch.GetName() == name:
            return vswitch
        


def AddVSwitch(name, ports=32):
    info = vmkctl.VirtualSwitchInfoImpl()
    try:
        vs = info.AddVirtualSwitch(name, ports)
    except vmkctl.HostCtlException, msg:
        print msg
        print "Couldn't add virtual switch \"%s\"." % (name)
        sys.exit(1)

    try:
        vs.SetTeamingPolicy(vmkctl.NicTeamingPolicy().GetDefaultPolicy())
        vs.SetSecurityPolicy(vmkctl.PortSecurityPolicy().GetDefaultPolicy())
        vs.SetShapingPolicy(vmkctl.ShapingPolicy().GetDefaultPolicy())
        vs.SetNicCapabilities(vmkctl.NicCapabilities().GetDefaultPolicy())
    except vmkctl.HostCtlException, msg:
        print msg
        print "Couldn't apply policy to vswitch \"%s\"." % (name)
        sys.exit(1)


PrintVSwitch()

