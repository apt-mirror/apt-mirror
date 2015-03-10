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

P.S. I am currently new to perl so all help and suggestions are welcome.
