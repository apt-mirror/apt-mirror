#!/usr/bin/env python3
"""
apt-mirror - async apt sources mirroring tool

A modern async implementation of apt-mirror with enhanced features:

* Async downloads using aiohttp
* Diff serving capability
* Better error handling and progress reporting
* Improved performance for large mirrors

Dependencies (all available in Debian/Ubuntu repos):

* python3 (standard library: asyncio, hashlib, json, gzip, bz2, lzma, etc.)
* python3-aiohttp (apt package)
* xdelta3 (apt package, for diff generation)

All imports are from standard library except aiohttp and xdelta3.
"""

import asyncio
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin
import json
import gzip
import bz2
import lzma
from dataclasses import dataclass, field
from enum import Enum

# Try to import aiohttp, but provide helpful error if not available
try:
    import aiohttp
except ImportError:
    print("Error: python3-aiohttp is required but not installed.")
    print("Please install it with: sudo apt-get install python3-aiohttp")
    sys.exit(1)

__version__ = "0.6.3"

class HashType(Enum):
    """Supported hash types in order of strength.
    
    Hash types are ordered from strongest to weakest for security
    and integrity verification purposes. Used when verifying file
    checksums and when downloading files via by-hash directories.
    """
    SHA512 = "SHA512"
    SHA256 = "SHA256"
    SHA1 = "SHA1"
    MD5Sum = "MD5Sum"


@dataclass
class Config:
    """Configuration settings for apt-mirror.
    
    All configuration values can be set in the mirror.list file using
    the ``set`` directive. Variable substitution is supported using
    ``$variable_name`` syntax. For example, ``$base_path`` will be
    replaced with the value of ``base_path``.
    
    :param base_path: Base directory for all mirror operations
    :type base_path: str
    :param mirror_path: Directory where mirrored files are stored
    :type mirror_path: str
    :param skel_path: Temporary directory for downloads
    :type skel_path: str
    :param var_path: Directory for logs and metadata
    :type var_path: str
    :param defaultarch: Default architecture (auto-detected if empty)
    :type defaultarch: str
    :param nthreads: Number of concurrent download threads
    :type nthreads: int
    :param limit_rate: Download rate limit (e.g., "100m" for 100MB/s)
    :type limit_rate: str
    :param enable_diffs: Enable diff generation for changed files
    :type enable_diffs: bool
    :param diff_algorithm: Algorithm to use for diffs (xdelta3, bsdiff, rsync)
    :type diff_algorithm: str
    :param retry_attempts: Number of retry attempts for failed downloads
    :type retry_attempts: int
    :param verify_checksums: Verify file checksums after download
    :type verify_checksums: bool
    :param resume_partial_downloads: Resume interrupted downloads
    :type resume_partial_downloads: bool
    """
    base_path: str = "/var/spool/apt-mirror"
    mirror_path: str = "$base_path/mirror"
    skel_path: str = "$base_path/skel"
    var_path: str = "$base_path/var"
    defaultarch: str = ""
    nthreads: int = 20
    limit_rate: str = "100m"
    _contents: bool = True
    clean: str = "on"  # User-facing option: "off", "on" (generate clean.sh), or "auto" (automatic cleanup)
    _autoclean: bool = False  # Internal: automatic cleanup enabled
    _clean_script: bool = True  # Internal: generate clean.sh script
    _tilde: bool = False
    run_postmirror: bool = True
    auth_no_challenge: bool = False
    no_check_certificate: bool = False
    unlink: bool = False  # Unlink destination files before copying if they differ (for hardlink support)
    postmirror_script: str = "$var_path/postmirror.sh"
    cleanscript: str = "$var_path/clean.sh"
    use_proxy: str = "off"
    http_proxy: str = ""
    https_proxy: str = ""
    proxy_user: str = ""
    proxy_password: str = ""
    certificate: str = ""
    private_key: str = ""
    ca_certificate: str = ""
    # New features
    enable_diffs: bool = True
    diff_algorithm: str = "xdelta3"  # xdelta3, bsdiff, or rsync
    diff_storage_path: str = "$base_path/diffs"
    max_diff_size_ratio: float = 0.5  # Don't create diffs if >50% of original
    progress_update_interval: float = 1.0  # seconds
    retry_attempts: int = 5
    retry_delay: float = 2.0
    verify_checksums: bool = True
    resume_partial_downloads: bool = True
    verify_gpg: bool = False  # Verify GPG signatures of Release files
    gpg_keyring: str = ""  # Custom GPG keyring path (empty = use system default)

    def __post_init__(self):
        """Resolve variable substitutions in configuration values.
        
        Auto-detects default architecture if not specified by running
        ``dpkg --print-architecture``. Then resolves all variable
        references (e.g., ``$base_path``) in config values by recursively
        substituting variable names with their actual values.
        
        :raises subprocess.CalledProcessError: If dpkg command fails
        :raises FileNotFoundError: If dpkg command is not found
        """
        if not self.defaultarch:
            try:
                result = subprocess.run(
                    ["dpkg", "--print-architecture"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self.defaultarch = result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.defaultarch = "amd64"

        # Initialize internal cleanup flags based on clean setting
        clean_value = self.clean.lower() if isinstance(self.clean, str) else "on"
        if clean_value == "off":
            self._autoclean = False
            self._clean_script = False
        elif clean_value == "on":
            self._autoclean = False
            self._clean_script = True
        elif clean_value == "auto":
            self._autoclean = True
            self._clean_script = False
        elif clean_value == "both":
            self._autoclean = True
            self._clean_script = True
        else:
            # Default to "on"
            self._autoclean = False
            self._clean_script = True

        # Resolve variable substitutions
        for key, value in vars(self).items():
            if isinstance(value, str) and "$" in value:
                setattr(self, key, self._resolve_vars(value))

    def _resolve_vars(self, value: str) -> str:
        """Resolve variable substitutions in config values.
        
        Recursively replaces variable references like ``$base_path`` with
        their actual values from the config. Handles dependencies by expanding
        in multiple passes until no more variables remain. Prevents infinite
        loops by limiting substitution depth to 16 iterations.
        
        :param value: String potentially containing variable references
        :type value: str
        :returns: String with variables resolved to actual values
        :rtype: str
        """
        count = 16
        old_value = None
        while "$" in value and count > 0 and value != old_value:
            old_value = value
            # Expand in dependency order: base_path first (no dependencies)
            # Use getattr to get current value, which may have been expanded in previous passes
            base_path_val = getattr(self, 'base_path', '')
            mirror_path_val = getattr(self, 'mirror_path', '')
            skel_path_val = getattr(self, 'skel_path', '')
            var_path_val = getattr(self, 'var_path', '')
            
            # Expand base_path first (it has no dependencies)
            value = value.replace("$base_path", base_path_val)
            # Then expand paths that depend on base_path
            value = value.replace("$mirror_path", mirror_path_val)
            value = value.replace("$skel_path", skel_path_val)
            value = value.replace("$var_path", var_path_val)
            count -= 1
        return value
    
    def _expand_all_vars(self):
        """Expand all variables in config values after parsing.
        
        This method should be called after parse_config() to ensure all
        variables set from the config file are properly expanded, including
        those that depend on other variables (e.g., $var_path depends on $base_path).
        Expands variables in dependency order across multiple passes.
        """
        # Expand in multiple passes until no more variables remain
        # This handles cases where variables depend on other variables
        max_passes = 16
        for pass_num in range(max_passes):
            changed = False
            # Get all config attributes
            attrs = list(vars(self).items())
            for key, value in attrs:
                if isinstance(value, str) and "$" in value:
                    # Resolve variables using current values (which may have been expanded in previous passes)
                    # First expand base_path references
                    expanded = value.replace("$base_path", str(self.base_path))
                    # Then expand paths that depend on base_path
                    expanded = expanded.replace("$mirror_path", str(self.mirror_path))
                    expanded = expanded.replace("$skel_path", str(self.skel_path))
                    expanded = expanded.replace("$var_path", str(self.var_path))
                    if expanded != value:
                        setattr(self, key, expanded)
                        changed = True
            if not changed:
                break


@dataclass
class DownloadTask:
    """Represents a file to download.
    
    Contains all information needed to download a single file from a
    repository, including URL, size, checksums, and target paths.
    
    :param url: URL of the file to download
    :type url: str
    :param size: Expected file size in bytes
    :type size: int
    :param hash_type: Type of hash for verification (SHA512, SHA256, etc.)
    :type hash_type: Optional[HashType]
    :param hashsum: Hash value for verification
    :type hashsum: Optional[str]
    :param canonical_path: Standard path for the file in the mirror
    :type canonical_path: Optional[str]
    :param hash_path: Path when downloaded via by-hash directory
    :type hash_path: Optional[str]
    :param stage: Download stage (release, index, or archive)
    :type stage: str
    """
    url: str
    size: int = 0
    hash_type: Optional[HashType] = None
    hashsum: Optional[str] = None
    canonical_path: Optional[str] = None
    hash_path: Optional[str] = None
    stage: str = "archive"  # release, index, archive


@dataclass
class FileVersion:
    """Tracks file versions for diff generation.
    
    Stores metadata about a file version to enable diff generation
    between versions. Used to determine when files have changed and
    to generate binary diffs for bandwidth savings.
    
    :param path: File path in the mirror
    :type path: str
    :param size: File size in bytes
    :type size: int
    :param hash: SHA256 hash of file contents
    :type hash: str
    :param timestamp: Modification timestamp
    :type timestamp: float
    :param previous_version: Path to previous version (if available)
    :type previous_version: Optional[str]
    """
    path: str
    size: int
    hash: str
    timestamp: float
    previous_version: Optional[str] = None


class ProgressTracker:
    """Tracks download progress and displays real-time statistics.
    
    Provides progress information including percentage complete, download
    speed, and estimated time remaining. Updates are displayed at regular
    intervals to avoid overwhelming the console.
    """
    def __init__(self, total_files: int, total_bytes: int):
        """Initialize progress tracker.
        
        Sets up tracking for the total number of files and bytes to
        download, initializing counters and timers.
        
        :param total_files: Total number of files to download
        :type total_files: int
        :param total_bytes: Total number of bytes to download
        :type total_bytes: int
        """
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.completed_files = 0
        self.completed_bytes = 0
        self.failed_files = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.update_interval = 1.0

    def update(self, bytes_downloaded: int, success: bool = True):
        """Update progress with downloaded bytes.
        
        Increments the progress counters and optionally displays
        progress information if the update interval has elapsed.
        
        :param bytes_downloaded: Number of bytes downloaded
        :type bytes_downloaded: int
        :param success: Whether the download succeeded
        :type success: bool
        """
        self.completed_bytes += bytes_downloaded
        if success:
            self.completed_files += 1
        else:
            self.failed_files += 1

        now = time.time()
        if now - self.last_update >= self.update_interval:
            self._print_progress()
            self.last_update = now

    def _print_progress(self):
        """Print progress information.
        
        Displays current progress including percentage, file count,
        download speed, and estimated time remaining. Updates are
        displayed on the same line to avoid console spam.
        """
        elapsed = time.time() - self.start_time
        percent = (self.completed_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
        speed = self.completed_bytes / elapsed if elapsed > 0 else 0
        remaining = (self.total_bytes - self.completed_bytes) / speed if speed > 0 else 0

        print(f"\rProgress: {percent:.1f}% | "
              f"Files: {self.completed_files}/{self.total_files} | "
              f"Speed: {self._format_bytes(speed)}/s | "
              f"ETA: {self._format_time(remaining)}", end="", flush=True)

    def finish(self):
        """Print final progress summary.
        
        Displays total time elapsed and any failed downloads.
        Should be called when all downloads are complete.
        """
        print()  # New line after progress
        elapsed = time.time() - self.start_time
        print(f"Completed in {self._format_time(elapsed)}")
        if self.failed_files > 0:
            print(f"Warning: {self.failed_files} files failed to download")

    @staticmethod
    def _format_bytes(bytes_val: int) -> str:
        """Format bytes to human readable format.
        
        Converts a byte count to a human-readable string with appropriate
        unit (B, KiB, MiB, GiB, TiB, PiB).
        
        :param bytes_val: Number of bytes
        :type bytes_val: int
        :returns: Formatted string with unit
        :rtype: str
        """
        for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PiB"

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds to human readable format.
        
        Converts a time duration in seconds to a human-readable string
        (e.g., "1h 23m", "45m 30s", "15s").
        
        :param seconds: Duration in seconds
        :type seconds: float
        :returns: Formatted time string
        :rtype: str
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"


class AptMirror:
    """Main apt-mirror class with async support.
    
    Handles all aspects of mirroring APT repositories including:
    downloading, parsing metadata, file management, and diff generation.
    Uses async/await for concurrent operations and improved performance.
    """

    def __init__(self, config_file: str = "/etc/apt/mirror.list"):
        """Initialize apt-mirror instance.
        
        Creates a new AptMirror instance with the specified configuration
        file. The configuration will be parsed when ``parse_config()`` is
        called.
        
        :param config_file: Path to mirror.list configuration file
        :type config_file: str
        """
        self.config_file = config_file
        self.config = Config()
        # Store binaries with keyring: (arch, uri, distribution, components, keyring)
        self.binaries: List[Tuple[str, str, str, List[str], Optional[str]]] = []
        # Store sources with keyring: (uri, distribution, components, keyring)
        self.sources: List[Tuple[str, str, List[str], Optional[str]]] = []
        # Map repository URIs to their keyrings for GPG verification
        self.repo_keyrings: Dict[str, Optional[str]] = {}  # Key: repo_key, Value: keyring path
        self.clean_dirs: Set[str] = set()
        self.skip_clean: Set[str] = set()
        self.download_queue: List[DownloadTask] = []
        self.hashsum_to_files: Dict[str, List[str]] = defaultdict(list)
        self.file_to_hashsums: Dict[str, List[str]] = defaultdict(list)
        self.file_versions: Dict[str, FileVersion] = {}
        # Store checksums from Release files for metadata files (Packages, Sources, etc.)
        # Key: canonical path, Value: (hash_type, hashsum, size)
        self.metadata_checksums: Dict[str, Tuple[HashType, str, int]] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.lock_file: Optional[Path] = None

    async def initialize(self):
        """Initialize async resources and create required directories.
        
        Sets up aiohttp session with appropriate timeouts and connection
        limits, creates the required directory structure (mirror, skel,
        var, and diffs if enabled), and acquires a lock file to prevent
        concurrent execution of multiple apt-mirror instances.
        
        :raises RuntimeError: If apt-mirror is already running (lock file exists)
        """
        # Create directories
        for path in [self.config.mirror_path, self.config.skel_path, self.config.var_path]:
            Path(path).mkdir(parents=True, exist_ok=True)

        if self.config.enable_diffs:
            Path(self.config.diff_storage_path).mkdir(parents=True, exist_ok=True)

        # Create aiohttp session
        connector = aiohttp.TCPConnector(limit=self.config.nthreads * 2)
        timeout = aiohttp.ClientTimeout(total=3600, connect=30)
        
        # Setup proxy with authentication if needed
        self.proxy = None
        self.proxy_auth = None
        if self.config.use_proxy in ("yes", "on"):
            self.proxy = self.config.http_proxy or self.config.https_proxy
            
            # Setup proxy authentication if credentials are provided
            if self.proxy and self.config.proxy_user and self.config.proxy_password:
                self.proxy_auth = aiohttp.BasicAuth(
                    self.config.proxy_user,
                    self.config.proxy_password
                )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=True  # Use environment variables for proxy
        )

        # Create semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(self.config.nthreads)

        # Acquire lock
        self.lock_file = Path(self.config.var_path) / "apt-mirror.lock"
        if self.lock_file.exists():
            raise RuntimeError("apt-mirror is already running, exiting")
        self.lock_file.touch()

    async def cleanup(self):
        """Cleanup async resources and release lock.
        
        Closes the aiohttp session to free network resources and removes
        the lock file to allow other instances to run. Should always be
        called in a finally block to ensure cleanup happens even on errors.
        """
        if self.session:
            await self.session.close()
        if self.lock_file and self.lock_file.exists():
            self.lock_file.unlink()

    def parse_config(self):
        """Parse mirror.list configuration file and mirror.list.d/*.list files.
        
        Reads and parses configuration files line by line, extracting:
        - Configuration settings (set directives)
        - Binary repository definitions (deb lines)
        - Source repository definitions (deb-src lines)
        - Cleanup directives (clean and skip-clean lines)
        
        Supports variable substitution and handles both standard and flat
        repository formats. Also supports per-repository GPG keyring configuration
        using the [signed-by=/path/to/keyring.gpg] option (compatible with APT format).
        
        Configuration files are read in this order:
        1. Main config file (e.g., /etc/apt/mirror.list)
        2. Files in mirror.list.d/ directory (sorted alphabetically)
        
        :raises FileNotFoundError: If config file doesn't exist
        """
        # Collect all config files to parse
        config_files = []
        
        # Add main config file
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        config_files.append(self.config_file)
        
        # Add mirror.list.d/*.list files if directory exists
        config_dir = os.path.dirname(self.config_file)
        mirror_list_d = os.path.join(config_dir, 'mirror.list.d')
        if os.path.isdir(mirror_list_d):
            for filename in sorted(os.listdir(mirror_list_d)):
                if filename.endswith('.list'):
                    config_files.append(os.path.join(mirror_list_d, filename))
        
        # Parse all config files
        for config_file in config_files:
            with open(config_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Parse set commands
                    if line.startswith('set '):
                        match = re.match(r'set\s+(\S+)\s+(.+)', line)
                        if match:
                            key, value = match.groups()
                            value = value.strip('"\'')
                            self._set_config(key, value)
                        continue

                    # Parse deb/deb-src lines
                    # Format: deb [OPTIONS] URI DISTRIBUTION COMPONENT1 COMPONENT2 ...
                    # Options can include: signed-by=/path/to/keyring.gpg, arch=amd64, etc.
                    deb_match = re.match(
                        r'^(deb-src|deb)(?:-(\S+))?\s+(?:\[([^\]]+)\]\s+)?(\S+)\s+(\S+)\s+(.+)$',
                        line
                    )
                    if deb_match:
                        repo_type, arch, options, uri, distribution, components = deb_match.groups()
                        components_list = components.split()
                        
                        # Extract keyring from options (signed-by=/path/to/keyring.gpg)
                        keyring = None
                        if options:
                            signed_by_match = re.search(r'signed-by=([^,\s]+)', options)
                            if signed_by_match:
                                keyring = signed_by_match.group(1).strip('"\'')
                        
                        # Create repository key for keyring mapping
                        repo_key = f"{uri}:{distribution}"
                        
                        if repo_type == "deb":
                            if not arch:
                                arch = self.config.defaultarch
                            # Handle arch= in options
                            if options and 'arch=' in options:
                                arch_match = re.search(r'arch=([^,\s]+)', options)
                                if arch_match:
                                    arch = arch_match.group(1)
                            repo_key = f"{uri}:{distribution}:{arch}"
                            self.binaries.append((arch, uri, distribution, components_list, keyring))
                        else:  # deb-src
                            self.sources.append((uri, distribution, components_list, keyring))
                        
                        # Store keyring mapping for GPG verification
                        if keyring:
                            self.repo_keyrings[repo_key] = keyring
                        elif repo_key not in self.repo_keyrings:
                            # Only set to None if not already set (allow override in mirror.list.d)
                            self.repo_keyrings[repo_key] = None
                        continue

                    # Parse clean/skip-clean
                    clean_match = re.match(r'^(clean|skip-clean)\s+(\S+)', line)
                    if clean_match:
                        clean_type, uri = clean_match.groups()
                        sanitized = self._sanitize_uri(uri)
                        if clean_type == "clean":
                            self.clean_dirs.add(sanitized)
                        else:
                            self.skip_clean.add(sanitized)
                        continue

                    print(f"Warning: Unrecognized line in {config_file}:{line_num}: {line}")

    def _set_config(self, key: str, value: str):
        """Set configuration value.
        
        Sets a configuration value, handling type conversion for boolean
        and integer values. Strips quotes from string values.
        
        :param key: Configuration key name
        :type key: str
        :param value: Configuration value (will be converted to appropriate type)
        :type value: str
        """
        # Handle boolean values
        if value.lower() in ('1', 'yes', 'on', 'true'):
            bool_value = True
        elif value.lower() in ('0', 'no', 'off', 'false'):
            bool_value = False
        else:
            bool_value = None

        if hasattr(self.config, key):
            # Special handling for clean (can be "off", "on", "auto", or "both")
            # Sets internal _autoclean and _clean_script variables
            # "both" enables both script generation and automatic cleanup (useful for testing)
            if key == "clean":
                value_lower = value.lower()
                if value_lower == "off":
                    self.config.clean = "off"
                    self.config._autoclean = False
                    self.config._clean_script = False
                elif value_lower == "on":
                    self.config.clean = "on"
                    self.config._autoclean = False
                    self.config._clean_script = True
                elif value_lower == "auto":
                    self.config.clean = "auto"
                    self.config._autoclean = True
                    self.config._clean_script = False
                elif value_lower == "both":
                    self.config.clean = "both"
                    self.config._autoclean = True
                    self.config._clean_script = True
                else:
                    # Default to "on" if invalid value
                    print(f"Warning: Invalid clean value '{value}', using 'on'")
                    self.config.clean = "on"
                    self.config._autoclean = False
                    self.config._clean_script = True
            elif bool_value is not None:
                setattr(self.config, key, bool_value)
            else:
                # Try to convert to int if possible
                try:
                    setattr(self.config, key, int(value))
                except ValueError:
                    setattr(self.config, key, value)
        else:
            print(f"Warning: Unknown config key: {key}")

    def _sanitize_uri(self, uri: str) -> str:
        """Sanitize URI for filesystem use.
        
        Removes protocol prefix and authentication information from URI
        to create a safe filesystem path. Handles tilde encoding if enabled.
        
        :param uri: URI to sanitize
        :type uri: str
        :returns: Sanitized path suitable for filesystem use
        :rtype: str
        """
        uri = re.sub(r'^\w+://', '', uri)
        uri = re.sub(r'^[^@]+@', '', uri)  # Remove auth
        if self.config._tilde:
            uri = uri.replace('~', '%7E')
        return uri

    def _remove_double_slashes(self, path: str) -> str:
        """Remove double slashes and normalize path.
        
        Removes duplicate slashes from paths while preserving protocol
        prefixes (e.g., http://). Handles tilde encoding if enabled.
        
        :param path: Path to normalize
        :type path: str
        :returns: Normalized path
        :rtype: str
        """
        path = re.sub(r'/+', '/', path)
        path = re.sub(r'^(\w+://)', r'\1', path)  # Preserve protocol
        if self.config._tilde:
            path = path.replace('~', '%7E')
        return path

    async def download_file(
        self,
        task: DownloadTask,
        progress: Optional[ProgressTracker] = None
    ) -> bool:
        """Download a single file asynchronously.
        
        Downloads a file with retry logic, resume support for partial
        downloads, and optional checksum verification. Uses a semaphore
        to limit concurrent downloads according to the nthreads setting.
        Automatically retries failed downloads with exponential backoff.
        
        :param task: DownloadTask containing URL and metadata
        :type task: DownloadTask
        :param progress: Optional progress tracker for reporting
        :type progress: Optional[ProgressTracker]
        :returns: True if download succeeded, False otherwise
        :rtype: bool
        :raises ValueError: If file size mismatch or checksum verification fails
        """
        async with self.semaphore:
            try:
                # Determine local path
                if task.hash_path:
                    local_path = Path(self.config.skel_path) / task.hash_path
                elif task.canonical_path:
                    local_path = Path(self.config.skel_path) / task.canonical_path
                else:
                    uri_path = self._sanitize_uri(task.url)
                    local_path = Path(self.config.skel_path) / uri_path

                # Create directory
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # Check if file exists in skel_path or mirror_path (#198)
                mirror_path = None
                if task.canonical_path:
                    mirror_path = Path(self.config.mirror_path) / task.canonical_path
                
                # Check if file already exists with correct checksum
                if mirror_path and mirror_path.exists():
                    # File exists in mirror, verify it's correct
                    if task.hashsum and self.config.verify_checksums:
                        # Use checksum verification for definitive check
                        if await self._verify_checksum(mirror_path, task.hash_type, task.hashsum):
                            # File is correct, copy from mirror to skel if needed
                            if not local_path.exists() or not local_path.samefile(mirror_path):
                                local_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(mirror_path, local_path)
                            print(f"  ✓ {task.url} (already exists, verified)")
                            if progress:
                                # Use actual file size if task.size is unknown
                                actual_size = mirror_path.stat().st_size
                                bytes_for_progress = task.size if task.size > 0 else actual_size
                                progress.update(bytes_for_progress, True)
                            return True
                    elif task.size > 0:
                        # Fall back to size check if no checksum
                        stat = mirror_path.stat()
                        if stat.st_size == task.size:
                            # File is correct size, copy from mirror to skel if needed
                            if not local_path.exists() or not local_path.samefile(mirror_path):
                                local_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(mirror_path, local_path)
                            print(f"  ✓ {task.url} (already exists, size matches)")
                            if progress:
                                progress.update(task.size, True)
                            return True

                # Check if file exists in skel_path and is correct size
                if local_path.exists() and self.config.resume_partial_downloads:
                    stat = local_path.stat()
                    # Only check size if we know the expected size (task.size > 0)
                    if task.size > 0 and stat.st_size == task.size:
                        # Verify checksum if available
                        if task.hashsum and self.config.verify_checksums:
                            if await self._verify_checksum(local_path, task.hash_type, task.hashsum):
                                # File already downloaded and verified
                                print(f"  ✓ {task.url} (already downloaded, verified)")
                                if progress:
                                    progress.update(task.size, True)
                                return True
                        else:
                            # File already downloaded (size matches)
                            print(f"  ✓ {task.url} (already downloaded, size matches)")
                            if progress:
                                progress.update(task.size, True)
                            return True
                    elif task.size > 0 and stat.st_size < task.size:
                        # Resume partial download
                        headers = {"Range": f"bytes={stat.st_size}-"}
                    elif task.size > 0 and stat.st_size > task.size:
                        # File is larger, re-download
                        local_path.unlink()
                        headers = {}
                    else:
                        # Size unknown (task.size == 0), can't verify by size
                        # If checksum is available, verify it; otherwise re-download
                        if task.hashsum and self.config.verify_checksums:
                            if await self._verify_checksum(local_path, task.hash_type, task.hashsum):
                                # File already downloaded and verified
                                actual_size = stat.st_size
                                print(f"  ✓ {task.url} (already downloaded, verified)")
                                if progress:
                                    progress.update(actual_size, True)
                                return True
                        # No checksum or checksum failed, re-download
                        local_path.unlink()
                        headers = {}
                else:
                    headers = {}

                # Download with retries
                print(f"  → {task.url}")
                for attempt in range(self.config.retry_attempts):
                    try:
                        async with self.session.get(
                            task.url,
                            headers=headers,
                            proxy=self.proxy,
                            proxy_auth=self.proxy_auth,
                            ssl=not self.config.no_check_certificate
                        ) as response:
                            # Handle 404 for optional files (like Release.gpg)
                            if response.status == 404:
                                # Release.gpg is optional, so 404 is acceptable
                                if "Release.gpg" in task.url:
                                    print(f"  ⊘ {task.url} (not found, optional file)")
                                    if progress:
                                        progress.update(0, True)  # Count as success (file is optional)
                                    return True
                                else:
                                    response.raise_for_status()
                            else:
                                response.raise_for_status()

                            # Read all data first (async)
                            data = await response.read()
                            
                            # Write to file in thread pool
                            mode = 'ab' if headers.get('Range') else 'wb'
                            def write_file():
                                with open(local_path, mode) as f:
                                    f.write(data)
                            
                            await asyncio.to_thread(write_file)

                            # Verify size (skip if size is unknown, i.e., 0)
                            if task.size > 0 and local_path.stat().st_size != task.size:
                                raise ValueError(f"Size mismatch: expected {task.size}, got {local_path.stat().st_size}")

                            # Verify checksum if provided
                            if task.hashsum and self.config.verify_checksums:
                                if not await self._verify_checksum(local_path, task.hash_type, task.hashsum):
                                    raise ValueError("Checksum verification failed")

                            # Use actual file size for progress if task.size is unknown (0)
                            actual_size = local_path.stat().st_size
                            bytes_for_progress = task.size if task.size > 0 else actual_size
                            
                            print(f"  ✓ {task.url} (downloaded)")
                            if progress:
                                progress.update(bytes_for_progress, True)
                            return True

                    except Exception as e:
                        if attempt < self.config.retry_attempts - 1:
                            await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        else:
                            raise

            except Exception as e:
                print(f"  ✗ {task.url}: {e}")
                if progress:
                    progress.update(0, False)
                return False

    async def _verify_checksum(self, filepath: Path, hash_type: HashType, expected: str) -> bool:
        """Verify file checksum.
        
        Calculates the hash of a file using the specified hash algorithm
        and compares it with the expected value.
        
        :param filepath: Path to file to verify
        :type filepath: Path
        :param hash_type: Type of hash algorithm to use
        :type hash_type: HashType
        :param expected: Expected hash value (hex string)
        :type expected: str
        :returns: True if hash matches, False otherwise
        :rtype: bool
        """
        hash_obj = {
            HashType.MD5Sum: hashlib.md5(),
            HashType.SHA1: hashlib.sha1(),
            HashType.SHA256: hashlib.sha256(),
            HashType.SHA512: hashlib.sha512(),
        }[hash_type]

        def read_and_hash():
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest() == expected

        return await asyncio.to_thread(read_and_hash)

    async def download_batch(self, tasks: List[DownloadTask], stage: str):
        """Download a batch of files concurrently.
        
        Creates concurrent download tasks for all files in the batch and
        waits for them to complete. Displays progress information including
        start/end times and handles copying of hashsum files to canonical
        locations after downloads complete.
        
        :param tasks: List of DownloadTask objects to download
        :type tasks: List[DownloadTask]
        :param stage: Download stage name (release, index, archive)
        :type stage: str
        """
        print(f"Downloading {len(tasks)} {stage} files using {self.config.nthreads} threads...")
        
        total_bytes = sum(t.size for t in tasks)
        progress = ProgressTracker(len(tasks), total_bytes)
        
        start_time = time.time()
        print(f"Begin time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # Create download tasks
        download_tasks = [self.download_file(task, progress) for task in tasks]
        
        # Wait for all downloads
        results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Count successes and failures
        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False or isinstance(r, Exception))
        skipped = len(tasks) - successful - failed
        
        end_time = time.time()
        print(f"\nEnd time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
        progress.finish()
        
        # Print summary
        if failed > 0:
            print(f"\nSummary: {successful} succeeded, {failed} failed, {skipped} skipped")
        elif skipped > 0:
            print(f"\nSummary: {successful} succeeded, {skipped} skipped (already existed)")

        # Handle hashsum file copying
        await self._copy_hashsum_files()

    async def _copy_hashsum_files(self):
        """Copy files from hashsum locations to canonical locations"""
        for hashsum_path, canonical_paths in self.hashsum_to_files.items():
            source = Path(self.config.skel_path) / hashsum_path
            if not source.exists():
                continue

            for canonical_path in canonical_paths:
                dest = Path(self.config.skel_path) / canonical_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)

                # Copy to other hashsum locations
                for other_hashsum in self.file_to_hashsums.get(canonical_path, []):
                    other_dest = Path(self.config.skel_path) / other_hashsum
                    other_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, other_dest)

    # ... (continuing with more methods)

    async def run(self):
        """Main execution flow.
        
        Orchestrates the complete mirroring process in the correct order:
        
        1. Initialize resources and parse configuration
        2. Download Release files
        3. Download metadata (Packages, Sources, etc.)
        4. Process indexes and queue package downloads
        5. Download packages
        6. Copy skel to mirror
        7. Generate diffs (if enabled)
        8. Cleanup old files
        9. Run postmirror script
        
        Ensures proper cleanup even if errors occur during execution.
        """
        try:
            await self.initialize()
            self.parse_config()
            # Expand all variables after parsing config file (handles dependencies)
            self.config._expand_all_vars()

            # Stage 1: Download Release files
            await self._download_releases()

            # Stage 2: Download metadata (Packages, Sources, etc.)
            await self._download_metadata()

            # Stage 3: Process indexes and queue package downloads
            await self._process_indexes()

            # Stage 4: Download packages
            await self._download_packages()

            # Stage 5: Copy skel to mirror
            await self._copy_skel_to_mirror()

            # Stage 6: Generate diffs if enabled
            if self.config.enable_diffs:
                await self._generate_diffs()

            # Stage 7: Cleanup
            await self._cleanup_old_files()

            # Stage 8: Run postmirror script
            if self.config.run_postmirror:
                await self._run_postmirror()

        finally:
            await self.cleanup()

    def _add_url_to_download(
        self,
        url: str,
        size: int = 0,
        strongest_hash: Optional[HashType] = None,
        hash_type: Optional[HashType] = None,
        hashsum: Optional[str] = None
    ):
        """Add URL to download queue with hash handling.
        
        Adds a file to the download queue, handling by-hash downloads
        when hash information is provided. Tracks relationships between
        hashsum files and canonical locations for proper file management.
        
        :param url: URL of file to download
        :type url: str
        :param size: Expected file size in bytes
        :type size: int
        :param strongest_hash: Strongest available hash type
        :type strongest_hash: Optional[HashType]
        :param hash_type: Specific hash type for this file
        :type hash_type: Optional[HashType]
        :param hashsum: Hash value for verification
        :type hashsum: Optional[str]
        """
        url = self._remove_double_slashes(url)
        canonical_path = self._sanitize_uri(url)
        self.skip_clean.add(canonical_path)

        if hashsum and strongest_hash:
            # Use by-hash download
            hash_dir = f"by-hash/{hash_type.value if hash_type else strongest_hash.value}"
            hash_url = f"{os.path.dirname(url)}/{hash_dir}/{hashsum}"
            hash_path = f"{os.path.dirname(canonical_path)}/{hash_dir}/{hashsum}"
            self.skip_clean.add(hash_path)

            if hash_type == strongest_hash:
                # Download using strongest hash
                self.hashsum_to_files[hash_path].append(canonical_path)
                task = DownloadTask(
                    url=hash_url,
                    size=size,
                    hash_type=hash_type,
                    hashsum=hashsum,
                    canonical_path=canonical_path,
                    hash_path=hash_path,
                    stage="archive"
                )
                self.download_queue.append(task)
            else:
                # Track for later copying
                self.file_to_hashsums[canonical_path].append(hash_path)
        else:
            # Regular download
            task = DownloadTask(url=url, size=size, canonical_path=canonical_path, stage="archive")
            self.download_queue.append(task)

    async def _download_releases(self):
        """Download Release files.
        
        Downloads InRelease, Release, and Release.gpg files for all configured
        repositories. Handles both standard (with components) and flat repository
        formats. Validates that at least one Release file is successfully downloaded
        for each repository.
        
        :raises RuntimeError: If no Release files are found for any repository
        """
        tasks = []
        release_urls = []
        repo_release_map = {}  # Track which releases belong to which repo (#193)

        # Process source repositories
        for uri, distribution, components, keyring in self.sources:
            repo_key = f"{uri}:{distribution}"
            if components:
                url_base = f"{uri}/dists/{distribution}/"
            else:
                # Flat repository format
                url_base = f"{uri}/{distribution}/"
            
            repo_release_map[repo_key] = []
            for filename in ["InRelease", "Release", "Release.gpg"]:
                url = f"{url_base}{filename}"
                release_urls.append(url)
                canonical = self._sanitize_uri(url)
                task = DownloadTask(url=url, canonical_path=canonical, stage="release")
                tasks.append(task)
                repo_release_map[repo_key].append(canonical)

        # Process binary repositories
        for arch, uri, distribution, components, keyring in self.binaries:
            repo_key = f"{uri}:{distribution}:{arch}"
            if components:
                url_base = f"{uri}/dists/{distribution}/"
            else:
                # Flat repository format
                url_base = f"{uri}/{distribution}/"
            
            repo_release_map[repo_key] = []
            for filename in ["InRelease", "Release", "Release.gpg"]:
                url = f"{url_base}{filename}"
                release_urls.append(url)
                canonical = self._sanitize_uri(url)
                task = DownloadTask(url=url, canonical_path=canonical, stage="release")
                tasks.append(task)
                repo_release_map[repo_key].append(canonical)

        if tasks:
            await self.download_batch(tasks, "release")
            self.release_urls = release_urls
            
            # Verify at least one Release file exists for each repository (#193)
            for repo_key, release_paths in repo_release_map.items():
                found_release = False
                for release_path in release_paths:
                    # Check both skel and mirror paths
                    skel_path = Path(self.config.skel_path) / release_path
                    mirror_path = Path(self.config.mirror_path) / release_path
                    # Only check InRelease and Release, not Release.gpg (optional)
                    if "Release.gpg" not in release_path:
                        if skel_path.exists() or mirror_path.exists():
                            found_release = True
                            break
                
                if not found_release:
                    print(f"\nWarning: No Release file found for repository: {repo_key}")
                    print("  This may indicate an invalid repository configuration or network issue.")
                    print("  Continuing anyway, but metadata downloads may fail.")
            
            # Verify GPG signatures if enabled
            if self.config.verify_gpg:
                await self._verify_release_signatures(repo_release_map)

    async def _verify_release_signatures(self, repo_release_map: Dict[str, List[str]]):
        """Verify GPG signatures of Release files.
        
        Verifies GPG signatures for all downloaded Release files. Supports both
        InRelease (inline signed) and Release + Release.gpg (detached signature) formats.
        Uses gpgv command which is standard on Debian/Ubuntu systems.
        
        :param repo_release_map: Dictionary mapping repository keys to their release file paths
        :type repo_release_map: Dict[str, List[str]]
        """
        if not self.config.verify_gpg:
            return
        
        # Check if gpgv is available
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ['gpgv', '--version'],
                capture_output=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\nWarning: gpgv command not found. GPG verification disabled.")
            print("  Install gpgv with: sudo apt-get install gpgv")
            return
        
        verified_count = 0
        failed_count = 0
        
        for repo_key, release_paths in repo_release_map.items():
            # Find InRelease or Release + Release.gpg files
            inrelease_path = None
            release_path = None
            release_gpg_path = None
            
            for release_path_str in release_paths:
                # Check both skel and mirror paths
                skel_path = Path(self.config.skel_path) / release_path_str
                mirror_path = Path(self.config.mirror_path) / release_path_str
                
                if "InRelease" in release_path_str:
                    if skel_path.exists():
                        inrelease_path = skel_path
                    elif mirror_path.exists():
                        inrelease_path = mirror_path
                elif "Release.gpg" in release_path_str:
                    if skel_path.exists():
                        release_gpg_path = skel_path
                    elif mirror_path.exists():
                        release_gpg_path = mirror_path
                elif "Release" in release_path_str and "Release.gpg" not in release_path_str:
                    if skel_path.exists():
                        release_path = skel_path
                    elif mirror_path.exists():
                        release_path = mirror_path
            
            # Get keyring for this repository
            keyring = self.repo_keyrings.get(repo_key)
            
            # Verify InRelease (inline signed)
            if inrelease_path:
                if await self._verify_gpg_signature(inrelease_path, None, repo_key, keyring):
                    verified_count += 1
                else:
                    failed_count += 1
            # Verify Release + Release.gpg (detached signature)
            elif release_path and release_gpg_path:
                if await self._verify_gpg_signature(release_path, release_gpg_path, repo_key, keyring):
                    verified_count += 1
                else:
                    failed_count += 1
            else:
                print(f"\nWarning: No Release signature files found for {repo_key}")
                print("  GPG verification skipped for this repository.")
        
        if verified_count > 0:
            print(f"\nGPG verification: {verified_count} repository signature(s) verified successfully")
        if failed_count > 0:
            print(f"\nWarning: {failed_count} repository signature(s) failed verification")

    async def _verify_gpg_signature(self, release_file: Path, gpg_file: Optional[Path], repo_key: str, keyring: Optional[str] = None) -> bool:
        """Verify GPG signature of a Release file.
        
        Verifies GPG signature using gpgv command. Supports both inline signed
        InRelease files and detached signatures (Release + Release.gpg).
        Uses per-repository keyring if specified, otherwise falls back to global
        keyring or system defaults.
        
        :param release_file: Path to Release or InRelease file
        :type release_file: Path
        :param gpg_file: Path to Release.gpg file (None for InRelease)
        :type gpg_file: Optional[Path]
        :param repo_key: Repository identifier for error messages
        :type repo_key: str
        :param keyring: Per-repository keyring path (overrides global keyring)
        :type keyring: Optional[str]
        :returns: True if signature is valid, False otherwise
        :rtype: bool
        """
        if not release_file.exists():
            return False
        
        # Build gpgv command
        cmd = ['gpgv']
        
        # Add keyring option - per-repository keyring takes precedence
        keyring_to_use = keyring or self.config.gpg_keyring
        if keyring_to_use:
            # Expand path if it's relative (e.g., /etc/apt/keyrings/ubuntu.gpg)
            if not os.path.isabs(keyring_to_use):
                # If relative, try common locations
                for base_dir in ['/etc/apt/keyrings', '/usr/share/keyrings', '/etc/apt/trusted.gpg.d']:
                    full_path = os.path.join(base_dir, keyring_to_use)
                    if os.path.exists(full_path):
                        keyring_to_use = full_path
                        break
            cmd.extend(['--keyring', keyring_to_use])
        # If no keyring specified, gpgv will use system default keyrings
        
        # For detached signature: gpgv Release.gpg Release
        # For inline signed: gpgv InRelease
        if gpg_file and gpg_file.exists():
            cmd.append(str(gpg_file))
            cmd.append(str(release_file))
        else:
            # InRelease (inline signed)
            cmd.append(str(release_file))
        
        try:
            def run_gpgv():
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.returncode == 0
            
            verified = await asyncio.to_thread(run_gpgv)
            
            if verified:
                print(f"  ✓ GPG signature verified for {repo_key}")
                return True
            else:
                print(f"  ✗ GPG signature verification failed for {repo_key}")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"  ✗ GPG signature verification failed for {repo_key}: {e.stderr.strip()}")
            return False
        except Exception as e:
            print(f"  ✗ GPG signature verification error for {repo_key}: {e}")
            return False

    async def _parse_release_file(self, release_path: Path) -> Dict:
        """Parse Release file and extract metadata.
        
        Reads and parses a Release or InRelease file to extract information
        about available files, their checksums, and whether by-hash downloads
        are supported.
        
        :param release_path: Path to Release file directory
        :type release_path: Path
        :returns: Dictionary containing parsed release information
        :rtype: Dict
        """
        # Try InRelease first, then Release
        for filename in ["InRelease", "Release"]:
            filepath = release_path.parent / filename
            if filepath.exists():
                def read_file():
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                
                content = await asyncio.to_thread(read_file)
                return self._parse_release_content(content)
        return {}

    def _parse_release_content(self, content: str) -> Dict:
        """Parse Release file content.
        
        Parses the text content of a Release file to extract hash sections,
        file listings, and Acquire-By-Hash settings.
        
        :param content: Text content of Release file
        :type content: str
        :returns: Dictionary containing parsed release information
        :rtype: Dict
        """
        result = {
            'hashes': {},
            'acquire_by_hash': False,
            'files': []
        }
        
        current_hash = None
        hash_strength = [HashType.SHA512, HashType.SHA256, HashType.SHA1, HashType.MD5Sum]
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Check for Acquire-By-Hash
            if line == "Acquire-By-Hash: yes":
                result['acquire_by_hash'] = True
            
            # Check for hash section
            for ht in hash_strength:
                if line == f"{ht.value}:":
                    current_hash = ht
                    result['hashes'][ht] = {}
                    break
            
            # Parse hash lines
            if current_hash and line.startswith(' '):
                parts = line.split()
                if len(parts) == 3:
                    hashsum, size, filename = parts
                    result['hashes'][current_hash][filename] = {
                        'hashsum': hashsum,
                        'size': int(size)
                    }
                    result['files'].append({
                        'filename': filename,
                        'size': int(size),
                        'hash_type': current_hash,
                        'hashsum': hashsum
                    })
            elif line and not line.startswith(' '):
                current_hash = None
        
        return result

    async def _download_metadata(self):
        """Download metadata files from Release"""
        tasks = []
        index_urls = []

        # Process binary repositories
        for arch, uri, distribution, components, _ in self.binaries:
            if components:
                dist_uri = f"{uri}/dists/{distribution}/"
            else:
                # Flat repository format
                dist_uri = f"{uri}/{distribution}/"
            
            # Find Release file
            release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}Release")
            if not release_path.exists():
                release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}InRelease")
            
            if release_path.exists():
                release_data = await self._parse_release_file(release_path.parent)
                
                # Determine strongest hash
                strongest_hash = None
                if release_data.get('acquire_by_hash'):
                    for ht in [HashType.SHA512, HashType.SHA256, HashType.SHA1, HashType.MD5Sum]:
                        if ht in release_data.get('hashes', {}):
                            strongest_hash = ht
                            break
                
                # Extract metadata files
                for file_info in release_data.get('files', []):
                    filename = file_info['filename']
                    size = file_info['size']
                    hash_type = file_info.get('hash_type')
                    hashsum = file_info.get('hashsum')
                    
                    # Match patterns for Packages, Contents, c-n-f, dep11, etc.
                    # Patterns must match the old Perl implementation exactly
                    matched = False
                    if components:
                        # Check against each component
                        for comp in components:
                            # Packages files (compressed)
                            if re.match(rf"^{re.escape(comp)}/binary-{re.escape(arch)}/Packages(\.(gz|bz2|xz))?$", filename) or \
                               re.match(rf"^{re.escape(comp)}/binary-all/Packages(\.(gz|bz2|xz))?$", filename):
                                matched = True
                                break
                            # Contents files (compressed)
                            if re.match(rf"^{re.escape(comp)}/Contents-{re.escape(arch)}(\.(gz|bz2|xz))?$", filename) or \
                               re.match(rf"^{re.escape(comp)}/Contents-all(\.(gz|bz2|xz))?$", filename):
                                matched = True
                                break
                            # c-n-f files: Commands-{arch} with optional compression (matches old: Commands-${arch}(\.(gz|bz2|xz))?)
                            if re.match(rf"^{re.escape(comp)}/cnf/Commands-{re.escape(arch)}(\.(gz|bz2|xz))?$", filename) or \
                               re.match(rf"^{re.escape(comp)}/cnf/Commands-all(\.(gz|bz2|xz))?$", filename):
                                matched = True
                                break
                            # dep11 files: Components-{arch}.yml or icons-*.tar, compressed (matches old: Components-${arch}\.yml|icons-[^./]+\.tar)\.(gz|bz2|xz)
                            # Also handle uncompressed dep11 files (modern APT may use uncompressed)
                            if re.match(rf"^{re.escape(comp)}/dep11/Components-{re.escape(arch)}\.yml(\.(gz|bz2|xz))?$", filename) or \
                               re.match(rf"^{re.escape(comp)}/dep11/icons-[^./]+\.tar(\.(gz|bz2|xz))?$", filename) or \
                               re.match(rf"^{re.escape(comp)}/dep11/.*", filename):  # Catch any other dep11 files
                                matched = True
                                break
                            # Translation files: i18n/Translation-*.bz2 or .xz (modern APT uses bz2/xz, not gz)
                            if re.match(rf"^{re.escape(comp)}/i18n/Translation-[^./]*\.(bz2|xz)$", filename):
                                matched = True
                                break
                            # i18n/Index file (explicitly downloaded in old code)
                            if re.match(rf"^{re.escape(comp)}/i18n/Index$", filename):
                                matched = True
                                break
                    else:
                        # Flat repository - match general patterns
                        if re.match(r"^Packages(\.(gz|bz2|xz))?$", filename) or \
                           re.match(r"^Contents-.*(\.(gz|bz2|xz))?$", filename) or \
                           re.match(r"^cnf/.*", filename) or \
                           re.match(r"^dep11/.*", filename) or \
                           re.match(r"^i18n/.*", filename):
                            matched = True
                    
                    # Also match Contents files that don't have component prefix
                    if not matched:
                        if re.match(rf"^Contents-{re.escape(arch)}(\.(gz|bz2|xz))?$", filename) or \
                           re.match(r"^Contents-all(\.(gz|bz2|xz))?$", filename):
                            matched = True
                    
                    if matched:
                        url = f"{dist_uri}{filename}"
                        index_urls.append(url)
                        canonical = self._sanitize_uri(url)
                        
                        # Store checksum for later verification (#199)
                        if strongest_hash and hashsum:
                            self.metadata_checksums[canonical] = (strongest_hash, hashsum, size)
                            self._add_url_to_download(
                                url, size, strongest_hash, hash_type, hashsum
                            )
                        else:
                            # Store size for basic validation
                            self.metadata_checksums[canonical] = (None, None, size)
                            task = DownloadTask(
                                url=url, size=size, canonical_path=canonical, stage="index"
                            )
                            tasks.append(task)

        # Process source repositories
        for uri, distribution, components, _ in self.sources:
            if components:
                dist_uri = f"{uri}/dists/{distribution}/"
            else:
                # Flat repository format
                dist_uri = f"{uri}/{distribution}/"
            
            release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}Release")
            if not release_path.exists():
                release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}InRelease")
            
            if release_path.exists():
                release_data = await self._parse_release_file(release_path.parent)
                
                for file_info in release_data.get('files', []):
                    filename = file_info['filename']
                    if re.match(r".*Sources(\.(gz|bz2|xz))?$", filename) or \
                       re.match(r".*Contents-source(\.(gz|bz2|xz))?$", filename):
                        url = f"{dist_uri}{filename}"
                        index_urls.append(url)
                        canonical = self._sanitize_uri(url)
                        # Store checksum for later verification (#199)
                        hash_type = file_info.get('hash_type')
                        hashsum = file_info.get('hashsum')
                        if hash_type and hashsum:
                            self.metadata_checksums[canonical] = (hash_type, hashsum, file_info['size'])
                        else:
                            self.metadata_checksums[canonical] = (None, None, file_info['size'])
                        task = DownloadTask(
                            url=url, size=file_info['size'], canonical_path=canonical, stage="index"
                        )
                        tasks.append(task)

        if tasks:
            await self.download_batch(tasks, "index")
            self.index_urls = index_urls
        
        # Download i18n/Index files explicitly (like old code does)
        # These are needed to find translation files
        await self._download_i18n_indexes()
        
        # Process translation indexes to find all translation files
        await self._process_translation_indexes()

    async def _download_i18n_indexes(self):
        """Download i18n/Index files explicitly for each component.
        
        These files list available translation files. Downloaded explicitly
        like the old Perl implementation does.
        """
        tasks = []
        
        for arch, uri, distribution, components, _ in self.binaries:
            if not components:
                continue
                
            dist_uri = f"{uri}/dists/{distribution}/"
            
            for component in components:
                # Download i18n/Index file for this component
                url = f"{dist_uri}{component}/i18n/Index"
                canonical = self._sanitize_uri(url)
                task = DownloadTask(url=url, canonical_path=canonical, stage="index")
                tasks.append(task)
                # Add to index_urls for copying
                if not hasattr(self, 'index_urls'):
                    self.index_urls = []
                self.index_urls.append(url)
        
        if tasks:
            await self.download_batch(tasks, "i18n-index")

    async def _process_translation_indexes(self):
        """Process i18n/Index files to find all translation files.
        
        Parses i18n/Index files to extract translation file listings.
        Falls back to parsing Release file if i18n/Index is not found.
        """
        tasks = []
        translation_urls = []
        
        for arch, uri, distribution, components, _ in self.binaries:
            if not components:
                continue
                
            dist_uri = f"{uri}/dists/{distribution}/"
            
            for component in components:
                # Try to parse i18n/Index file first
                index_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}{component}/i18n/Index")
                
                if index_path.exists():
                    # Parse i18n/Index file
                    def read_index():
                        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                            return f.read()
                    
                    content = await asyncio.to_thread(read_index)
                    translation_files = self._parse_translation_index(content, f"{dist_uri}{component}/i18n/")
                    
                    for filename, size in translation_files:
                        url = f"{dist_uri}{component}/i18n/{filename}"
                        translation_urls.append(url)
                        canonical = self._sanitize_uri(url)
                        task = DownloadTask(url=url, size=size, canonical_path=canonical, stage="index")
                        tasks.append(task)
                else:
                    # Fall back to parsing Release file for translation files
                    release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}Release")
                    if not release_path.exists():
                        release_path = Path(self.config.skel_path) / self._sanitize_uri(f"{dist_uri}InRelease")
                    
                    if release_path.exists():
                        release_data = await self._parse_release_file(release_path.parent)
                        for file_info in release_data.get('files', []):
                            filename = file_info['filename']
                            # Match translation files: component/i18n/Translation-*.bz2 or .xz
                            if re.match(rf"^{re.escape(component)}/i18n/Translation-[^./]*\.(bz2|xz)$", filename):
                                url = f"{dist_uri}{filename}"
                                translation_urls.append(url)
                                canonical = self._sanitize_uri(url)
                                size = file_info['size']
                                hash_type = file_info.get('hash_type')
                                hashsum = file_info.get('hashsum')
                                
                                if hash_type and hashsum:
                                    self.metadata_checksums[canonical] = (hash_type, hashsum, size)
                                    self._add_url_to_download(url, size, hash_type, hash_type, hashsum)
                                else:
                                    task = DownloadTask(url=url, size=size, canonical_path=canonical, stage="index")
                                    tasks.append(task)
        
        if tasks:
            await self.download_batch(tasks, "translation")
        
        # Add translation URLs to index_urls for copying
        if translation_urls:
            if not hasattr(self, 'index_urls'):
                self.index_urls = []
            self.index_urls.extend(translation_urls)

    def _parse_translation_index(self, content: str, base_path: str) -> List[Tuple[str, int]]:
        """Parse i18n/Index file to extract translation file listings.
        
        :param content: Content of i18n/Index file
        :type content: str
        :param base_path: Base path for translation files (unused, kept for compatibility)
        :type base_path: str
        :returns: List of (filename, size) tuples
        :rtype: List[Tuple[str, int]]
        """
        files = []
        current_hash = None
        hash_strength = [HashType.SHA512, HashType.SHA256, HashType.SHA1, HashType.MD5Sum]
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Check for hash section
            for ht in hash_strength:
                if line == f"{ht.value}:":
                    current_hash = ht
                    break
            
            # Parse hash lines
            if current_hash and line.startswith(' '):
                parts = line.split()
                if len(parts) == 3:
                    hashsum, size, filename = parts
                    files.append((filename, int(size)))
            elif line and not line.startswith(' '):
                current_hash = None
        
        return files

    async def _decompress_file(self, filepath: Path) -> Optional[Path]:
        """Decompress a file if needed"""
        for ext in ['.gz', '.bz2', '.xz']:
            if filepath.name.endswith(ext):
                decompressed = filepath.with_suffix('')
                
                def decompress():
                    try:
                        if ext == '.gz':
                            with open(filepath, 'rb') as f_in, open(decompressed, 'wb') as f_out:
                                f_out.write(gzip.decompress(f_in.read()))
                        elif ext == '.bz2':
                            with open(filepath, 'rb') as f_in, open(decompressed, 'wb') as f_out:
                                f_out.write(bz2.decompress(f_in.read()))
                        elif ext == '.xz':
                            with open(filepath, 'rb') as f_in, open(decompressed, 'wb') as f_out:
                                f_out.write(lzma.decompress(f_in.read()))
                        return decompressed
                    except Exception as e:
                        print(f"Warning: Failed to decompress {filepath}: {e}")
                        return None
                
                result = await asyncio.to_thread(decompress)
                return result
        return filepath

    async def _process_packages_index(self, uri: str, index_path: Path, mirror_base: Path):
        """Process Packages index file.
        
        Parses a Packages index file to extract package information and
        queue package files for download. Checks if files need updating
        by comparing sizes and checksums.
        
        :param uri: Base URI of the repository
        :type uri: str
        :param index_path: Path to Packages index file
        :type index_path: Path
        :param mirror_base: Base path of mirror directory
        :type mirror_base: Path
        """
        # Verify file completeness before parsing (#199)
        canonical = self._sanitize_uri(uri + '/' + index_path.name)
        if canonical in self.metadata_checksums:
            hash_type, hashsum, expected_size = self.metadata_checksums[canonical]
            actual_size = index_path.stat().st_size
            
            # Check size first (fast check)
            if actual_size != expected_size:
                print(f"\nWarning: Packages file {index_path.name} size mismatch: "
                      f"expected {expected_size}, got {actual_size}")
                return
            
            # Verify checksum if available
            if hash_type and hashsum and self.config.verify_checksums:
                if not await self._verify_checksum(index_path, hash_type, hashsum):
                    print(f"\nWarning: Packages file {index_path.name} checksum verification failed")
                    return
        
        # Decompress if needed
        decompressed = await self._decompress_file(index_path)
        if not decompressed or not decompressed.exists():
            return

        def read_index():
            with open(decompressed, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        
        content = await asyncio.to_thread(read_index)
        
        # Parse package entries
        packages = content.split('\n\n')
        for package in packages:
            if not package.strip():
                continue
            
            lines = {}
            current_key = None
            for line in package.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    current_key = key.strip()
                    lines[current_key] = value.strip()
                elif current_key and line.startswith(' '):
                    lines[current_key] += '\n' + line
            
            if 'Filename' in lines:
                filename = lines['Filename'].strip()
                size = int(lines.get('Size', '0'))
                file_path = self._remove_double_slashes(f"{uri}/{filename}")
                canonical = self._sanitize_uri(file_path)
                self.skip_clean.add(canonical)
                
                mirror_file = mirror_base / canonical
                
                # Extract checksums from Packages entry (#198)
                hash_type = None
                hashsum = None
                for ht in [HashType.SHA512, HashType.SHA256, HashType.SHA1, HashType.MD5Sum]:
                    checksum_key = ht.value
                    if checksum_key in lines:
                        hash_type = ht
                        hashsum = lines[checksum_key].strip()
                        break
                
                # Check if update needed using checksum if available, otherwise size (#198)
                needs_update = True
                if mirror_file.exists():
                    if hash_type and hashsum and self.config.verify_checksums:
                        # Use checksum for definitive check
                        if await self._verify_checksum(mirror_file, hash_type, hashsum):
                            needs_update = False
                    else:
                        # Fall back to size check
                        if mirror_file.stat().st_size == size:
                            needs_update = False
                
                if needs_update:
                    if hash_type and hashsum:
                        self._add_url_to_download(file_path, size, hash_type, hash_type, hashsum)
                    else:
                        self._add_url_to_download(file_path, size)

    async def _process_indexes(self):
        """Process Packages/Sources indexes"""
        print("Processing indexes...", end="", flush=True)
        
        for arch, uri, distribution, components, _ in self.binaries:
            print("P", end="", flush=True)
            if components:
                for component in components:
                    index_path = Path(self.config.skel_path) / self._sanitize_uri(
                        f"{uri}/dists/*/{component}/binary-{arch}/Packages"
                    )
                    # Find actual Packages file (may be compressed)
                    for ext in ['', '.gz', '.bz2', '.xz']:
                        test_path = index_path.parent / f"Packages{ext}"
                        if test_path.exists():
                            mirror_base = Path(self.config.mirror_path)
                            await self._process_packages_index(uri, test_path, mirror_base)
                            break

        for uri, distribution, components, _ in self.sources:
            print("S", end="", flush=True)
            # Similar processing for Sources
            pass

        print()  # New line

    async def _download_packages(self):
        """Download package files.
        
        Downloads all queued package files (deb packages, source tarballs,
        etc.) that were identified during index processing. Displays total
        size to be downloaded before starting.
        """
        if self.download_queue:
            total_bytes = sum(t.size for t in self.download_queue)
            print(f"{self._format_bytes(total_bytes)} will be downloaded into archive.")
            await self.download_batch(self.download_queue, "archive")

    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PiB"

    async def _copy_file(self, source: Path, dest: Path):
        """Copy file preserving metadata.
        
        Copies a file from source to destination, preserving file metadata
        (timestamps, permissions). Attempts to create a hardlink first to
        save disk space, falling back to a regular copy if hardlinking fails
        (e.g., different filesystem).
        
        The unlink option is for hardlink support: when files are hardlinked
        (multiple directory entries pointing to the same inode), you cannot
        simply overwrite one - you must unlink it first, then create a new file.
        This prevents all hardlinked copies from being updated simultaneously.
        
        :param source: Source file path
        :type source: Path
        :param dest: Destination file path
        :type dest: Path
        """
        if not source.exists():
            return
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if files are identical (same stat info means same file or already copied)
        if dest.exists():
            source_stat = source.stat()
            dest_stat = dest.stat()
            
            # Compare stat info - if identical, files are the same
            if (source_stat.st_size == dest_stat.st_size and
                source_stat.st_mtime == dest_stat.st_mtime and
                source_stat.st_mode == dest_stat.st_mode):
                return  # Already copied and identical
            
            # If unlink is enabled and files differ, unlink destination first
            # This is important for hardlinked files - you can't overwrite a hardlink
            if self.config.unlink:
                # Compare file contents (like Perl's File::Compare)
                def files_differ():
                    if source_stat.st_size != dest_stat.st_size:
                        return True
                    # Compare file contents
                    with open(source, 'rb') as f1, open(dest, 'rb') as f2:
                        while True:
                            chunk1 = f1.read(8192)
                            chunk2 = f2.read(8192)
                            if chunk1 != chunk2:
                                return True
                            if not chunk1:  # Both files ended
                                return False
                
                if await asyncio.to_thread(files_differ):
                    dest.unlink()
        
        # Copy file (will create hardlink if possible, otherwise regular copy)
        # Try to create hardlink first, fall back to copy
        try:
            # Try to create hardlink (saves space if both files are on same filesystem)
            os.link(source, dest)
            # Copy metadata
            shutil.copystat(source, dest)
        except (OSError, AttributeError):
            # Hardlink failed (different filesystem or other reason), use regular copy
            shutil.copy2(source, dest)

    async def _copy_skel_to_mirror(self):
        """Copy files from skel to mirror directory"""
        print("Copying files from skel to mirror...")
        copied_count = 0
        
        # Copy release and index files
        for url in getattr(self, 'release_urls', []) + getattr(self, 'index_urls', []):
            canonical = self._sanitize_uri(url)
            source = Path(self.config.skel_path) / canonical
            dest = Path(self.config.mirror_path) / canonical
            if source.exists():
                await self._copy_file(source, dest)
                # Ensure copied files are in skip_clean
                self.skip_clean.add(canonical)
                copied_count += 1
            elif "Release" in canonical or "InRelease" in canonical:
                # Warn if Release files are missing - they're critical
                print(f"Warning: Release file not found in skel: {canonical}")
            
            # Handle hashsum files
            if canonical in self.hashsum_to_files:
                for target_file in self.hashsum_to_files[canonical]:
                    target_dest = Path(self.config.mirror_path) / target_file
                    if source.exists():
                        await self._copy_file(source, target_dest)
                        self.skip_clean.add(target_file)
        
        # Copy all package files from download queue
        for task in self.download_queue:
            if task.canonical_path:
                source = Path(self.config.skel_path) / task.canonical_path
                dest = Path(self.config.mirror_path) / task.canonical_path
                if source.exists():
                    await self._copy_file(source, dest)
                    # Ensure copied files are in skip_clean
                    self.skip_clean.add(task.canonical_path)
                    copied_count += 1
            
            # Copy hashsum files for packages
            if task.hash_path:
                source = Path(self.config.skel_path) / task.hash_path
                dest = Path(self.config.mirror_path) / task.hash_path
                if source.exists():
                    await self._copy_file(source, dest)
                    self.skip_clean.add(task.hash_path)
        
        print(f"Copied {copied_count} files from skel to mirror.")

    async def _generate_diffs(self):
        """Generate diffs for changed files.
        
        Compares current file versions with previous versions stored in the
        file_versions.json database. For files that have changed, generates
        binary diffs using the configured algorithm (xdelta3, bsdiff, or rsync).
        Only creates diffs if they're smaller than the configured threshold
        (max_diff_size_ratio) to avoid creating diffs that are larger than
        the original files. Updates the version database with new file hashes.
        """
        if not self.config.enable_diffs:
            return
        
        print("Generating diffs for changed files...")
        diff_count = 0
        
        # Load previous file versions
        # Ensure var_path is resolved (should already be done in __post_init__, but be safe)
        var_path_str = str(self.config.var_path)
        if "$" in var_path_str:
            # Variable expansion failed, try to resolve manually
            var_path_str = var_path_str.replace("$base_path", self.config.base_path)
        versions_file = Path(var_path_str) / "file_versions.json"
        if versions_file.exists():
            def read_versions():
                with open(versions_file, 'r') as f:
                    return json.load(f)
            old_versions = await asyncio.to_thread(read_versions)
        else:
            old_versions = {}
        
        new_versions = {}
        
        # Process each downloaded file
        for task in self.download_queue:
            if not task.canonical_path:
                continue
            
            mirror_file = Path(self.config.mirror_path) / task.canonical_path
            if not mirror_file.exists():
                continue
            
            # Calculate current hash
            def calc_hash():
                file_hash = hashlib.sha256()
                with open(mirror_file, 'rb') as f:
                    while chunk := f.read(8192):
                        file_hash.update(chunk)
                return file_hash.hexdigest()
            
            current_hash = await asyncio.to_thread(calc_hash)
            
            # Check if file changed
            old_version = old_versions.get(task.canonical_path)
            if old_version and old_version['hash'] != current_hash:
                # File changed, generate diff
                old_file = Path(self.config.mirror_path) / old_version.get('path', task.canonical_path)
                
                if old_file.exists():
                    diff_path = Path(self.config.diff_storage_path) / f"{task.canonical_path}.diff"
                    diff_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Generate diff using xdelta3 or similar
                    if await self._create_diff(old_file, mirror_file, diff_path):
                        diff_count += 1
                        print(f"Generated diff: {diff_path}")
            
            # Store new version
            new_versions[task.canonical_path] = {
                'path': task.canonical_path,
                'size': task.size,
                'hash': current_hash,
                'timestamp': time.time()
            }
        
        # Save new versions
        def write_versions():
            # Ensure parent directory exists
            versions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(versions_file, 'w') as f:
                json.dump(new_versions, f, indent=2)
        
        await asyncio.to_thread(write_versions)
        
        print(f"Generated {diff_count} diffs")

    async def _create_diff(self, old_file: Path, new_file: Path, diff_path: Path) -> bool:
        """Create a diff between two files.
        
        Uses the configured diff algorithm (xdelta3, bsdiff, or rsync) to
        generate a binary diff between the old and new file versions. Only
        returns True if the diff was successfully created and is smaller than
        the configured threshold (max_diff_size_ratio). If the diff is too
        large, it is deleted and False is returned.
        
        :param old_file: Path to old version of file
        :type old_file: Path
        :param new_file: Path to new version of file
        :type new_file: Path
        :param diff_path: Path where diff should be stored
        :type diff_path: Path
        :returns: True if diff was created and is smaller than threshold, False otherwise
        :rtype: bool
        """
        try:
            if self.config.diff_algorithm == "xdelta3":
                # Use xdelta3 if available
                result = subprocess.run(
                    ['xdelta3', '-e', '-s', str(old_file), str(new_file), str(diff_path)],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    # Check if diff is smaller than threshold
                    diff_size = diff_path.stat().st_size
                    new_size = new_file.stat().st_size
                    if diff_size < new_size * self.config.max_diff_size_ratio:
                        return True
                    else:
                        diff_path.unlink()  # Diff too large, remove it
                        return False
            elif self.config.diff_algorithm == "bsdiff":
                # Use bsdiff if available
                result = subprocess.run(
                    ['bsdiff', str(old_file), str(new_file), str(diff_path)],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    diff_size = diff_path.stat().st_size
                    new_size = new_file.stat().st_size
                    if diff_size < new_size * self.config.max_diff_size_ratio:
                        return True
                    else:
                        diff_path.unlink()
                        return False
            elif self.config.diff_algorithm == "rsync":
                # Use rsync for delta sync (simpler but less efficient)
                result = subprocess.run(
                    ['rsync', '--only-write-batch', str(diff_path), str(new_file), str(old_file)],
                    capture_output=True,
                    check=False
                )
                return result.returncode == 0
        except FileNotFoundError:
            print(f"Warning: {self.config.diff_algorithm} not found, skipping diff generation")
        
        return False

    async def _cleanup_old_files(self):
        """Remove old/unused files from mirror directories.
        
        Uses internal _autoclean and _clean_script flags set from clean config.
        
        Files in skip_clean set are never removed. Only files in directories
        specified by "clean" directives in mirror.list are considered for removal.
        """
        if not self.config._autoclean and not self.config._clean_script:
            print("Cleanup disabled (set clean to 'on' or 'auto' to enable)")
            return
        
        # Generate script first if requested (useful for debugging/testing)
        if self.config._clean_script:
            await self._generate_cleanup_script()
        
        # Perform automatic cleanup if requested
        if self.config._autoclean:
            print("\n" + "="*70)
            print("WARNING: Automatic cleanup is enabled!")
            print("="*70)
            print("This will PERMANENTLY DELETE files from your mirror that are")
            print("no longer in the repository. This action cannot be undone.")
            print("="*70)
            if self.config._clean_script:
                print("Note: clean.sh script has been generated for reference.")
                print("="*70)
            print("\nProceeding with automatic cleanup in 5 seconds...")
            print("(Press Ctrl+C to cancel)")
            print()
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("\nCleanup cancelled by user.")
                return
            
            await self._perform_automatic_cleanup()

    async def _generate_cleanup_script(self):
        """Generate cleanup script for manual review.
        
        Creates a shell script that lists files to be removed. Users can
        review the script before running it manually. Files in skip_clean
        are never included in the cleanup script.
        """
        script_path = Path(self.config.cleanscript)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        
        print("Generating cleanup script...")
        
        # Collect files to remove
        files_to_remove = []
        
        for clean_dir in self.clean_dirs:
            clean_path = Path(self.config.mirror_path) / clean_dir
            if not clean_path.exists():
                continue
            
            # Walk the directory tree
            def walk_directory():
                files = []
                for root, dirs, filenames in os.walk(clean_path):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        # Get relative path from mirror_path
                        try:
                            rel_path = file_path.relative_to(Path(self.config.mirror_path))
                            canonical = str(rel_path).replace('\\', '/')
                            
                            # Skip if file is in skip_clean
                            if canonical not in self.skip_clean:
                                files.append((file_path, canonical))
                        except ValueError:
                            # File is outside mirror_path, skip it
                            continue
                return files
            
            files_to_remove.extend(await asyncio.to_thread(walk_directory))
        
        if not files_to_remove:
            print("No files to clean up.")
            return
        
        # Generate the cleanup script
        def write_script():
            with open(script_path, 'w') as f:
                f.write("#!/bin/sh\n")
                f.write("# Cleanup script generated by apt-mirror\n")
                f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# Review this script before running!\n")
                f.write("# Run with: sh " + str(script_path) + "\n\n")
                f.write("set -e\n\n")
                f.write(f"# Removing {len(files_to_remove)} files...\n\n")
                
                for file_path, canonical in sorted(files_to_remove):
                    # Use relative path in script for clarity
                    f.write(f"rm -f \"{file_path}\"\n")
                
                f.write("\n# Cleanup complete\n")
            
            # Make script executable
            script_path.chmod(0o755)
        
        await asyncio.to_thread(write_script)
        
        print(f"Cleanup script generated: {script_path}")
        print(f"  {len(files_to_remove)} files will be removed")
        print(f"  Review the script before running: sh {script_path}")

    async def _perform_automatic_cleanup(self):
        """Perform automatic cleanup of old files.
        
        WARNING: This permanently deletes files. Use with extreme caution.
        Only files in directories specified by "clean" directives and not
        in skip_clean are removed. Files that exist in skel (just downloaded)
        are also protected.
        """
        print("Performing automatic cleanup...")
        removed_count = 0
        
        # Build set of files that should be kept:
        # 1. Files in skip_clean (current run)
        # 2. Files that exist in skel (just downloaded, may not be in skip_clean yet)
        # 3. Files in download queue
        files_to_keep = set(self.skip_clean)
        
        # Add files from download queue
        for task in self.download_queue:
            if task.canonical_path:
                files_to_keep.add(task.canonical_path)
            if task.hash_path:
                files_to_keep.add(task.hash_path)
        
        # Add files that exist in skel (they were just downloaded)
        def collect_skel_files():
            skel_files = set()
            skel_path = Path(self.config.skel_path)
            if skel_path.exists():
                for root, dirs, filenames in os.walk(skel_path):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        try:
                            rel_path = file_path.relative_to(skel_path)
                            canonical = str(rel_path).replace('\\', '/')
                            skel_files.add(canonical)
                        except ValueError:
                            continue
            return skel_files
        
        skel_files = await asyncio.to_thread(collect_skel_files)
        files_to_keep.update(skel_files)
        
        for clean_dir in self.clean_dirs:
            clean_path = Path(self.config.mirror_path) / clean_dir
            if not clean_path.exists():
                continue
            
            # Walk the directory tree and remove files
            def remove_files():
                count = 0
                for root, dirs, filenames in os.walk(clean_path):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        # Get relative path from mirror_path
                        try:
                            rel_path = file_path.relative_to(Path(self.config.mirror_path))
                            canonical = str(rel_path).replace('\\', '/')
                            
                            # Skip if file should be kept
                            if canonical not in files_to_keep:
                                try:
                                    file_path.unlink()
                                    count += 1
                                except OSError as e:
                                    print(f"Warning: Could not remove {file_path}: {e}")
                        except ValueError:
                            # File is outside mirror_path, skip it
                            continue
                return count
            
            removed_count += await asyncio.to_thread(remove_files)
        
        print(f"Automatic cleanup complete: {removed_count} files removed.")

    async def _run_postmirror(self):
        """Run postmirror script.
        
        Executes the postmirror script specified in configuration after
        all mirroring operations are complete. Checks if the script exists,
        is readable, and is executable before running. Falls back to
        executing with /bin/sh if the script is not directly executable.
        
        :raises subprocess.CalledProcessError: If script execution fails
        """
        # Store in variable to avoid multiple lookups (PR #196 improvement)
        script_path = self.config.postmirror_script
        
        # Check if script path is non-empty (PR #196 improvement)
        if not script_path or not script_path.strip():
            print("Warning: postmirror_script is empty, skipping postmirror execution.")
            return
        
        script = Path(script_path)
        
        # Check if script file exists (PR #196 improvement)
        if not script.exists():
            print(f"Warning: postmirror script not found: {script_path}, skipping.")
            return
        
        # Check if script is readable (needed for /bin/sh execution)
        # Note: Executable binaries don't need read permission, but scripts do
        if script.stat().st_mode & 0o111:  # Executable
            # Try to execute directly (works for binaries and executable scripts)
            subprocess.run([str(script)], check=False)
        else:
            # For non-executable scripts, check readability before using /bin/sh
            if os.access(script, os.R_OK):
                subprocess.run(['/bin/sh', str(script)], check=False)
            else:
                print(f"Warning: postmirror script is not readable: {script_path}, skipping.")


async def main():
    """Main entry point for apt-mirror.
    
    Parses command line arguments to get the configuration file path
    (defaults to /etc/apt/mirror.list), creates an AptMirror instance,
    and runs the complete mirroring process.
    """
    parser = argparse.ArgumentParser(description='Async apt-mirror')
    parser.add_argument('config_file', nargs='?', default='/etc/apt/mirror.list',
                       help='Path to mirror.list config file')
    args = parser.parse_args()

    mirror = AptMirror(args.config_file)
    await mirror.run()


if __name__ == '__main__':
    asyncio.run(main())

