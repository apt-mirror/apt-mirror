#!/bin/sh -e

## Post-mirror script for apt-mirror
##
## This script runs AFTER all mirroring operations complete.
## Enable it by setting in mirror.list:
##   set run_postmirror 1
##
## Common use cases:
## - Sync additional files (installer files, etc.)
## - Send notifications (email, webhooks)
## - Run cleanup operations
## - Trigger other processes
## - Update indexes or metadata

## Example: Sync installer files for Ubuntu (uncomment and adjust as needed)
## Note: rsync must be installed for these examples to work
##
# DIST="noble"
# BASE="/var/spool/apt-mirror/mirror/archive.ubuntu.com/ubuntu/dists/${DIST}/main"
# 
# # Sync debian-installer files
# rsync --recursive --times --links --hard-links --delete --delete-after \
#   rsync://archive.ubuntu.com/ubuntu/dists/${DIST}/main/debian-installer \
#   "${BASE}/"
# 
# # Sync installer files for amd64
# rsync --recursive --times --links --hard-links --delete --delete-after \
#   rsync://archive.ubuntu.com/ubuntu/dists/${DIST}/main/installer-amd64 \
#   "${BASE}/"

## Example: Send email notification (requires mailx or similar)
## Uncomment and adjust as needed:
##
# echo "apt-mirror completed successfully at $(date)" | \
#   mail -s "apt-mirror update complete" admin@example.com

## Example: Run cleanup script automatically
## Uncomment if you have a cleanup script:
##
# /var/spool/apt-mirror/var/clean.sh

## Example: Trigger webhook notification
## Uncomment and adjust URL:
##
# curl -X POST https://example.com/webhook/apt-mirror-complete \
#   -H "Content-Type: application/json" \
#   -d '{"status":"success","timestamp":"'$(date -Iseconds)'"}'
