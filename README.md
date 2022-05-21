An actively maintained version of apt-mirror.
==========

Please check the wiki for examples, and feel free to add more if you wish. https://github.com/Stifler6996/apt-mirror/wiki
Also use the discussions section https://github.com/Stifler6996/apt-mirror/discussions if you have queries, dont post help requests to Issues.

---

The easiest way to get going with this version is to first install the original apt-mirror from the Debian or Ubuntu repo.

`sudo apt install apt-mirror`

Make a backup of the original file that was installed.

`sudo cp /usr/bin/apt-mirror /usr/bin/apt-mirror.original`

Next clone this repo somewhere on your local system, and then copy or symlink this version to the location /usr/bin/apt-mirror overwriting it.

Either way if you copy or symlink, change the permissions.

`sudo chown root:root /usr/bin/apt-mirror && sudo chmod 755 /usr/bin/apt-mirror`

---
