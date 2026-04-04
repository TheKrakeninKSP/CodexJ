# CodexJ Help

CodexJ is organized around workspaces, journals, entries, and a Bin for deleted entries.

## Navigation overview

- Sidebar: Main navigation for workspaces, journals, Bin, appearance, account actions, imports, exports, and help.
- Workspace overview: Your top-level area for selecting a workspace and managing its journals and entry types.
- Journal view: Shows entries for the selected journal and provides import, create, search, and filter actions.
- Entry editor: Create or update entry content, media, links, webpage archives, and custom fields.
- Entry reader: Read a full entry with its metadata, media, music info, linked entries, and archived webpages.
- Bin: Review deleted entries, then restore or permanently purge them.

## Sidebar guide

- CodexJ version is shown at the top of the sidebar next to the app name.
- Your username and Sudo badge (when active) are displayed in the sidebar header.
- Create Workspace: Adds a new workspace via an inline input.
- Create Journal: Adds a new journal inside the selected workspace via an inline input.
- Bin: Opens deleted entries and shows a badge with the current count.
- Theme section: Switches between Light and Dark appearance themes.
- Sudo Mode: Enables or disables access to privileged actions after you re-enter your password.
- Export Data: Exports your encrypted data dump.
- Trim Media: Deletes unreferenced media files and unused entry type records.
- Shred Account: Exports your data and permanently deletes your account.
- Help: Opens this help page.
- Log Out: Ends your session and returns you to login.

## Workspaces

- Create as many workspaces as you need to organize your journals.
- Rename a workspace from the workspace overview.
- Delete a workspace (Sudo mode required) to soft-delete it along with all its journals and entries.
- Entry types are scoped per workspace and managed from the workspace overview.

## Journals

- Create journals inside a workspace. Each journal has a name and an optional description.
- Rename a journal or update its description.
- Delete a journal (Sudo mode required) to soft-delete it and all its entries.

## Journal view guide

- Import Entry: Imports one plaintext `.txt` entry and optional image, video, or audio files into the current journal.
- Create Entry: Opens the editor to create a new entry in the current journal.
- Search and filters: Narrow the visible entries in the current journal.
  - Name search: Filter entries by name substring.
  - Advanced search: Toggle the advanced panel for full-text search, entry type filter, date range (from/to), and pagination (limit and offset).
  - Clear filters: Reset all filters to show every entry in the journal.

## Entry editor guide

- Entry Type: Required. If you enter a new type, CodexJ creates it for the current workspace.
- Entry Name: Optional. If left empty, CodexJ falls back to a date-based title.
- Date Override: Optionally set a custom date for the entry.
- Timezone: Automatically captured from your browser for accurate date display.
- Custom fields: Add any number of extra key-value metadata pairs to keep with the entry.
- Show audio inline in entry reader: Plays audio directly inside the entry body instead of separate audio cards.
- Show webpages inline in entry reader: Displays archived webpage embeds inside the entry body instead of separate webpage cards.
- Archive Webpage: Enter a URL to archive a live webpage using the SingleFile engine. The archive runs in the background and its status updates automatically.
- Import Webpage Archive: Import a previously saved SingleFile HTML archive into the entry.
- Link Entry: Search for other entries by name and insert internal links. Searches the current journal first, then falls back to a global search.
- Media uploads: The editor accepts images (JPEG, PNG, GIF, WebP), videos (MP4, WebM, Ogg), and audio files (MP3, AAC, FLAC, WAV, M4A, OGG).

## Entry reader guide

- Header: Shows the entry title, date, entry type, and any custom metadata fields.
- Body: Displays the rich-text content in read-only mode.
- Entry links: Click an internal entry link to navigate directly to the linked entry. The back button uses your navigation history.
- Audio section: When audio is not set to display inline, audio files appear as separate cards. If music has been identified, the card shows cover art, title, artist, album, and year.
- Webpages section: When webpages are not set to display inline, archived pages appear as separate cards showing the page title and source URL. Cards link to both the live site and the archived snapshot. Pending or failed archives show their current status.
- Actions: Back, Edit, and Move to Bin (Sudo mode required).

## Media

- Upload images, videos, and audio files from the entry editor.
- Media files are reference-counted. A media file cannot be deleted while any entry still references it.
- Trim Media (sidebar action, Sudo mode required) scans for orphaned media files and unused entry types, then deletes them. It reports the number of items scanned and removed.

## Music identification

- When you upload an audio file, CodexJ automatically attempts to identify the song using AcoustID fingerprinting and MusicBrainz lookup.
- If a match is found, the entry reader shows the cover art, song title, artist, album, and release year.
- If automatic identification did not run or found no match, use the Identify button on the audio card in the entry reader to trigger a manual lookup.

## Webpage archiving

- Archive a live webpage by entering its URL in the entry editor. CodexJ uses the SingleFile engine with a headless browser to create a self-contained HTML snapshot.
- Alternatively, import a SingleFile HTML archive you saved from your browser.
- Archives run in the background. The editor polls for completion and shows the current status (pending, completed, or failed).
- Archived pages store the page title, source URL, and archive timestamp.
- CodexJ auto-detects Chrome, Edge, or Chromium on your system. Set the `CODEXJ_BROWSER_PATH` environment variable to override the browser path.

## Entry types

- Entry types are scoped to a workspace.
- Creating an entry with a new type name automatically registers that type.
- View and manage types from the workspace overview. Each type shows how many entries use it.
- Delete a type only when no entries in the workspace reference it.

## Bin

- Deleting an entry moves it to the Bin instead of deleting it permanently right away. The entry's original workspace and journal context are recorded.
- Restore to Original returns an entry to its previous workspace and journal when that location still exists.
- Restore lets you choose any workspace and journal you still own.
- Purge permanently and irreversibly deletes a single Bin entry.
- Bulk Purge: Select multiple entries and purge them all at once.
- Restore and purge require Sudo mode.

## Sudo mode

Sudo mode unlocks sensitive actions:

- Deleting workspaces, journals, and entries.
- Restoring or purging entries in the Bin.
- Exporting encrypted data.
- Trimming orphaned media and entry types.
- Running Shred Account.

Use the Sudo Mode control in the sidebar, re-enter your password, and confirm. You can disable Sudo mode from the same control when you are done.

## Data management

### Export

- Requires Sudo mode. You provide an encryption key (8–64 characters).
- Exports all your data (workspaces, journals, entries including binned entries, entry types, media files, and account info) into a single AES-encrypted dump file.
- The dump downloads automatically to your computer.
- Keep your encryption key safe — it is needed to restore the dump.

### Import

- Register a new account with an encrypted dump: create credentials and import all data in one step.
- Import into an existing account: merge dump data into your current workspaces and journals with conflict resolution.
- All internal IDs and media references are remapped during import.

### Plaintext entry import

- Import a `.txt` file with a structured format: date, journal name, entry type, entry name, optional custom metadata lines (`<<<key |-| value>>>`), and body text.
- Media references in the text (`<<>>filename`) are matched against files you upload alongside the `.txt` file.

## Authentication

- Register with a username (3–64 characters) and password (8–128 characters).
- On registration you receive a one-time hashkey (64-character hex string). Save it securely — it can be used to unlock your account if you forget your password.
- Log in with username and password, or use the hashkey via the Unlock route as an alternative.

## Keyboard shortcuts

- Alt+Enter: Toggle fullscreen.

## Basic usage flow

1. Create a workspace.
2. Create a journal in that workspace.
3. Open the journal and choose Create Entry.
4. Pick an entry type and write your content.
5. Add media, links, custom fields, or webpage archives as needed.
6. Save the entry.

## Tips

- Entry type is required, but entry name is optional.
- Manage entry types from the workspace overview.
- Use the SingleFile browser extension to save a webpage, then import the HTML archive into an entry.
- Archiving a webpage by URL runs in the background — you can save the entry immediately and the archive will update when ready.
- Uploaded audio files are automatically checked for music identification. Use the Identify button in the entry reader if the automatic lookup missed it.
- Keep your export encryption key safe — without it, the dump cannot be restored.
- Binned entries are included in data exports so nothing is lost.
- Long names for workspaces, journals, or entries will show a character limit message — this applies to the name field, not the entry body.
