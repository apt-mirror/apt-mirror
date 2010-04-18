#!/bin/sh -e

## anything in this file gets run AFTER the mirror has been run
## put your custom post mirror operations in here ( like rsyncing the installer files and running clean.sh automaticly )

## Example of grabbing the extra translations and installer files from ubuntu ( note rsync needs to be installed 
## and in the path for this example to work correctly )

#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/lucid/main/debian-installer /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/lucid/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/lucid/main/dist-upgrader-all/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/lucid/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/lucid/main/i18n/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/lucid/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/lucid/main/installer-amd64/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/lucid/main/
#rsync --recursive --times --links --hard-links --delete --delete-after rsync://mirror.anl.gov/ubuntu/dists/lucid/main/installer-i386/ /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/lucid/main/
