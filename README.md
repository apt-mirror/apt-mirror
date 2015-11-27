apt-mirror
==========

See: http://apt-mirror.github.com for general usage

This repository is a fork of the original, intended to allow compatibilty for NetBSD. Mostly borne out of me
converting one my servers from a Debian/Ubuntu distro to BSD and finding that was no plug-and play apt-mirror
replacement. 

Fixes include:
- NetBSD style `install` invocation in Makefile
- Updated filepaths for interpreter and configs
- Envirnoment-independent; falls back on `uname -m` when dpkg not available to get arch

