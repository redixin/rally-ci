How to run third party CI on single node
########################################

Prerequesites
*************
You need at least one node with any modern GNU/Linux distribution with zfs
and virsh installed. All shell commands listed below are working for Ubuntu.

SSH key
*******
Third party CI can be tested using you main gerrit account. There is a project
openstack-dev/ci-sandbox for this purpose. Any active gerrit account can
upload patches, approve, vote and so on. You may want to generate separate ssh
key for rally-ci::

    ssh-keygen -N '' -f ci-key -t rsa
    cat ci-key.pub

You need to paste this public key in gerrit settings page (add key in
https://review.openstack.org/#/settings/ssh-keys )

NOTE: Keep private key (ci-key) in safe. Do not publish this file. This file
should not be readable by users other then system users used to run rally-ci.
Do not forget to delete this key from gerrit settings when it is not aneeded
anymore.

The worker
**********

Virsh
=====

Installing virsh on ubuntu is as simple as::

    sudo apt-get install python-software-properties libvirt-bin
    sudo virsh net-start default

ZFS
===

First install zfs::

    sudo add-apt-repository --yes ppa:zfs-native/stable
    sudo apt-get update
    sudo apt-get install ubuntu-zfs

More about zfs on linux: http://zfsonlinux.org/

After you have virsh and zfs installed, you need to create zfs pool.

It is recommended to use separate disk, or at least disk partition or lvm volume. It is possible to
use sparse file if you don't have any better option::

    # create sparse file
    sudo truncate /store/zfs-ci --size 64G
    # craate pesudo block device
    sudo modprobe loop
    sudo losetup /dev/loop0 /store/zfs-ci
    # create zfs pool
    sudo zpool create ci /dev/loop0
    # create dataset for images
    sudo zfs create ci/images

Obtain base ubuntu image
========================

Image should be in format qcow2 and contain your public ssh key (ci-key.pub) in
/root/.ssh/authorized_keys. You may install ubuntu manually using virt-manager,
or using virsh-install or any other way.

The easiest way to get qcow image with ubuntu is ubuntu-vm-builder::

    sudo apt-get install ubuntu-vm-builder
    sudo ubuntu-vm-builder kvm trusty \
     --destdir new-img \
     --rootsize 16000 \
     --domain example.net \
     --user username --name user --pass r00tme \
     --ssh-key ci-key.pub \
     --addpkg acpid --addpkg openssh-server --addpkg linux-image-generic \
     --mirror http://cz.archive.ubuntu.com/ubuntu/ --components main,universe,restricted \
     --arch amd64 --hostname bare-ubuntu-1404 \
     --libvirt qemu:///system --bridge virbr0 \
     --mem 512 --cpus 1

Create new dataset and copy image::

    sudo zfs create ci/images/bare-ubuntu-1404
    sudo cp new-img/*.qcow2 /ci/images/bare-ubuntu-1404/vda.qcow2
    sudo zfs snapshot ci/images/bare-ubuntu-1404@1

Now we have snapshot ci/images/bare-ubuntu-1404@1 which will be source for new images.

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

Copy and edit sample configuration::

    cp rci/etc/rally-ci/noop.yaml rally-conf.yaml
    vim rally-conf.yaml

At this point you only need to change username and path to private key. Use your gerrit
username (username at https://review.openstack.org/#/settings/ )

Save file and run rally-ci::

    rci/bin/rally-ci rally-conf.yaml

Now you can go in https://review.openstack.org/#/q/status:open+project:openstack-dev/ci-sandbox,n,z
and write a comment `my-ci recheck` for any patchset. Wait few seconds and reload the page.
You should see a commend from Rally-CI.

Configure access to host machine
================================

Open rally-conf.yaml again, and edit nodepool. There is one node in nodes list
in sample configuration. Edit hostname and path to private key. If you running
rally-ci on the worker node, you only need to change path to private key.
Obviously you should be able to ssh to localhost with this private key.
If you want to use ci-key for this, you may do the following::

    sudo cat ci-key.pub >> /root/.ssh/authorized_keys

NOTE: root ssh access is usually disabled by default. To enable it, please edit
/etc/ssh/sshd_config and insert (or uncomment) line `PermitRootLogin without-password`. 

Restart sshd, and you will be able to login as root::

    sudo service ssh restart
    ssh root@localhost -i ci-key

Add new job
===========

Add one more runner
-------------------

First of all we need some bash scripts to prepare and run tests::

    TBD

Open rally-conf.yaml and add virsh runner::

    - runner:
        name: virsh
        name: my-virsh-runner
        module: rallyci.runners.virsh
        nodepool: test
        images:
          u1404-base:
            dataset: tank/rci
            source: bare_u1404@2
            build-scripts: ["prepare_node", "clone_projects"]
            build-net: "virbr0"
        vms:
          u1404-base:
            image: u1404-base
            net:
              bridge: "virbr0"


Here we got one VM defined with ubuntu image and 2048M of RAM.

Add script
----------

This script shoud check out project source
