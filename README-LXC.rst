RCI and LXC on single node mini howto
=====================================

Install lxc::

    sudo apt-get update
    sudo apt-get install lxc

Install and configure btrfs::

    sudo apt-get install btrfs-tools
    # assume we have /dev/vdb volume dedicated to btrfs filesystem
    sudo mkfs.btrfs /dev/vdb # Be careful!
    sudo sh -c 'echo "/dev/vdb /var/lib/lxc btrfs noatime 0 0" >> /etc/fstab'
    sudo mount /var/lib/lxc/
    df -h

Configure ssh::

    ssh-keygen # generate keypair
    cat ~/.ssh/id_rsa.pub # add this key into CI gerrit account
    sudo service ssh restart
    sudo mkdir /root/.ssh
    sudo sh -c 'cat /home/ubuntu/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys'

Install rci::

    sudo apt-get install git python3-pip libffi-dev libssl-dev
    git clone git://github.com/redixin/rally-ci.git
    sudo pip3 install .
