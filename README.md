apt-mirror
==========
For the original apt-mirror please see: http://apt-mirror.github.com

Our apt-mirror variant
=================
This variant of the apt-mirror, allows for setting a size limit for a package to be downloaded.
It also allows setting up exclusion rules for packages based on the section they belong to or their name patterns.
At the moment the script only allows configuration via changing the script itself, we hope to change to using the configuration file for this purpose.

The origin of the idea came from the blog page of Tyler Oderkirk
http://unsyncopated.com/blog/index.php/2009/11/04/creating-a-local-mirror-of-ubuntus-most-popular-packages/

The intent of this package is to create a subset of distribution for a community such as a school, college, hostel etc where people require a known subset of the packages based on either their language or some other package preferences, and to allow evolving it over a period of time.

Some important notes
====================
While mirroring if one needs to skip a certain set of packages, this
can be configured in the config file, by using skip and exception configuration.
A skip configuration line look like

    skip <criteria> {except <criteria>} reason <some text explaining the intent of this skip for logging>

An exception configuration line look like

    exception <criteria> reason <some text explaining the intent of this exception for logging>

The following criteria are valid:
    * size_more_than <size in bytes> e.g. size_more_than 10000000 : This means size more than 10M
    * section <section name such as Games or Accessories> e.g. section Games
    * if_name_contains <any text> e.g. if_name_contains cloud : Match packages with the text cloud in their names (case sensitive)
    * if_name_ends_with <any text> e.g. if_name_ends_with locale-en : Match packages with the text locale-en at the end of their names (case sensitive) e.g. firefox-locale-en

If spaces are given as input text then the text must be quoted using "(double quotes).
e.g. exception if_name_contains git reason "because we like git"

The reason is mandatory. The reason gets logged when a rule matches the given skip or exception criteria.
e.g.
        * Download exception granted for git because we like git
        * Skipping clamav-dbg because it is more than 10MB

The skip configuration can be used to skip packages based on any of the criteria definitions.
Multiple such configurations can be specified on separate lines.
To handle cases where the skip configuration matches a desired package or packages the except clause
may be used with similar criteria as a part of the skip config line itself.
If more than one rules cause a package to be skipped, the exception config line must be used.
e.g. One might like sudoku package in games section. So the skip config might say that we do not
wish to download any games and another config line might say skip any packages larger than 10MB.
To prevent adding an except config to each of these skip config one can add a single exception config line.
This will also safeguard it against future additions of skip config lines which could potentially cause
a desirable package to be excluded.

The files {base_path}/var/SKIP and {base_path}/var/EXCEPTION contain the results of the skip and exception config rules.
Using these the user can get to know why a certain package was skipped or downloaded.

How to configure?
=================
Please see the file AdvancedMirrorConfig.list for a sample config file. This file is in use for us. You can get a fair idea from this file. The intent of the file is to maintain packages for two distributions Ubuntu 12.04 and Ubuntu 14.04. We also like to switch between versions so the clean script is turned off. The script currently eliminates 139Gb+ worth of downloads for us which it would otherwise do because of our preferences. 

Example 1:
skip size_more_than 10000000 reason "because it is more than 10MB"

Meaning: Skip any file with size more than 10MB and when logging to the SKIP file in log directory output something like "Skipping kde-workspace-data-extras because it is more than 10MB". This is a general rule we came up with to prevent downloading of excessively large packages. Our idea was to download large packages only when specifically requested for. See how the reason text is quoted this is done because we used multiple words with spaces. It is also important to us that this entire config occur on a single line so line breaks are not allowed.

Example 2:
skip section games reason "because it is a game package"

Meaning: Skip any file which blongs to a section game and when logging to the SKIP file in log directory output something like "Skipping gnome-sudoku because it is a game package". This is a general rule we came up with to prevent downloading of any game packages.

Example 3:
skip if_name_contains dbg reason "because it is a debug package"

Meaning: Skip any file whose package name contains the phrase dbg and when logging to SKIP file in log directory output something like "Skipping cups-dbg because it is a debug package". This is a rule we came up with to avoid downloading debug packages. These packages are supposed to contain debugging symbols for debugging said packages. In general we did not want to debug any ubuntu package itself, we wanted to be able to switch between different library and application versions but we are not interested at the moment in debugging any.

Example 4:
skip if_name_contains locale except if_name_contains locale-en except if_name_ends_with locale reason "because it is a non english locale package"

Meaning: Here we wanted to skip locale packages since at our workplace we are usually only interested in english packages which are generally default. Also to cater for any exceptions to our understanding of the locale packaging, we choose to download the locale package if the name contains the text "locale-en" or if the name is simply "locale" to get the locale packages for english. In the log files we see log lines such as "Skipping firefox-locale-af because it is a non english locale package".

Example 5:
exception if_name_contains git reason "because we like git"

Meaning: This relates to the other half of the skip configuration where we would like to download a package despite of the exception rules. We do this via exception and this example tells us to download a package if the name contains git. We noticed in our runs because of our size rule of 10MB git was getting excluded, but we here are fond of git and are frequently switching to newer versions to try them out. This exception rule will get all git packages for us. Correspondingly in the EXCEPTION log file we see "Download exception granted for git because we like git".

Why would you need a distribution of your own?
=====================================
To save on internet bandwidth by avoiding downloading the same content over and over again for each device/pc/os instance. This especially helps if one is interested in switiching between versions of packages frequently.

Got suggestions/tips for a perl noob
============================
All the help and suggestions are most welcome.
