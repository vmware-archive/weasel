# VMware has ended active development of this project, this repository will no longer be updated.

Weasel for ESX
==============

Copyright (c) 2008-2010 VMware, Inc.

Weasel is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation version 2 and no later version.

Weasel is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
version 2 for more details.

You should have received a copy of the GNU General Public License along with
this program; if not, write to the Free Software Foundation, Inc., 51
Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.


ABOUT WEASEL

Weasel is a replacement for Red Hat Linux's Anaconda installer and is used
for installing ESX 4.  As such, it normally runs from a Red Hat Enterprise 3
"Console OS" running underneath VMware ESX Server.

Weasel is written almost entirely in Python, and supports a fairly robust
set of features including:

  - graphical installation
  - text based installation
  - scripted (kickstart) installation
  - multiple types of boot media including CD-ROM, DVD, USB, and PXE
  - network based installation through http, ftp and nfs
  - asynchronous storage and network driver disks
  - support for creating multiple filesystem types including ext3 and vmfs
  - installation of Red Hat Enterprise Linux into a special container called
    the "Console VMDK"
  - extensive unit tests which can be run to validate the installer code
  - dynamic partition checking to ensure that any set of partitions will
    be able to house the operating system at installation time.

The graphical installation front end uses the PyGTK library and each screen
was created with the glade tool.  


SUPPORT

For support for Weasel, please check with VMware's Community Forums at:

http://communities.vmware.com/community/vmtn/vsphere/upgradecenter



RUNNING WEASEL

Running Weasel is different than running other Linux-based operating system
installers.  Even though it was developed to run on top of the Linux based
Console OS and shares many concepts with installers such as Anaconda like RPM
based packaging, Weasel will not run directly on Linux.  There is no direct
module support for loading modules;  in the ESX installer this is taken care
of by initscripts which are executed before the installer is run and at
the module load stage.

It is however possible to test Weasel in Linux.  To start the graphical
installer from the weasel directory, invoke the command:

  $ python test/caged_weasel.py weasel.py --nox


