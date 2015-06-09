How to run third party CI on single node
########################################

Prerequesites
*************

Worker node(s)
==============

* virsh
* zfs

Master node
===========

* virtualenv

Preparing worker node
*********************

Setting up ubuntu is as simple as::

    apt-get install python-software-properties libvirt-bin
    add-apt-repository --yes ppa:zfs-native/stable
    apt-get update
    apt-get install ubuntu-zfs


After you have virsh and zfs installed, you need to create zfs pool.

It is recommended to use separate disk, or at least disk partition or lvm volume. It is possible to
use sparse file if you don't have any better option::

    # create sparse file
    truncate /store/zfs-ci --size 64G
    # craate pesudo block device
    modprobe loop
    losetup /dev/loop0 /store/zfs-ci
    # create zfs pool
    zpool create ci /dev/loop0
    # create dataset for images
    zfs create ci/images


Preparing master node
*********************

