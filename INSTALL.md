# Installation and Usage

version 0.6.3

## Quick Start

### 1. Install Dependencies

```bash
sudo apt-get update
sudo apt-get install python3 python3-aiohttp xdelta3
```

**Note**: `python3-aiohttp` is available in:

- Debian Testing (Bookworm+) and Unstable
- Ubuntu 24.04 (Noble) and later

For older Ubuntu versions, you may need to use backports or compile from source.

### 2. Install apt-mirror.py

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

**Note**: apt-mirror also supports configuration files in `/etc/apt/mirror.list.d/*.list` directory (similar to APT's `sources.list.d/`). This allows you to organize repositories into separate files. All files are read and merged together.

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

# GPG signature verification (requires gpgv command)
# Verify GPG signatures of Release files for security
# set verify_gpg 1
# Optional: specify custom GPG keyring path (empty = use system default)
# set gpg_keyring /path/to/keyring.gpg

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

**Systemd service/timer is recommended** over cron for better monitoring, logging, and resource management. apt-mirror includes a lock file mechanism to prevent concurrent runs.

**Note**: If you installed via `.deb` package, the systemd service and timer files are already installed. Skip to "Enable and start" below.

#### Create apt-mirror user (manual installation only)

Create a dedicated system user for apt-mirror:

```bash
sudo adduser --system --group --home /var/spool/apt-mirror \
    --no-create-home --disabled-login apt-mirror

# Set ownership of mirror directories
sudo chown -R apt-mirror:apt-mirror /var/spool/apt-mirror
```

**Note**: If you installed via `.deb` package, the user is created automatically.

#### Create systemd service (manual installation only)

Create `/etc/systemd/system/apt-mirror.service`:

```ini
[Unit]
Description=APT Mirror Update
Documentation=man:apt-mirror(1)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/apt-mirror /etc/apt/mirror.list
User=apt-mirror
StandardOutput=journal
StandardError=journal

# Resource limits (adjust as needed)
CPUQuota=200%
MemoryMax=4G
IOWeight=100

# Nice priority (lower = higher priority, range -20 to 19)
Nice=10
```

#### Create systemd timer (manual installation only)

Create `/etc/systemd/system/apt-mirror.timer`:

```ini
[Unit]
Description=Run apt-mirror daily
Requires=apt-mirror.service

[Timer]
# Run daily at 2:00 AM
OnCalendar=*-*-* 02:00:00

# Run twice daily (2 AM and 2 PM) - uncomment to use:
# OnCalendar=*-*-* 02,14:00:00

# Run every 6 hours - uncomment to use:
# OnCalendar=*-*-* 00,06,12,18:00:00

# If the system was off during the scheduled time, run immediately after boot
Persistent=true

# Randomize start time by up to 30 minutes to avoid thundering herd
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

#### Enable and start

**If you installed via .deb package**: The systemd service and timer files are already installed. You just need to enable and start the timer:

```bash
# Enable the timer (starts automatically on boot)
sudo systemctl enable apt-mirror.timer

# Start the timer immediately
sudo systemctl start apt-mirror.timer
```

**If you installed manually**: Create the service and timer files as shown above, then:

```bash
# Reload systemd to recognize new units
sudo systemctl daemon-reload

# Enable the timer (starts automatically on boot)
sudo systemctl enable apt-mirror.timer

# Start the timer immediately
sudo systemctl start apt-mirror.timer
```

#### Check timer status

```bash
sudo systemctl status apt-mirror.timer
```

### 6. Uninstalling

To remove repo-mirror:

```bash
# Remove package (keeps config files)
sudo apt remove repo-mirror

# Or remove package and config files
sudo apt purge repo-mirror
```

**Important**: The following are NOT automatically removed and must be cleaned up manually if desired:

- **apt-mirror user**: The system user created during installation (if installed via `.deb` package)
- **Data directories**: `/var/spool/apt-mirror/` and all its contents (mirror data, logs, etc.)

To manually remove the user and data:

```bash
# Remove the apt-mirror user (optional - only if you want to completely remove everything)
sudo deluser --system apt-mirror

# Remove data directories (WARNING: This deletes all mirrored data!)
sudo rm -rf /var/spool/apt-mirror
```

**Note**: The systemd timer and service are automatically stopped and disabled during package removal by the `prerm` script.

# View when the next run is scheduled
sudo systemctl list-timers apt-mirror.timer

# View service logs
sudo journalctl -u apt-mirror.service -f

# Manually trigger a run (for testing)
sudo systemctl start apt-mirror.service
```

#### Benefits of systemd over cron

1. **Better logging**: Integrated with journald, easy to query and filter
2. **Status monitoring**: Check if service is running with `systemctl status`
3. **Resource limits**: Control CPU, memory, and IO usage
4. **Dependencies**: Wait for network to be online before starting
5. **Persistent timers**: Automatically catch up if system was off
6. **Randomized delays**: Avoid thundering herd on multiple mirrors
7. **Better error handling**: Can see exit codes and failure reasons

### Alternative: Cron (if systemd is not available)

If you prefer cron or are on a system without systemd:

Edit root's crontab:

```bash
sudo crontab -e
```

Add one of these entries:

```bash
# Run daily at 2:00 AM
0 2 * * * /usr/bin/apt-mirror /etc/apt/mirror.list >> /var/spool/apt-mirror/var/cron.log 2>&1

# Run twice daily (2 AM and 2 PM)
0 2,14 * * * /usr/bin/apt-mirror /etc/apt/mirror.list >> /var/spool/apt-mirror/var/cron.log 2>&1

# Run every 6 hours
0 */6 * * * /usr/bin/apt-mirror /etc/apt/mirror.list >> /var/spool/apt-mirror/var/cron.log 2>&1
```

**Note**: With cron, you'll need to manually check logs and cannot easily monitor status or set resource limits.

## New Configuration Options

Add these to your `mirror.list` for new features:

```bash
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
# Verify GPG signatures of Release files for security. Supports both InRelease
# (inline signed) and Release + Release.gpg (detached signature) formats.
# Uses the system's trusted GPG keyrings by default.
set verify_gpg 1
# Optional: specify global GPG keyring path (empty = use system default)
# Per-repository keyrings can be specified using [signed-by=/path/to/keyring.gpg] option
# Example: deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://archive.ubuntu.com/ubuntu noble main
# set gpg_keyring /path/to/keyring.gpg

# Proxy configuration (for authenticated proxies)
set use_proxy on
set http_proxy http://proxy.example.com:3128
set https_proxy http://proxy.example.com:3128
set proxy_user your_proxy_username
set proxy_password your_proxy_password

# Unlink option: For hardlinked directories support. When enabled, unlinks destination files before copying if they differ. This is necessary when using hardlinks - you cannot overwrite a hardlinked file directly, you must unlink it first. (Note: wget --unlink is no longer used since we use async downloads, but this option still applies to file copying operations)
set unlink 1

# Cleanup mode: Controls how old files are removed from the mirror
#   "off"  - No cleanup performed
#   "on"   - Generate clean.sh script for manual review (default, recommended)
#   "auto" - Automatically remove old files (DANGEROUS - use with extreme caution!)
#            WARNING: Automatic cleanup permanently deletes files and cannot be undone!
#   "both" - Generate clean.sh script AND perform automatic cleanup (useful for testing/debugging)
# set clean on
```

### Per-Repository GPG Keyrings

Each repository can have its own GPG keyring for signature verification. This is especially useful when mirroring multiple distributions (e.g., Ubuntu, Debian, Kali) that use different signing keys.

**Method 1: Using [signed-by=...] option (Recommended, APT-compatible)**

```bash
# Ubuntu repositories with Ubuntu keyring
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://archive.ubuntu.com/ubuntu noble main

# Debian repositories with Debian keyring
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian bookworm main

# Kali repositories with Kali keyring
deb [signed-by=/usr/share/keyrings/kali-archive-keyring.gpg] http://http.kali.org/kali kali-rolling main
```

**Method 2: Using mirror.list.d/ directory**

Organize repositories into separate files, each with their own keyring configuration:

```bash
# /etc/apt/mirror.list.d/ubuntu.list
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://archive.ubuntu.com/ubuntu noble main

# /etc/apt/mirror.list.d/debian.list
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian bookworm main

# /etc/apt/mirror.list.d/kali.list
deb [signed-by=/usr/share/keyrings/kali-archive-keyring.gpg] http://http.kali.org/kali kali-rolling main
```

**Getting GPG keyrings:**

Most distributions provide keyring packages:

```bash
# Ubuntu
sudo apt-get install ubuntu-keyring

# Debian
sudo apt-get install debian-archive-keyring

# Kali
wget -q -O - https://archive.kali.org/archive-key.asc | sudo gpg --dearmor -o /usr/share/keyrings/kali-archive-keyring.gpg
```

**Keyring locations:**

- Modern: `/usr/share/keyrings/*.gpg` (recommended)
- Legacy: `/etc/apt/trusted.gpg.d/*.gpg`
- System: `/etc/apt/trusted.gpg` (not recommended for per-repo use)

## Verification

Check that dependencies are installed:

```bash
python3 -c "import aiohttp; print('✓ aiohttp OK')"
which xdelta3 && echo "✓ xdelta3 OK"
```

## Web Server

apt-mirror is only half the equation. While apt-mirror creates the files framework for serving a mirror, you will still need a web server to serve the files.

We recommend either Nginx or Apache. There are a lot of elements you can configure for web servers, so here are some example configurations that might work for you.
These are only examples, you will need to sort out your own configuration if it is more complex.

### Nginx Configuration

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # Point the web root directly to the mirror directory
    root /var/spool/apt-mirror/mirror;

    location /ubuntu/ {
        autoindex on;
        alias /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/;
    }
}
```

### Apache2 Configuration

```apache
<VirtualHost *:80>
    ServerName _
    
    # Point the web root directly to the mirror directory
    DocumentRoot /var/spool/apt-mirror/mirror
    
    <Directory /var/spool/apt-mirror/mirror>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>
    
    # Alias for Ubuntu repository
    Alias /ubuntu /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu
    
    <Directory /var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>
</VirtualHost>
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

Make sure you run as a user with write access to the mirror directory. If installed via `.deb` package, the `apt-mirror` user is created automatically and owns `/var/spool/apt-mirror`:

```bash
# Run as root (if apt-mirror user doesn't exist)
sudo apt-mirror

# Or run as apt-mirror user (recommended if user exists)
sudo -u apt-mirror apt-mirror
```

Or configure proper permissions manually:

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

   ```bash
   set limit_rate 100m
   ```

## Compatibility

- **Backward compatible** with existing `mirror.list` files
- **Same directory structure** as Perl version
- **Drop-in replacement** - can replace Perl script directly
