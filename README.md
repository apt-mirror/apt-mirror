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

Please be patient, I don't get a lot of foot traffic here, and might be a week before I see an issue or a PR. You are welcome to dm/ping me if you feel its urgent enough.
