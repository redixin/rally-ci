How to run third party CI on a single node
##########################################

Prerequesites
*************
You need at least one node with any modern GNU/Linux distribution with btrfs or zfs
and virsh installed. All shell commands listed below are known to work for Ubuntu.

SSH key
*******
Third party CI can be tested using you main gerrit account. There is a project
openstack-dev/ci-sandbox for testing purpose. Any active gerrit account can
upload patches, approve, vote and so on. You may want to generate separate ssh
key for this::

    ssh-keygen -N '' -f ci-key -t rsa
    cat ci-key.pub

You need to paste this public key in gerrit settings page (add key in
https://review.openstack.org/#/settings/ssh-keys )

NOTE: Keep private key (ci-key) in safe. Do not publish this file.
Do not forget to delete this key from gerrit settings when it is not used 
anymore.

The worker
**********

Install prerequisites
=====================
Installing virsh and btrfs on ubuntu is as simple as::

    sudo apt-get install libvirt-bin qemu-kvm btrfs-tools
    sudo virsh net-start default

BTRFS parttition
================
Skip this step if you already have btfs.

It is recommended to use separate disk, or at least disk partition or lvm volume. It is also possible to
use sparse file if you don't have any better option::

    # create sparse file
    sudo truncate /store/btrfs-file --size 64G
    # craate pesudo block device
    sudo modprobe loop
    sudo losetup /dev/loop0 /store/btrfs-file
    # create btrfs filesystem
    sudo mkfs.btrfs /dev/loop0
    # mount filesystem
    sudo mount /dev/loop0 /ci

Create subvolume for Rally-CI
=============================

    sudo btrfs subvolume create /ci/rally

RallyCI
*******

Access to worker node(s)
========================
Main node should have root access to worker node(s) by ssh key. Use ssh-copy-id
to copy your ssh key to worker node::

    ssh-copy-id root@host.example.com

Installation
============
You need to install python >= 3.4 and virtualenv::

    sudo apt-get -y install python3-virtualenv

Create virtual env and install rally-ci in it::

    virtualenv -p /usr/bin/python3 rci
    rci/bin/pip3 install rally-ci

Configure HTTP Server
=====================
Separate http server is needed to serve log files and proxy metadata requests.

Setup nginx::

    sudo apt-get install nginx
    sudo cp rci/etc/rally-ci/nginx.conf /etc/nginx/sites-enabled/ci.conf
    # Edit nginx configuration file. You may want to change only path to logs
    sudo vim /etc/nginx/sites-enabled/ci.conf
    sudo service nginx reload

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
You should see a comment from Rally-CI.

Configure access to host machine
================================
Open rally-conf.yaml again, and edit provider. There is one node in nodes list
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

Sample full configuration
=========================
Full example may be found in etc/sample-multinode-dsvm.yaml

Thit sample job deploys devstack on two VMs, boot a VM inside this
cloud, and tests live migration by running corresponding rally
scenario.

This sample is mostly self documented, but some sections needs further
description::

    - provider:
        name: virsh
        module: rallyci.runners.virsh
        hosts:
          - hostname: localhost
            key: /home/user/.ssh/ci-key
        storage:
          backend: btrfs
          path: /ci/rally
        metadata_server:
          listen_addr: 127.0.0.1
          listen_port: 8080
          authorized_keys: /etc/rally-ci/authorized_keys
          user_data: |
            #cloud-config
            manage_etc_hosts: true
            bootcmd:
              - echo 'root:r00tme' | chpasswd
            disable_root: 0
            ssh_pwauth: True
        images:
          u1404:
            url: https://cloud-images.ubuntu.com/trusty/current/trusty-server-cloudimg-amd64-disk1.img
          dsvm:
            parent: u1404
            build-scripts: ["init_dsvm", "clone_projects"]
        vms:
          dsvm:
            memory: 3000
            image: dsvm
            net:
              - bridge: virbr0

Images section
^^^^^^^^^^^^^^
In this section images are defined. Here we define base image "u1404", which
will be downloaded from cloud-images.ubuntu.com. Second image "dsvm" will
be created based on u1404 by running two scripts "init_dsvm" and "clone_projects".

New image will be stored /ci/rally/dsvm. This image will be base for our test VMs.
Image may be deleted by hand at any moment, and rally-ci will rebuild it from scratch.

Vms section
^^^^^^^^^^^
In this section vms are defined. Here we make one VM called dsvm
based on image dsvm with 3G of RAM and attached to virbr0.

When running tests, base image will be cloned, and VM is started. When
tests finished, image clone will be destroyed.

Why BTRFS?
==========
The biggest problem in running many VMs on single host is disk performance.
When we create one parent image and make child images by cloning parent,
all VMs are using the same shared blocks from parent image, and only
changed blocks are copied (COW).
