# Building Debian Packages

This document explains how to build Debian packages for apt-mirror.

## Prerequisites

### Build Dependencies

Install the required build dependencies:

```bash
sudo apt-get update
sudo apt-get install build-essential devscripts debhelper python3 python3-aiohttp xdelta3
```

Or use the Makefile to check:

```bash
make check-deps
```

### Runtime Dependencies

The package requires these runtime dependencies (automatically installed when installing the .deb):

- `python3` - Python 3 interpreter
- `python3-aiohttp` - Async HTTP client library
- `xdelta3` - Binary diff tool for diff serving feature

**Note**: `python3-aiohttp` is available in:
- Debian Testing (Bookworm+) and Unstable
- Ubuntu 24.04 (Noble) and later

For older Ubuntu versions, you may need to use backports.

## Building the Package

### Using Makefile

```bash
# Build source tarball and Debian package
make deb
```

This will:
1. Check that all dependencies are available
2. Create a source tarball
3. Build the Debian package using `dpkg-buildpackage`

### Manual Build

```bash
# Create source tarball
make dist

# Build Debian package
dpkg-buildpackage -us -uc -b
```

Options:
- `-us` - Don't sign the source package
- `-uc` - Don't sign the .changes file
- `-b` - Build binary package only

### Full Signed Build

For official releases:

```bash
dpkg-buildpackage
```

This will create signed packages (requires GPG setup).

## Package Structure

The Debian package includes:

- `/usr/bin/apt-mirror` - Main executable (Python script)
- `/etc/apt/mirror.list` - Default configuration file
- `/var/spool/apt-mirror/` - Base directory structure:
  - `mirror/` - Mirrored repository files
  - `skel/` - Temporary download location
  - `var/` - Logs and metadata
  - `diffs/` - Generated diffs (if enabled)

## Installing the Package

After building, install with:

```bash
sudo dpkg -i ../repo-mirror_0.6.3-1_all.deb
```

If there are missing dependencies:

```bash
sudo apt-get install -f
```

## Debian Package Files

The `debian/` directory contains:

- `control` - Package metadata and dependencies
- `rules` - Build instructions
- `changelog` - Package changelog
- `compat` - debhelper compatibility level
- `install` - Files to install

## Troubleshooting

### Missing python3-aiohttp

If `python3-aiohttp` is not available in your repository:

1. Check backports:
   ```bash
   sudo apt-get install -t <release>-backports python3-aiohttp
   ```

2. Or build from source (not recommended for packages)

### Build Errors

If you encounter build errors:

1. Clean previous builds:
   ```bash
   make clean
   fakeroot debian/rules clean
   ```

2. Check dependencies:
   ```bash
   make check-deps
   ```

3. Review build logs in `debian/` directory

## Testing the Package

After building, test installation:

```bash
# Install
sudo dpkg -i ../repo-mirror_0.6.3-1_all.deb

# Verify installation
which apt-mirror
apt-mirror --help

# Test dependencies
python3 -c "import aiohttp; print('OK')"
which xdelta3
```

## Uninstalling the Package

To remove the package:

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

**Note**: The systemd timer and service are automatically stopped and disabled during package removal by the `prerm` script.

## Uploading to Repository

For official Debian/Ubuntu repositories, follow the standard Debian packaging workflow:

1. Ensure all files are committed
2. Update `debian/changelog` with new version
3. Build signed packages: `dpkg-buildpackage`
4. Upload to Debian/Ubuntu repositories via standard process

