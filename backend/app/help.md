# CodexJ Help

CodexJ is organized around workspaces, journals, entries, and a Bin for deleted entries.

## Navigation overview

- Sidebar: Main navigation for workspaces, journals, Bin, appearance, account actions, imports, exports, and help.
- Workspace overview: Your top-level area for selecting a workspace and managing its journals and entry types.
- Journal view: Shows entries for the selected journal and provides import and create actions.
- Entry editor: Create or update entry content, media, links, webpage archives, and custom fields.
- Entry reader: Read a full entry with its metadata, media, linked entries, and archived webpages.
- Bin: Review deleted entries, then restore or permanently purge them.

## Sidebar guide

- Create Workspace: Adds a new workspace.
- Create Journal: Adds a new journal inside the selected workspace.
- Bin: Opens deleted entries and shows how many are waiting.
- Theme section: Switches between available appearance themes.
- Sudo Mode: Enables or disables access to privileged actions after you re-enter your password.
- Export Data: Exports your encrypted data dump.
- Trim Media: Deletes unreferenced media files and unused entry type records.
- Shred Account: Exports your data and permanently deletes your account.
- Help: Opens this help page.
- Log Out: Ends your session and returns you to login.

## Journal view guide

- Import Entry: Imports one plaintext `.txt` entry and optional image, video, or audio files into the current journal.
- Create Entry: Opens the editor to create a new entry in the current journal.
- Search and filters: Narrow the visible entries in the current journal.

## Entry editor guide

- Entry Type: Required. If you enter a new type, CodexJ creates it for the current workspace.
- Entry Name: Optional. If left empty, CodexJ falls back to a date-based title.
- Custom fields: Add any extra key and value metadata you want to keep with the entry.
- Show audio inline in entry reader: Plays audio directly inside the entry reader instead of separate audio cards.
- Show webpages inline in entry reader: Displays archived webpage embeds inside the reader instead of separate webpage cards.
- Import Webpage Archive: Import a SingleFile HTML archive into the entry.
- Link Entry: Create internal links to other entries.
- Media uploads: The editor accepts images, videos, and audio files.

## Bin

- Deleting an entry moves it to the Bin instead of deleting it permanently right away.
- Restore to Original returns an entry to its previous workspace and journal when that location still exists.
- Restore lets you choose any workspace and journal you still own.
- Purge permanently deletes a Bin entry.
- Restore and purge require Sudo mode.

## Sudo mode

Sudo mode unlocks sensitive actions:

- Restoring or purging entries in the Bin.
- Deleting protected records.
- Exporting encrypted data.
- Trimming orphaned media.
- Running Shred Account.

Use the Sudo Mode control in the sidebar, re-enter your password, and confirm.

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
- Use SingleFile in your browser before importing webpage archives.
- Keep your export encryption key safe during export.
- Press Alt+Enter to toggle fullscreen.
