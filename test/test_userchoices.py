
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

import sys

sys.path.append( '..' )

from userchoices import *

def genericTest( setFn, getFn, expectedLen, badArgs, goodArgs, asserts ):
    try:
        setFn( *badArgs )
        assert False, 'should throw TypeError, bad args'
    except TypeError,e:
        pass

    setFn( *goodArgs )
    result = getFn()
    assert len( result ) == expectedLen, 'dict not expected length'

    for k,v  in asserts.items():
        assert result[k] == v, "%s should be %s" % (k, str(v))

    return result

def test_toggles():
    setParanoid( True )
    assert getParanoid() == True

    setUpgrade( True )
    assert getUpgrade() == True

    setReboot( True )
    assert getReboot() == True

    setAcceptEULA( True )
    assert getAcceptEULA() == True

    setZeroMBR( True )
    assert getZeroMBR() == True

    setParanoid( False )
    assert getParanoid() == False

    setUpgrade( False )
    assert getUpgrade() == False

    setReboot( False )
    assert getReboot() == False

    setAcceptEULA( False )
    assert getAcceptEULA() == False

    setZeroMBR( False )
    assert getZeroMBR() == False

def test_keyboard():
    d = genericTest( setKeyboard, getKeyboard, 6, 
                     (), ('one', 'foo','bar','baz','asdf','jkl;'),
                     {'name':'foo'}
                   )

def test_auth():
    d = genericTest( setAuth, getAuth, 17, 
                     (), ('foo','bar','baz','asdf','qwer'),
                     {'md5':'foo', 'kerberosRealm':None}
                     )
    setAuth( 'mmm', 'sss', 'nnn', None, 'lll', 
             ldapServer='ls', ldapBaseDN='lbdn', ldapTLS=True )
    d = getAuth()
    assert d['ldapTLS'] == True, 'ldap tls should be true'

def test_boot():
    d = genericTest( setBoot, getBoot, 7,
                     (), ('foo',),
                     {'upgrade':'foo', 'password':''}
                   )

    setBoot( upgrade=False, location=BOOT_LOC_PARTITION )
    d = getBoot()
    assert d['location'] == BOOT_LOC_PARTITION, 'location should be part'

def test_clearpartitions():
    d = genericTest( setClearPartitions, getClearPartitions, 2, 
                     (1,2,3,4,5), (),
                     {'drives':[]}
                   )

def test_mediaLocation():
    d = genericTest( setMediaLocation, getMediaLocation, 1, 
                     (), ('http://example.com/weasel/dir/',),
                     {'mediaLocation':'http://example.com/weasel/dir/'}
                   )

def test_rootPassword():
    d = genericTest( setRootPassword, getRootPassword, 2, 
                     (), ('foo','crypt'),
                     {'password':'foo'}
                   )

def test_timezone():
    d = genericTest( setTimezone, getTimezone, 4, 
                     (), ('foo',),
                     {'tzName':'foo',
              'offset': None,
              'city': None,
              'isUTC': True}
                   )

def test_vmlicense():
    d = genericTest( setVMLicense, getVMLicense, 4, 
                     (), ('foo', 'bar', 'baz'),
                     {'server': None}
                   )
    d = genericTest( setVMLicense, getVMLicense, 4, 
                     (), ('foo', 'bar', 'baz', 'bork'),
                     {'mode':'foo', 'server':'bork'}
                   )

def test_mouse():
    d = genericTest( setMouse, getMouse, 3, 
                     (), ('foo', 'bar', 1),
                     {'mouseType':'foo'}
                   )
    assert bool(d['emuThree']), 'emuThree should be true'

def test_lang():
    d = genericTest( setLang, getLang, 1, 
                     (), ('foo',),
                     {'lang':'foo'}
                   )

def test_langSupport():
    d = genericTest( setLangSupport, getLangSupport, 2, 
                     (), ('foo', 'bar'),
                     {'lang':'foo', 'default':'bar'}
                   )

def test_ESXFirewall():
    d = genericTest( setESXFirewall, getESXFirewall, 2, 
                     (), ('foo', 'bar'),
                     {'incoming':'foo', 'outgoing':'bar'}
                   )

def test_network():
    d = genericTest( setCosNetwork, getCosNetwork, 4, 
                     (), ('foo', 'bar', 'baz', 'asdf'),
                     {'gateway':'foo', 'hostname':'asdf'}
                   )
    d = genericTest( setVmkNetwork, getVmkNetwork, 1, 
                     (), ('foo',),
                     {'gateway':'foo'}
                   )


def test_nics():
    funcDict = {'cos' : {'add':addCosNIC, 'get':getCosNICs, 'del':delCosNIC},
                'vmk' : {'add':addVmkNIC, 'get':getVmkNICs, 'del':delVmkNIC}}

    for networkType in 'cos', 'vmk':
        addNIC = funcDict[networkType]['add']
        getNICs = funcDict[networkType]['get']
        delNIC = funcDict[networkType]['del']

        for nic in getNICs():
            delNIC(nic)

        try:
            addNIC()
            assert False, 'should throw TypeError, needs more args'
        except TypeError,e:
            pass

        # device, vlanID, bootProto=NIC_BOOT_DHCP, ip='', netmask=''
        addNIC( 'eth0', 'vvv' )
        addNIC( 'eth1', 'vvvv', NIC_BOOT_STATIC, '123.123.123.0',
                      '255.255.255.255' )
        pDict = dict( device='eth2', vlanID='vee', bootProto=NIC_BOOT_DHCP,
                      ip='', netmask='' )
        addNIC( **pDict )

        nics = getNICs()

        assert len( nics ) == 3, 'NICs list not length 3'
        assert pDict in nics, 'pdict should be in NICs'

        delNIC( pDict )
        nics = getNICs()
        assert len( nics ) == 2, 'NICs list not length 2'

        p1 = nics[0]
        assert p1['device'] == 'eth0', 'p1 device should be eth0'

        delNIC( p1 )
        nics = getNICs()
        assert len( nics ) == 1, 'NICs list not length 1'


def test_portrules():
    try:
        addPortRule()
        assert False, 'should throw TypeError, needs more args'
    except TypeError,e:
        pass

    addPortRule( PORT_STATE_OPEN, 1, PORT_PROTO_TCP,
                    PORT_DIRECTION_IN, name="asdf" )
    addPortRule( PORT_STATE_CLOSED, 2, PORT_PROTO_UDP,
                    PORT_DIRECTION_OUT )
    pDict = dict( state=PORT_STATE_OPEN, number=3, protocol=PORT_PROTO_TCP,
                  direction=PORT_DIRECTION_IN, name='qwer' )
    addPortRule( **pDict )

    ports = getPortRules()

    assert len( ports ) == 3, 'PortRules list not length 3'
    assert pDict in ports, 'pdict should be in PortRules'

    delPortRule( pDict )
    ports = getPortRules()
    assert len( ports ) == 2, 'PortRules list not length 2'

    p1 = ports[0]
    assert p1['name'] == 'asdf', 'p1 name should be asdf'

    delPortRule( p1 )
    ports = getPortRules()
    assert len( ports ) == 1, 'PortRules list not length 1'



if __name__ == "__main__":

    #if the user specifies a specific test to run, just run that then exit
    testName = None
    try:
        testName = sys.argv[1]
    except IndexError:
        pass
    if testName:
        print "________Just running ", testName
        locals()[testName]()
        print "________PASSED"
        sys.exit()
    else:
        print 'You can run this test suite using nosetests'


    testNames = [ n for n in locals().keys() if n.startswith('test_') ]
    for testName in testNames:
        print '\n________Running test', testName
        try:
            locals()[testName]()
            print "________PASSED"
        except Exception, e:
            print "*Exception caught:"
            print "*",  e.__class__.__name__, ":",  e
            print "*",  e.__doc__
            print "SYS EXC INFO", sys.exc_info()[0]
            print "________** FAIL **"

