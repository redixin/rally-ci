How to run third party CI on a single node
##########################################

Prerequesites
*************
You need at least one node with any modern GNU/Linux distribution with zfs and
virsh installed. All shell commands listed below are known to work for Ubuntu.

SSH key
*******
Third party CI can be tested using you main gerrit account. There is a project
openstack-dev/ci-sandbox for testing purpose. Any active gerrit account can
upload patches, approve, vote and so on. You may want to generate separate ssh
key for this::

    ssh-keygen -N '' -f ~/.ssh/ci-key -t rsa
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

    sudo apt-get install libvirt-bin qemu-kvm zfs
    sudo virsh net-start default

ZFS Dataset
===========
Skip this step if you already have zfs.

It is recommended to use separate disk, or at least disk partition or lvm volume::

    zpool create tank /dev/some-dev
    zfs create tank/ci

RallyCI
*******

Access to worker node(s)
========================
Main node should have root access to worker node(s) by ssh key. Use ssh-copy-id
to copy your ssh key to worker node::

    ssh-copy-id root@host.example.com -i ~/.ssh/ci-key.pub

Installation
============
You need to install python >= 3.4 and virtualenv(optional)::

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

    rci/bin/rally-ci -v rally-conf.yaml

Now you can go in https://review.openstack.org/#/q/status:open+project:openstack-dev/ci-sandbox,n,z
and write a comment `my-ci recheck` for any patchset. Wait few seconds and reload the page.
You should see a comment from Rally-CI.


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
          backend: zfs
          dataset: tank/ci
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
