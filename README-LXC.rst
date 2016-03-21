Worker
======

Install lxc::
    sudo apt-get update
    sudo apt-get install lxc

Install and configure btrfs::
    sudo apt-get install btrfs-tools
    sudo mkfs.btrfs /dev/vdb # Be careful!
    sudo sh -c 'echo "/dev/vdb /var/lib/lxc btrfs noatime 0 0" >> /etc/fstab'
    sudo mount /var/lib/lxc/
    df -h

Install rci::
    sudo apt-get install git python3-pip libffi-dev libssl-dev
    git clone git://github.com/redixin/rally-ci.git
    sudo pip3 install .
