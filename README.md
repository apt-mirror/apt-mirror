This is a fork of the original apt-mirror.
==========

The easiest way to get going with this version is to first install the original apt-mirror from the Ubuntu repo.

`sudo apt install apt-mirror`

Make a backup of the original file that was installed.

`sudo cp /usr/bin/apt-mirror /usr/bin/apt-mirror.original`

Next clone this repo somewhere on your local system, and then copy or symlink this version to the location /usr/bin/apt-mirror overwriting it.

Either way if you copy or symlink, change the permissions.

`sudo chown root:root /usr/bin/apt-mirror && sudo chmod 755 /usr/bin/apt-mirror`

---

This version now supports cnf (command-not-found) folder structures in the newer repos (such as eaon and focal). https://github.com/Stifler6996/apt-mirror/commit/c6a8a7eacf48f72453f1d5920a1514761679c952

This version adds support for files with the "@" character in filenames. https://github.com/Stifler6996/apt-mirror/commit/36255f35e9a8698c46ce20d06412e8bc16f821fc

This version adds support for xy compressed translation files. https://github.com/Stifler6996/apt-mirror/commit/692ba11aeec9953e9a4860b78098b2c783f80484

This version adds support for simple repositories that do not have "Distribution" or "Component" sections. https://github.com/Stifler6996/apt-mirror/commit/0611b5ab7d5b15cd9ab24b1dfdfb1a1125ecb6cd
