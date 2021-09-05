# apt-mirror

steamboatid's fork of apt-mirror

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

- Coded at debian buster 10.10
- Enough explanation at config file
- Merge almost all open PR from parent project
- Tons of new features added, including some workaround to support it


## Some new features added :
- new config option "use_proxy"  (PR #48)
- new config option "http_proxy"  (PR #48)
- new config option "proxy_user"  (PR #48)
- new config option "proxy_password"  (PR #48)
- new config option "user_agent"  (fixes #146)
- new config option "timeout"
	previously hard-coded, now the setup will affect on read, dns and connect timeout
- new config option "tries"
	previously hard-coded
- new config option "cookies_file"
	some server provide cookies, so we should provide cookies to legitimate cookie-full servers
- new config option "dry_run" (PR #86)
- new config option "max_redirect"
	reducing redirect attempt, to fasten Wget
- new config option "ip_v6"
	some network problematic with ipv6
- merge pull request (PR) #36, #40, #48, #77, #86, #95, #96, #100, #103, #105, #111, #112, #115, #116, #120, #127, #131, #136, #143
- bz2 or xz or gz (buster-backports i18n xz) (fixes #130)
- port number (fixes #19)
- checksum checking for binary & sources files. checksum checking can be executed at pre and post mirroring. both can be enabled/disabled via config file.
- using absolute full path for uncompress *.gz, *.xs and *.bz2
- Packages* files checksum checking
- ISO netinst mirroring
- Translation and DEP-11 files checksum checking. Unified downloads, so we can include these files at pre and post mirroring.
- minimum time to re-download missing file/URL (404 HTTP error)


## WORKAROUND :
- checksum checking ONLY on indexes files and "new/missing files"
- clear skel_path before mirroring
- add special aqrguments for "archive" stage and "index" stage


## TODO :
- clone any "distribution name" {buster, bullseye, xenial, etc} from uri
syntax example: deb http://adomain.com/folder any main contrib non-free
- clone any "components name" {main, contrib, non-free, ui} from specific "distribution name"
syntax example: deb http://adomain.com/folder bullseye any
- clone any "distribution name" AND "components name" from uri
syntax example: deb http://adomain.com/folder any any
- clone any "architecture" {including source} AND "distribution name" AND "components name" from uri
syntax example: deb-any http://adomain.com/folder any any
- any idea? please sumbit issue. thanks.


## DROPPED TODO LIST :
- Concurrent checksum checks
Workaround: checksum checking ONLY on indexes files and "new/missing files"
- Release files checksum checking.
Workaround: clear skel_path before mirroring
- Caching download feature. only re-download stale/expire or corruted uri
Workaround: add special aqrguments for "archive" stage and "index" stage


## List all of PR merged
- https://github.com/apt-mirror/apt-mirror/pull/36
- https://github.com/apt-mirror/apt-mirror/pull/40
- https://github.com/apt-mirror/apt-mirror/pull/48
- https://github.com/apt-mirror/apt-mirror/pull/77
- https://github.com/apt-mirror/apt-mirror/pull/86
- https://github.com/apt-mirror/apt-mirror/pull/95
- https://github.com/apt-mirror/apt-mirror/pull/96
- https://github.com/apt-mirror/apt-mirror/pull/100
- https://github.com/apt-mirror/apt-mirror/pull/103
- https://github.com/apt-mirror/apt-mirror/pull/105
- https://github.com/apt-mirror/apt-mirror/pull/111
- https://github.com/apt-mirror/apt-mirror/pull/112
- https://github.com/apt-mirror/apt-mirror/pull/115
- https://github.com/apt-mirror/apt-mirror/pull/116
- https://github.com/apt-mirror/apt-mirror/pull/120
- https://github.com/apt-mirror/apt-mirror/pull/127
- https://github.com/apt-mirror/apt-mirror/pull/131
- https://github.com/apt-mirror/apt-mirror/pull/136
- https://github.com/apt-mirror/apt-mirror/pull/143
