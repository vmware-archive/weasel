#! /bin/bash

# if you just run `nosetests` nakedly from this directory, some tests will 
# change the environment such that it interferes with other tests, and the 
# latter ones fail.  So run them in separate processes to isolate them from 
# each other.

# -----------------------------------------------------------------------------
# Exclude gui and remotefiles tests
CMD="nosetests -e test_gui -e test_remotefiles"
echo "Running $CMD ..."
$CMD
if [ $? == 0 ]
then
    echo 'success'
else
    echo 'failed.  exiting (All tests not run)...'
    exit
fi

# -----------------------------------------------------------------------------
# GUI test only
CMD="nosetests test_gui"
echo "Running $CMD ..."
$CMD
if [ $? == 0 ]
then
    echo 'success'
else
    echo 'failed.  exiting (All tests not run)...'
    exit
fi

# -----------------------------------------------------------------------------
# remotefiles test only
# (if run with the rest, it makes nosetests quit early for some reason)
CMD="nosetests test_remotefiles"
echo "Running $CMD ..."
$CMD
if [ $? == 0 ]
then
    echo 'success'
else
    echo 'failed.  exiting ...'
    exit
fi
