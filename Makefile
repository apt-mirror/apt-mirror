VERSION := 0.6.3
DIST := apt-mirror.py CHANGELOG LICENSE Makefile mirror.list postmirror.sh README.md INSTALL.md FEATURES.md DEBIAN_DEPENDENCIES.md
BASE_PATH := /var/spool/apt-mirror
PREFIX ?= /usr/local
PYTHON := python3

all:
	@echo "apt-mirror Python version $(VERSION)"
	@echo "Checking dependencies..."
	@$(PYTHON) -c "import aiohttp" 2>/dev/null || (echo "ERROR: python3-aiohttp not found. Install with: sudo apt-get install python3-aiohttp" && exit 1)
	@which xdelta3 >/dev/null 2>&1 || (echo "ERROR: xdelta3 not found. Install with: sudo apt-get install xdelta3" && exit 1)
	@echo "All dependencies found."

dist: apt-mirror-$(VERSION).tar.xz

install:
	install -m 755 -D apt-mirror.py $(DESTDIR)$(PREFIX)/bin/apt-mirror
	if test ! -f $(DESTDIR)/etc/apt/mirror.list; then install -m 644 -D mirror.list $(DESTDIR)/etc/apt/mirror.list; fi
	mkdir -p $(DESTDIR)$(BASE_PATH)/mirror
	mkdir -p $(DESTDIR)$(BASE_PATH)/skel
	mkdir -p $(DESTDIR)$(BASE_PATH)/var
	mkdir -p $(DESTDIR)$(BASE_PATH)/diffs

%.tar.bz2: $(DIST)
	tar -c --exclude-vcs --transform="s@^@$*/@" $^ | bzip2 -cz9 > $@

%.tar.gz: $(DIST)
	tar -c --exclude-vcs --transform="s@^@$*/@" $^ | gzip -cn9 > $@

%.tar.xz: $(DIST)
	tar -c --exclude-vcs --transform="s@^@$*/@" $^ | xz -cz9 > $@

clean:
	rm -f *.tar.*
	rm -rf debian/apt-mirror
	rm -rf debian/.debhelper
	rm -f debian/files debian/substvars debian/*.debhelper.log
	rm -f debian/*.substvars debian/*.debhelper

# Build Debian package
deb: dist
	@echo "Building Debian package..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "ERROR: dpkg-buildpackage not found. Install with: sudo apt-get install devscripts build-essential"; \
		exit 1; \
	fi
	dpkg-buildpackage -us -uc -b

# Check dependencies for Debian package building
check-deps:
	@echo "Checking build dependencies..."
	@for pkg in python3 python3-aiohttp xdelta3 debhelper; do \
		dpkg -l | grep -q "^ii.*$$pkg" || (echo "Missing: $$pkg" && MISSING=1); \
	done; \
	if [ -n "$$MISSING" ]; then \
		echo "Install missing packages with: sudo apt-get install python3 python3-aiohttp xdelta3 debhelper"; \
		exit 1; \
	fi
	@echo "All build dependencies found."

.PHONY: all clean dist install deb check-deps
