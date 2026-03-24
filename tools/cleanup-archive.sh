#!/bin/bash

# Archive Cleanup Script
# Automatically removes old archived applications to prevent file bloat

set -euo pipefail

# Configuration
ARCHIVE_DIR="applications/archive"
RETENTION_MONTHS=6
DRY_RUN=${DRY_RUN:-false}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

# Calculate cutoff date
CUTOFF_DATE=$(date -d "$RETENTION_MONTHS months ago" +%Y-%m-%d 2>/dev/null || date -v-${RETENTION_MONTHS}m +%Y-%m-%d)
log "Removing applications older than $CUTOFF_DATE (retention: $RETENTION_MONTHS months)"

# Check if archive directory exists
if [[ ! -d "$ARCHIVE_DIR" ]]; then
    warn "Archive directory not found: $ARCHIVE_DIR"
    exit 0
fi

# Function to check if directory is older than cutoff date
is_directory_old() {
    local dir_path="$1"
    local dir_date

    # Try to get date from directory name (year)
    if [[ $(basename "$dir_path") =~ ^[0-9]{4}$ ]]; then
        dir_date="$(basename "$dir_path")-01-01"
    else
        # Fallback to modification time
        dir_date=$(date -r "$dir_path" +%Y-%m-%d 2>/dev/null || echo "1970-01-01")
    fi

    [[ "$dir_date" < "$CUTOFF_DATE" ]]
}

# Count and list old directories
old_dirs=()
total_size_kb=0

while IFS= read -r -d '' dir; do
    if is_directory_old "$dir"; then
        old_dirs+=("$dir")
        # Calculate directory size
        size_kb=$(du -sk "$dir" | cut -f1)
        total_size_kb=$((total_size_kb + size_kb))
    fi
done < <(find "$ARCHIVE_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

if [[ ${#old_dirs[@]} -eq 0 ]]; then
    log "No old archives found. Cleanup not needed."
    exit 0
fi

# Convert size to MB for display
total_size_mb=$((total_size_kb / 1024))

log "Found ${#old_dirs[@]} old archive directories (approx. ${total_size_mb}MB)"

# Show what will be deleted
if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY RUN - The following directories would be deleted:"
    for dir in "${old_dirs[@]}"; do
        echo "  - $(basename "$dir")"
    done
    exit 0
fi

# Confirmation prompt
echo
warn "This will permanently delete ${#old_dirs[@]} archived application directories."
warn "Total space to be freed: ~${total_size_mb}MB"
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Cleanup cancelled by user."
    exit 0
fi

# Delete old directories
deleted_count=0
for dir in "${old_dirs[@]}"; do
    log "Removing: $(basename "$dir")"
    if rm -rf "$dir"; then
        ((deleted_count++))
    else
        error "Failed to remove: $dir"
    fi
done

log "Cleanup completed. Deleted $deleted_count archive directories."
log "Space freed: ~${total_size_mb}MB"

log "Archive cleanup script completed successfully."
