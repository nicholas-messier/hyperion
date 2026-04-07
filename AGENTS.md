# Project Rules

## Date & Time Verification

At the start of every session, verify the current date and time by running:

```sh
date
```

Confirm the output before proceeding with any tasks. This ensures all work, commits, and logs reference accurate timestamps.

## Directory Logic

- `/data` - Main data storage drive. Used for Media files
- `/data/plex_data` - main home of all tv show and moive files
- `/media/nmessier/NicksData/sda1` - External drive used for backup of media files
- `/home/nmessier/bin` - main directory for scripts and running devin
- `sdb` - data drive
- `sdc` - backup of data drive. backup done by cron job

## Rules

new scripts should be created in a subdirectory under /bin.
There needs to be a readme with detailed information in the sub directory
the readme in the main bin directory needs to be updated to link and include the new subdirectories
