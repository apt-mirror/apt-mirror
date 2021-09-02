#!/bin/sh -e

## Anything in this file gets run AFTER the mirror has been run.
## Put your custom post mirror operations in here (like rsyncing the installer
## files and running clean.sh automatically)!

## Example of grabbing the extra installer files from Ubuntu (Note: rsync needs
## to be installed and in the path for this example to work correctly)

#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/trusty/main/debian-installer /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/trusty/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/trusty/main/dist-upgrader-all/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/trusty/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/trusty/main/installer-amd64/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/trusty/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/trusty/main/installer-i386/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/trusty/main/
