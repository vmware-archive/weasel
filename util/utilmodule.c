
/*****************************************************************************
 *
 * Copyright (c) 2008-2009 VMware, Inc.
 *
 * This file is part of Weasel.
 *
 * Weasel is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
 * version 2 for more details.
 *
 * You should have received a copy of the GNU General Public License along with
 * this program; if not, write to the Free Software Foundation, Inc., 51
 * Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 */

/* 
 * this _XOPEN_SOURCE undef is to make utilmodule build properly with 
 * scons. See Bug # ...
 */
#undef _XOPEN_SOURCE
#include <Python.h>
#include <ext2fs/ext2fs.h>
#include <linux/ext2_fs.h>
#include <uuid/uuid.h>
#include <stdio.h>
#include <unistd.h>


static PyObject * doGetDeviceUuid(PyObject * s, PyObject * args);
static PyObject * doSyncKernelBufferToDisk(PyObject * s, PyObject * args);

static PyMethodDef utilMethods[] = {
    { "getUuid", (PyCFunction) doGetDeviceUuid, METH_VARARGS,
        "Get uuid for a device" },
    { "syncKernelBufferToDisk", (PyCFunction) doSyncKernelBufferToDisk, METH_VARARGS,
        "Wraps the C sync() function.  sync() first commits inodes to buffers, and then buffers to disk." },
    {0,0,0,0} /* Sentinel */
};

void initlibutil(void) {
    PyObject * m, * d;

    m = Py_InitModule("libutil", utilMethods);
    d = PyModule_GetDict(m);

}

static PyObject * doGetDeviceUuid(PyObject * s, PyObject * args) {
    ext2_filsys fsys;
    int rc = 0;
    char * devstr;
    char error[80];
    char uuid[100];

    if (!PyArg_ParseTuple(args, "s", &devstr)) return NULL;

    rc = ext2fs_open(devstr, EXT2_FLAG_FORCE, 0, 0, unix_io_manager, &fsys);

    if (rc) {
        snprintf(error, sizeof error, "Couldn't open device: %s\n", devstr);
        PyErr_SetString(PyExc_IOError, error);
        return NULL;
    }

    memset(uuid, 0, sizeof(uuid));
    uuid_unparse(fsys->super->s_uuid, uuid);

    ext2fs_close(fsys);

    return Py_BuildValue("s", uuid);

}

static PyObject * doSyncKernelBufferToDisk(PyObject * s, PyObject * args) {
    sync();
    Py_RETURN_NONE;

}
