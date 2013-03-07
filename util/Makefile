TOOLCHAIN_ROOT ?= /bldmnt/toolchain/lin32

CC = GCC_EXEC_PREFIX="$(TOOLCHAIN_ROOT)/gcc-3.3.3/lib/gcc-lib/" $(TOOLCHAIN_ROOT)/gcc-3.3.3/bin/i686-linux-gcc
CFLAGS = -g -Os -Wall -Werror -ffunction-sections

PYTHON_INCLUDES = -I$(TOOLCHAIN_ROOT)/python-2.4.3/include/python2.4

E2FSPROGS_INCLUDES = -I$(TOOLCHAIN_ROOT)/e2fsprogs-1.39/include/
E2FSPROGS_LIBS = -L$(TOOLCHAIN_ROOT)/e2fsprogs-1.39/lib/ -lext2fs -luuid

all: libutil.so

clean:
	-rm *.o *.lo *.so

utilmodule.lo: utilmodule.c
	$(CC) -c $(CFLAGS) -fPIC $(PYTHON_INCLUDES) $(E2FSPROGS_INCLUDES) $< -o $@

libutil.so: utilmodule.lo
	echo "*********************************"
	echo "\
	This Makefile here is only for testing purposes.  eg, getting \
	caged_weasel to run properly.  The .so file that actually makes \
	it into the build is built by scons. \
	See BORA/scons/modules/weasel_util.sc \
	"
	echo "*********************************"
	$(CC) -shared -fPIC $< -o $@ $(E2FSPROGS_LIBS)
