#!/bin/sh

BASE_PATH="/var/spool/apt-mirror"

echo "Installing apt-mirror command ...";
sudo cp apt-mirror /usr/local/bin/;
sudo chmod +x /usr/local/bin/apt-mirror;

echo "Installing apt-mirror configuration ...";
sudo mkdir -p /etc/apt/;
if [ -f /etc/apt/mirror.list ]; then
  sudo cp mirror.list /etc/apt/mirror.list.dpkg-dist
else
  sudo cp mirror.list /etc/apt/;
fi

echo "Installing apt-mirror manual ...";
sudo mkdir -p /usr/share/man/man1/
sudo pod2man apt-mirror > apt-mirror.1;
sudo mv apt-mirror.1 /usr/share/man/man1/;

echo "Creating base mirror structure ...";
sudo mkdir -p ${BASE_PATH}
sudo mkdir -p ${BASE_PATH}/mirror
sudo mkdir -p ${BASE_PATH}/skel
sudo mkdir -p ${BASE_PATH}/var

echo "Installing postmirror script example ...";
sudo cp postmirror.sh ${BASE_PATH}/var/

