How to run third party CI on single node
########################################

Prerequesites
*************

You need at least one node with any modern OS with zfs and virsh installed.
This may be any distribution of GNU/Linux, or even FreeBSD.

All shell commands listed below are working for Ubuntu.

RallyCI
*******

Installation
============

You need to install python >= 3.4 and virtualenv::

    sudo apt-get -y install python3-virtualenv

Create virtual env and install rally-ci in it::

    virtualenv -p /usr/bin/python3 rci
    rci/bin/pip3 install rally-ci

Test default configuration
==========================

Third party CI can be tested using you main gerrit account. There is a project
openstack-dev/ci-sandbox for this purpose. Any active gerrit account can
upload patches, approve, vote and so on. You may want to generate separate ssh
key for rally-ci::

    ssh-keygen -N '' -f ci-key -t rsa
    cat ci-key.pub

You should copy and pase this public key into your gerrit settings page.

NOTE: Keep ci-key in safe. Do not publish this file. This file should not be
readable by users other then users who used to run rally-ci. This public key
should be deleted from gerrit configuration after testing is finished.

WORK IN PROGRESS

Edit noop configuration::

    vim rci/etc/rally-ci/noop.yaml

Preparing worker node
*********************

Installing zfs and virsh on ubuntu is as simple as::

    sudo apt-get install python-software-properties libvirt-bin
    sudo add-apt-repository --yes ppa:zfs-native/stable
    sudo apt-get update
    sudo apt-get install ubuntu-zfs

More about zfs on linux: http://zfsonlinux.org/

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


