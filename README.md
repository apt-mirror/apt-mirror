# apt-mirror

Josh's fork of apt-mirror

For official source, see: http://apt-mirror.github.com

## Usage

Basic execution:

```
# To run with default paths and values (e.g /etc/apt/mirror.list)
./apt-mirror
# To run using ./mirror.list
./apt-mirror mirror.list
# Or:
perl ./apt-mirror mirror.list
```

apt-mirror can also be installed with

`make install`

See also:

`perldoc ./apt-mirror`

## Changes from apt-mirror/apt-mirror

- Updated for Ubuntu 19.04
  - Default mirror.list reflects new release
  - apt-mirror supports cnf directory with Commands index
- Set default architecture to amd64
- Expanded README.md
- Download 'debian-installer' directory
