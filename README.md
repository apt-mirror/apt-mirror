apt-mirror
==========

A small and efficient tool that lets you mirror a part of or the whole Debian GNU/Linux distribution or any other apt sources.

**Version 0.6.3** - Now with async Python implementation!

See: https://apt-mirror.github.io/

## Features

- **Async downloads** using Python's asyncio and aiohttp for improved performance
- **GPG signature verification** - Optional verification of Release file signatures for security
- **Diff generation** - Generate binary diffs for custom use cases (note: standard APT does not support diffs)
- **Fully pool compliant** - Works with modern APT repository formats
- **Multithreaded downloading** - Configurable concurrency
- **Multiple architectures** - Support for all Debian/Ubuntu architectures
- **Automatic cleanup** - Remove unneeded files automatically
- **Backward compatible** - Works with existing mirror.list configuration files

## Quick Installation

### 1. Install Dependencies

```bash
sudo apt-get update
sudo apt-get install python3 python3-aiohttp xdelta3
```

**Note**: `python3-aiohttp` is available in:
- Debian Testing (Bookworm+) and Unstable
- Ubuntu 24.04 (Noble) and later

For older Ubuntu versions, you may need to use backports or compile from source.

### 2. Install apt-mirror

```bash
# Copy the script to a system location
sudo cp apt-mirror.py /usr/local/bin/apt-mirror
sudo chmod +x /usr/local/bin/apt-mirror
```

Or if replacing the Perl version:
```bash
sudo cp apt-mirror.py /usr/bin/apt-mirror
sudo chmod +x /usr/bin/apt-mirror
```

### 3. Configure

Edit `/etc/apt/mirror.list` (or your custom config file):

```bash
sudo nano /etc/apt/mirror.list
```

Example configuration:

```bash
set base_path         /var/spool/apt-mirror
set mirror_path       $base_path/mirror
set skel_path         $base_path/skel
set var_path          $base_path/var
set postmirror_script $var_path/postmirror.sh
set defaultarch       amd64
set run_postmirror    0
set nthreads          20
set limit_rate        100m
set _tilde            0
set unlink            1
set use_proxy         off
set http_proxy        127.0.0.1:3128
set proxy_user        user
set proxy_password    password
set enable_diffs      1
set diff_algorithm    xdelta3
set diff_storage_path $base_path/diffs
set max_diff_size_ratio 0.5
set retry_attempts    5
set retry_delay       2.0
set verify_checksums  1
set resume_partial_downloads 1

# Ubuntu 24.04 LTS (Noble Numbat) repositories
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-backports main restricted universe multiverse

# Source repositories (optional, uncomment if needed)
#deb-src http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
#deb-src http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
#deb-src http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse
#deb-src http://archive.ubuntu.com/ubuntu noble-backports main restricted universe multiverse

clean http://archive.ubuntu.com/ubuntu
```

### 4. Run

**Note**: If installed via `.deb` package, a dedicated `apt-mirror` system user is created automatically. The systemd service runs as this user for security. When running manually, you can run as root or the `apt-mirror` user (if it exists).

```bash
sudo apt-mirror /etc/apt/mirror.list
```

Or with the default config:
```bash
sudo apt-mirror
```

Or run as the apt-mirror user (if created):
```bash
sudo -u apt-mirror apt-mirror /etc/apt/mirror.list
```

### 5. Schedule with systemd (Recommended)

To keep your mirror up to date automatically, enable the systemd timer:

```bash
# If installed via .deb: service/timer files are already installed
# If installed manually: create service/timer files (see INSTALL.md)
sudo systemctl enable apt-mirror.timer
sudo systemctl start apt-mirror.timer
```

See [INSTALL.md](INSTALL.md) for detailed systemd service/timer setup and cron alternatives.

### 6. Uninstalling

To remove repo-mirror:

```bash
# Remove package (keeps config files)
sudo apt remove repo-mirror

# Or remove package and config files
sudo apt purge repo-mirror
```

**Important**: The following are NOT automatically removed and must be cleaned up manually if desired:

- **apt-mirror user**: The system user created during installation
- **Data directories**: `/var/spool/apt-mirror/` and all its contents (mirror data, logs, etc.)

To manually remove the user and data:

```bash
# Remove the apt-mirror user (optional - only if you want to completely remove everything)
sudo deluser --system apt-mirror

# Remove data directories (WARNING: This deletes all mirrored data!)
sudo rm -rf /var/spool/apt-mirror
```

## Configuration Files

apt-mirror supports multiple configuration files:

1. **Main config file**: `/etc/apt/mirror.list` (or custom path)
2. **Additional config files**: `/etc/apt/mirror.list.d/*.list` (sorted alphabetically)

This allows you to organize repositories into separate files (e.g., one file per distribution or vendor). All files are read and merged together.

## New Configuration Options

Add these to your `mirror.list` for new features:

```
# Enable diff generation (for custom tools only - standard APT does not use diffs)
# Note: Standard APT clients download complete .deb files. Diffs are only useful
# for custom tools that can download and apply diffs. See Debian SourcesList docs.
set enable_diffs 1

# Choose diff algorithm (xdelta3, bsdiff, or rsync)
set diff_algorithm xdelta3

# Where to store diffs
set diff_storage_path $base_path/diffs

# Only create diffs if they're smaller than 50% of original
set max_diff_size_ratio 0.5

# Retry configuration
set retry_attempts 5
set retry_delay 2.0

# Verify checksums after download
set verify_checksums 1

# Resume partial downloads
set resume_partial_downloads 1

# GPG signature verification (requires gpgv command)
# Verify GPG signatures of Release files for security
# set verify_gpg 1
# Optional: specify global GPG keyring path (empty = use system default)
# Per-repository keyrings can be specified using [signed-by=/path/to/keyring.gpg] option
# set gpg_keyring /path/to/keyring.gpg

# Cleanup mode: Controls how old files are removed from the mirror
#   "off"  - No cleanup performed
#   "on"   - Generate clean.sh script for manual review (default, recommended)
#   "auto" - Automatically remove old files (DANGEROUS - use with extreme caution!)
#            WARNING: Automatic cleanup permanently deletes files and cannot be undone!
#   "both" - Generate clean.sh script AND perform automatic cleanup (useful for testing/debugging)
# set clean on

# Proxy configuration (for authenticated proxies)
set use_proxy on
set http_proxy http://proxy.example.com:3128
set https_proxy http://proxy.example.com:3128
set proxy_user your_proxy_username
set proxy_password your_proxy_password

# Unlink option: For hardlinked directories support. When enabled, unlinks destination files before copying if they differ. This is necessary when using hardlinks - you cannot overwrite a hardlinked file directly, you must unlink it first. (Note: wget --unlink is no longer used since we use async downloads, but this option still applies to file copying operations)
set unlink 1
```

## Verification

Check that dependencies are installed:

```bash
python3 -c "import aiohttp; print('✓ aiohttp OK')"
which xdelta3 && echo "✓ xdelta3 OK"
```

## Troubleshooting

### python3-aiohttp not found

If `python3-aiohttp` is not available in your repository:

1. **Check if it's in backports:**
   ```bash
   sudo apt-get install -t <release>-backports python3-aiohttp
   ```

2. **For very old systems**, you can modify the script to use `urllib` instead (less efficient but works)

### Permission Errors

Make sure you run as a user with write access to the mirror directory:
```bash
sudo apt-mirror
```

Or configure proper permissions:
```bash
sudo chown -R apt-mirror:apt-mirror /var/spool/apt-mirror
```

## Performance Tips

1. **Adjust nthreads** based on your bandwidth and CPU:
   - For fast connections: 20-50 threads
   - For slower connections: 5-10 threads

2. **Enable diffs** (for custom tools only - standard APT does not use diffs):
   ```bash
   set enable_diffs 1
   ```

   **Note**: Standard APT clients download complete `.deb` files and do not support diffs. The diff feature is only useful for custom tools or scripts that can download and apply diffs. See [Debian SourcesList documentation](https://wiki.debian.org/SourcesList) for APT's standard behavior.

3. **Use limit_rate** to avoid saturating your connection:
   ```
   set limit_rate 100m
   ```

## Compatibility

- **Backward compatible** with existing `mirror.list` files
- **Same directory structure** as Perl version
- **Drop-in replacement** - can replace Perl script directly

## Documentation

- [INSTALL.md](INSTALL.md) - Detailed installation and usage guide
- [FEATURES.md](FEATURES.md) - Complete feature list and improvements
- [DEBIAN_DEPENDENCIES.md](DEBIAN_DEPENDENCIES.md) - Package dependency information
- [BUILD.md](BUILD.md) - Building Debian packages from source

## New maintainer(s) wanted
========================

We (the current maintainers) lack the time and energy to maintain apt-mirror:
Our last commit is years old and the number of pull request is rising. We
agreed on acknowledging this fact and are searching for new maintainers who
wants to join the GitHub apt-mirror group and continue maintaining this
repository and do new releases. If you are interested and have time and energy
to take the project over, please contact Brandon Holtsclaw to give you the
permission.

## License

See [LICENSE](LICENSE) file for details.

## Authors

- Dmitry N. Hramtsov <hdn@nsu.ru>
- Brandon Holtsclaw <me@brandonholtsclaw.com>
- Richard Dawson <dawsonra@clockworx.org>
