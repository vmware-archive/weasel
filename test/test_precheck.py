
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
import stat

from StringIO import StringIO

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.append(os.path.join(TEST_DIR, "faux"))
import fauxroot

DEFAULT_CONFIG_NAME = "good-config.1"
sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

import precheck

def test_parseCpuInfo():
    def cmpFileDict(filename, expected):
        contents = open(os.path.join(TEST_DIR, "upgrade", filename)).read()
        got = precheck._parseCpuInfo(contents)
        assert got == expected
    
    cases = [
        ("precheck-cpuinfo.0", {
        'flags' : ['fpu', 'vme', 'de', 'pse', 'tsc', 'msr', 'pae', 'mce', 'cx8', 'apic', 'sep', 'mtrr', 'pge', 'mca', 'cmov', 'pat', 'pse36', 'clflush', 'dts', 'acpi', 'mmx', 'fxsr', 'sse', 'sse2', 'ss', 'ht', 'tm', 'syscall', 'nx', 'lm', 'constant_tsc', 'pni', 'monitor', 'ds_cpl', 'vmx', 'est', 'tm2', 'ssse3', 'cx16', 'xtpr', 'lahf_lm'] }),
        ("precheck-cpuinfo.1", {'flags' : [] })
        ]

    for filename, expected in cases:
        yield cmpFileDict, filename, expected

def test_checkCpu():
    goodCpuInfo = { 'flags' : ['lm'] }
    res = precheck.checkCpu(goodCpuInfo)
    assert res.name == "SUPPORTED_CPU"
    assert res.expected == [True]
    assert res.found == [True]
    assert res.code == precheck.Result.SUCCESS

    badCpuInfo = { 'flags' : [] }
    res = precheck.checkCpu(badCpuInfo)
    assert res.name == "SUPPORTED_CPU"
    assert res.expected == [True]
    assert res.found == [False]
    assert res.code == precheck.Result.ERROR

def test_resultsToXML():
    def cmpResultXML(results, filename):
        got = precheck.resultsToXML(results)
        expected = open(os.path.join(TEST_DIR, "upgrade", filename)).read()
        expected = expected.replace('\t', ' ' * 8)
        assert got == expected

    cases = [
        ([precheck.Result("TEST_CASE", ["Debra"], ["Dexter"])], "results.0.xml")
        ]

    for results, filename in cases:
        yield cmpResultXML, results, filename

def _captureMain():
    newStdout = StringIO()
    oldStdout = sys.stdout
    try:
        fauxroot.WRITTEN_FILES["/"] = fauxroot.CopyOnWriteFile(
            fmode=stat.S_IFDIR)
        fauxroot.WRITTEN_FILES["/boot"] = fauxroot.CopyOnWriteFile(
            fmode=stat.S_IFDIR)
        
        fauxroot.FAUXROOT = [DEFAULT_CONFIG_NAME]
        sys.stdout = newStdout
        precheck.main([])
    finally:
        sys.stdout = oldStdout
        fauxroot.FAUXROOT = []

    return newStdout.getvalue()

def test_noEsxConf():
    fauxroot.resetLogs()
    reload(fauxconfig)
    expected = open(os.path.join(
            TEST_DIR, "upgrade", "precheck-noesxconf.xml")).read()

    inventoryContent = open(
        os.path.join(TEST_DIR, "upgrade", "vmInventory.xml")).read()
    fauxroot.WRITTEN_FILES["/etc/vmware/hostd/vmInventory.xml"] = \
        fauxroot.CopyOnWriteFile(inventoryContent)
    
    got = _captureMain()
    print got
    assert got == expected

def test_hasEsxConf():
    fauxroot.resetLogs()
    reload(fauxconfig)
    fauxroot.WRITTEN_FILES["/etc/vmware/esx.conf"] = fauxroot.CopyOnWriteFile(
        '/system/uuid = "473027ac-5705f21d-6d09-000c2918f3dd"\n')
    expected = open(os.path.join(
            TEST_DIR, "upgrade", "precheck-esxconf.xml")).read()

    got = _captureMain()
    print got
    
    assert got == expected

def test_notEnoughMemory():
    def usrSbinEsxcfgInfo(_argv):
        return ("    |---Physical Mem.............536870912\n"
                "    |---Service Console Mem (Cfg)....272\n", 0)

    fauxroot.resetLogs()
    reload(fauxconfig)
    fauxroot.WRITTEN_FILES["/etc/vmware/esx.conf"] = fauxroot.CopyOnWriteFile(
        '/system/uuid = "473027ac-5705f21d-6d09-000c2918f3dd"\n')
    expected = open(os.path.join(
            TEST_DIR, "upgrade", "precheck-mem.xml")).read()
    fauxroot.EXEC_FUNCTIONS['/usr/sbin/esxcfg-info'] = usrSbinEsxcfgInfo

    got = _captureMain()
    print got
    
    assert got == expected

def test_failures():
    lspciOutput = open(os.path.join(
            TEST_DIR, "upgrade", "lspci.unsupported")).read()
    def lspci(_argv):
        return (lspciOutput, 0)

    fauxroot.resetLogs()
    reload(fauxconfig)
    fauxroot.WRITTEN_FILES["/etc/vmware/esx.conf"] = fauxroot.CopyOnWriteFile(
        '/system/uuid = "473027ac-5705f21d-6d09-000c2918f3dd"\n')
    fauxroot.EXEC_FUNCTIONS['/sbin/lspci'] = lspci

    inventoryContent = open(
        os.path.join(TEST_DIR, "upgrade", "vmInventory-old.xml")).read()
    fauxroot.WRITTEN_FILES["/etc/vmware/hostd/vmInventory.xml"] = \
        fauxroot.CopyOnWriteFile(inventoryContent)
    
    expected = open(os.path.join(
            TEST_DIR, "upgrade", "precheck-failures.xml")).read()

    try:
        got = _captureMain()
        print got
    finally:
        del fauxroot.EXEC_FUNCTIONS['/sbin/lspci']

    assert got == expected
