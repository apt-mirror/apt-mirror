# Debian/Ubuntu Package Dependencies

This document lists all required packages that must be installed via `apt-get` for apt-mirror.py to function.

## Required Packages

Install with:
```bash
sudo apt-get update
sudo apt-get install python3 python3-aiohttp xdelta3
```

### Core Dependencies

1. **python3** - Python 3 interpreter (standard on Debian/Ubuntu)
   - Provides: asyncio, hashlib, json, gzip, bz2, lzma, and all standard library modules

2. **python3-aiohttp** - Async HTTP client/server framework
   - Available in Debian (testing/unstable) and Ubuntu 24.04+
   - For older Ubuntu versions, may need to use backports or alternative approach

3. **xdelta3** - Binary diff tool for generating file differences
   - Used for the diff serving feature
   - Alternative: bsdiff (python3-bsdiff) or rsync

### Optional Dependencies

- **wget** or **curl** - For fallback download methods (usually already installed)
- **bsdiff** - Alternative diff algorithm (available as `bsdiff` package)
- **rsync** - Alternative diff/sync method (usually already installed)

## Installation Verification

After installation, verify dependencies:

```bash
python3 -c "import aiohttp; print('aiohttp OK')"
which xdelta3
```

## Compatibility

- **Debian**: Testing (Bookworm+) and Unstable (Sid) have python3-aiohttp
- **Ubuntu**: 24.04 (Noble) and later have python3-aiohttp
- **Older Ubuntu**: May need to use backports or compile from source

## Alternative for Older Systems

If python3-aiohttp is not available, the script can be modified to use:
- `urllib` with `asyncio` (standard library, but less efficient)
- `subprocess` with `curl` or `wget` in async mode

