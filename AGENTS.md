# Project Rules

## Date & Time Verification

At the start of every session, verify the current date and time by running:

```sh
date
```

Confirm the output before proceeding with any tasks. This ensures all work, commits, and logs reference accurate timestamps.

## Directory Logic

Server-specific paths and drive mappings are defined in `config.env` at the repo root.
See `config.env.example` for the full list of configurable values.

Key config variables:
- `MEDIA_SOURCE` - Main media library path (Plex/ErsatzTV content)
- `DATA_DRIVE_PATH` - Primary data drive mount
- `ARCHIVE_DRIVE_PATH` - Archive/backup drive mount
- `EXTERNAL_DRIVE_MEDIA` - External drive media path
- `BIN_DIR` - This scripts repository

## Rules

New scripts should be created in a subdirectory under the repo root.
There needs to be a README with detailed information in the subdirectory.
The README in the main directory needs to be updated to link and include the new subdirectories.

All server-specific paths must go in `config.env` (git-ignored), not hardcoded in scripts.
No IP addresses, drive serial numbers, or personal paths in files committed to git.

## Screenshots

The local display can be captured for visual troubleshooting (e.g., conky panels) even when working over SSH:

```sh
DISPLAY=:0 gnome-screenshot -f /tmp/screenshot.png
```

Then use the `read` tool on the resulting image to view it. This is useful for verifying conky layout, styling, or visual bugs.
