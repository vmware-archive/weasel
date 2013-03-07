
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

import os
import sys
import shutil

TEST_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

import consts

from users import *
import userchoices

from migrate_support import cmpMigratedFiles

def test_Authentication():
    #
    # test default values are consistent
    #
    expValue = ['--disablenis', '--disableldap', '--disableldapauth', '--disableldaptls', '--disablekrb5']
    auth = Authentication()
    assert expValue == auth.getArgList(), "%s != %s" % (
        expValue, auth.getArgList())

    #
    # test all values scenario
    #
    userchoices.setAuth( nis=1, kerberos=1, ldap=1, \
                         nisServer='myserver', nisDomain='mydomain', \
                         kerberosRealm='kb5realm', kerberosKDC='kb5KDC', \
                         kerberosServer='kb5Server', ldapAuth=1, \
                         ldapServer='ldapServer', ldapBaseDN='baseDN', \
                         ldapTLS=1)

    expValue = ['--enablenis', '--nisdomain', 'mydomain', '--nisserver', 'myserver', '--enableldap', '--enableldapauth', '--ldapserver', 'ldapServer', '--ldapbasedn', 'baseDN', '--enableldaptls', '--enablekrb5', '--krb5realm', 'kb5realm', '--krb5kdc', 'kb5KDC', '--krb5adminserver', 'kb5Server']

    options = userchoices.getAuth()
    auth = Authentication(options)
    assert expValue == auth.getArgList(), "%s != %s" % (
        expValue, auth.getArgList())
   
CRYPT_PASSWORD_LENGTH = 13
MD5_PASSWORD_LENGTH = 34

def test_Password():
    passwordAccount = 'account'
    passwordToken = 'password'
    #
    # test password setter/getter
    #
    passwd = Password(passwordAccount, passwordToken, False, True)
    assert passwd.password != None

    #
    # test length of crypt is as expected
    #
    assert len(passwd.password) == MD5_PASSWORD_LENGTH

    #
    # duplicate first two tests with rootpassword class and CRYPT 
    # and MD5 password types
    #
    cryptedPassword = cryptPassword(passwordToken, False)
    passwd = RootPassword(cryptedPassword, True, False)
    assert passwd.password == cryptedPassword
    assert len(passwd.password) == CRYPT_PASSWORD_LENGTH

    md5Password = cryptPassword(passwordToken, True)
    passwd = RootPassword(md5Password, True, True)
    assert passwd.password == md5Password
    assert len(passwd.password) == MD5_PASSWORD_LENGTH


def test_CryptPassword():

    #
    # test crypt password does something
    #
    passwd = 'password'
    crypted = cryptPassword(passwd, useMD5=False)
    assert crypted

    crypted = cryptPassword(passwd, useMD5=True)
    assert crypted


def test_passwdFile():
    def cmpPasswd(path, expected):
        actual = PasswdFile.fromFile(os.path.join(TEST_DIR, "upgrade", path))
        assert actual.elements == expected

    cases = [
        ("passwd.0", [
        ['root', 'x', '0', '0', 'root', '/root', '/bin/bash'],
        ['bin', 'x', '1', '1', 'bin', '/bin', '/sbin/nologin'],
        ])
        ]

    for path, expected in cases:
        yield cmpPasswd, path, expected

def test_migratePasswdFile():
    def setup0():
        os.makedirs("/mnt/sysimage/esx3-installation/home/joe")
        
    def sideEffects0():
        assert "/mnt/sysimage/home/joe" in fauxroot.WRITTEN_FILES

        actual = fauxroot.WRITTEN_FILES[
            "/mnt/sysimage/home/joe/esx3-home"].getvalue()
        assert actual == "/esx3-installation/home/joe"
    
    cases = [
        ("passwd.old.0", "passwd.new.0", "passwd.mig.0", sideEffects0, setup0),
        ]

    for oldPath, newPath, expectedPath, sideEffects, setup in cases:
        yield (cmpMigratedFiles,
               hostActionMigratePasswdFile, "etc/passwd",
               oldPath, newPath, expectedPath, sideEffects, setup)

def test_migrateGroupFile():
    cases = [
        ("group.old.0", "group.new.0", "group.mig.0"),
        ]

    for oldPath, newPath, expectedPath in cases:
        yield (cmpMigratedFiles,
               hostActionMigrateGroupFile, "etc/group",
               oldPath, newPath, expectedPath)

def test_addingAdditionalUsers():
    fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]
    authXMLFile = "/mnt/sysimage/etc/vmware/hostd/authorization.xml"
    expectedOutput = """<ConfigRoot>
  <ACEData id="11">
    <ACEDataEntity>ha-folder-root</ACEDataEntity>
    <ACEDataId>11</ACEDataId>
    <ACEDataIsGroup>false</ACEDataIsGroup>
    <ACEDataPropagate>true</ACEDataPropagate>
    <ACEDataRoleId>-1</ACEDataRoleId>
    <ACEDataUser>dcui</ACEDataUser>
  </ACEData><ACEData id="12">
    <!-- generated by weasel/users.py -->
    <ACEDataEntity>ha-folder-root</ACEDataEntity>
    <ACEDataId>12</ACEDataId>
    <ACEDataIsGroup>false</ACEDataIsGroup>
    <ACEDataPropagate>true</ACEDataPropagate>
    <ACEDataRoleId>-1</ACEDataRoleId>
    <ACEDataUser>root</ACEDataUser>
  </ACEData>
  <ACEData id="13">
    <!-- generated by weasel/users.py -->
    <ACEDataEntity>ha-folder-root</ACEDataEntity>
    <ACEDataId>13</ACEDataId>
    <ACEDataIsGroup>false</ACEDataIsGroup>
    <ACEDataPropagate>true</ACEDataPropagate>
    <ACEDataRoleId>-1</ACEDataRoleId>
    <ACEDataUser>foobar</ACEDataUser>
  </ACEData>
  <ACEData id="14">
    <!-- generated by weasel/users.py -->
    <ACEDataEntity>ha-folder-root</ACEDataEntity>
    <ACEDataId>14</ACEDataId>
    <ACEDataIsGroup>false</ACEDataIsGroup>
    <ACEDataPropagate>true</ACEDataPropagate>
    <ACEDataRoleId>-1</ACEDataRoleId>
    <ACEDataUser>bazbar</ACEDataUser>
  </ACEData>
  <NextAceId>15</NextAceId>
</ConfigRoot>"""

    try:
        users = ["foobar", "bazbar"]
        for user in users:
            userchoices.addUser(user, "password", "md5")

        Accounts(userchoices.getUsers()).write()
    finally:
        fauxroot.FAUXROOT = None

    assert authXMLFile in fauxroot.WRITTEN_FILES

    actual = fauxroot.WRITTEN_FILES[authXMLFile].getvalue()

    print "Expected: ==============="
    print expectedOutput
    print "Got: ===================="
    print actual
    print "========================="

    assert expectedOutput == actual


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

			
