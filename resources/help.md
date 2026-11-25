# CodexJ Help

CodexJ is organized around workspaces, journals, entries, and a Bin for deleted entries.

## Navigation overview

- Sidebar: Workspaces and journals, the Bin, Theme and Editor settings, account actions, and Help. On narrow screens it becomes a drawer opened from the menu button at the top.
- Workspace overview: Shows the journals in the selected workspace.
- Journal view: Lists the entries in a journal, with search, filters, and Create Entry.
- Entry editor: Write an entry and add media, songs, webpage archives, and links to other entries.
- Entry reader: Read an entry with its media, music info, linked entries, archived webpages, and version history.
- Bin: Restore deleted entries or delete them permanently.

## Sidebar guide

- The CodexJ version is shown next to the app name, and your username (plus a Sudo badge when active) below it.
- ✦ Create Workspace / ✦ Create Journal: Add one via an inline input (Enter to create, Esc to cancel). New journals go into the selected workspace.
- In Sudo mode, buttons appear next to each name: ✎ rename, ↗ move a journal to another workspace, ✖ delete.
- Bin: Opens deleted entries; the badge shows how many there are.
- Theme: Choose Light, Solarized Dark, or Midnight. Your choice is saved to your account.
- Editor: Set the content width (Narrow, Medium, Wide, Full) and turn Sticky Toolbar on or off. Saved in this browser.
- Sudo Mode: Turn privileged actions on or off (turning on asks for your password).
- Export Data, Trim Media, Shred Account: Only shown while Sudo mode is on.
- Help: Opens this page.
- Log Out: Ends your session.

## Workspaces

- Create as many workspaces as you need to organize your journals.
- Rename or delete a workspace from the sidebar (Sudo mode required). Deleting a workspace permanently deletes its journals, their entries, and their media. They do not go to the Bin, so export first if in doubt.

## Journals

- Create journals inside a workspace from the sidebar.
- In Sudo mode, the workspace overview shows "+ Description" / "Edit description" on each journal card.
- Rename, move (to another workspace), or delete a journal from the sidebar (Sudo mode required). Deleting a journal permanently deletes its entries and their media (they do not go to the Bin).

## Journal view guide

- ✦ Create Entry: Creates a new blank entry in this journal right away and opens it in the editor.
- Search by Entry Name: Filters entries as you type.
- Advanced Search: Opens extra filters - Full-Text Query (searches entry text), a tag filter, From Date / To Date, and Limit / Offset for paging. Click Search to apply them.
- Clear: Resets all filters.
- Entries are listed newest first, with their name (or date) and tags.

## Entry editor guide

### Header

- Tags: Type a tag and press Enter or comma to add it. A dropdown suggests existing tags as you type - use the arrow keys and Enter (or click) to pick one, Esc to close it. Backspace in an empty input removes the last tag; click × on a tag to remove it. New tags are created when you save. Tags are optional.
- Theme: Three round buttons - BG (background colour), Text (text colour), and Audio (background track). Click an empty button to set it (a colour picker, or an audio file upload for Audio). Click a set button to remove it. BG and Text colours preview live in the editor and apply in the reader.
- Preferences: Per-entry options, grouped into sections:
  - Audio - Show audio inline in entry reader (play audio inside the text instead of as cards below it); Show rich metadata for audio (show cover art, title, artist, album, and year on audio cards - turned on automatically when you add audio); Hide background audio track from entry body (see Background audio).
  - Webpages - Show webpages inline in entry reader (show archives inside the text instead of as cards below it).
  - Entry - Track versions of this entry (keep a version history, see Entry reader); Set custom creation date (pick a date and time for the entry).

### Name and body

- Name: The title field at the top of the editor card. Leave it empty to name the entry after its date. Press Enter to jump into the body.
- Toolbar: Bold, Italic, Underline, Strikethrough, H1-H3, blockquote, code block, ordered and bullet lists, then 🖼︎ Insert media, 🌐︎ Insert webpage, ♫ Tag a song, § Link entry, and ✕ Clear formatting.
- ← Back leaves without saving; Save Entry saves and opens the entry in the reader.

### Links

- Pasting rich text keeps its links.
- Pasting a URL makes it a link; select some text first and paste a URL to link that text.
- Typing a URL followed by a space turns it into a link.
- ✕ Clear formatting removes links and all other formatting (including headings and lists) from the selection.

### Linking to other entries

- Click § (Link entry) and search your entries by name or text.
- Select text first to turn it into an internal entry link, or insert an entry title directly with Insert Link.
- Results stay in the current journal when possible: if nothing in this journal matches, your other entries are shown instead.

### Media

- Click 🖼︎ (Insert media) or drag and drop files into the editor.
- Supported: images (JPEG, PNG, GIF, WebP), videos (MP4, WebM, Ogg), audio (MP3, AAC, FLAC, WAV, M4A, ALAC, Ogg, Opus), and PDFs.

### Background audio

- An entry can have one background track. If it has identified cover art, the reader uses it as a blurred backdrop.
- The first audio you add (upload or tagged song) becomes the background only if the entry doesn't have one yet. Adding more audio never replaces it.
- To change it, click "Set as background" on any audio block in the editor (it then shows "♪ Background ✓"; click again to unset). Or use Theme > Audio to upload a new track as the background.
- With "Hide background audio track from entry body" on, the track is left out of the entry text and plays automatically on a loop in the reader. Uploading through Theme > Audio turns this on for you.

## Entry reader guide

- Header: Entry name (or date), date, and tags.
- Body: The entry text, read-only. Click an internal entry link to open that entry.
- Audio: Unless shown inline, audio appears as cards below the text. With "Show rich metadata for audio" on, identified songs show cover art, title, artist, album, and year. Songs still downloading or failed show their status.
- Webpages: Unless shown inline, archives appear as cards with the page title and source, plus Open live site and View archived buttons. Pending or failed archives show their status.
- Version History: When version tracking is on, the clock button next to the title opens a list of saved versions. Expand one to see the words and files added or removed since the previous version. A version is recorded each time you save.
- Actions: ← Back (to the journal), Edit, ↗ Move (to another journal, Sudo mode required), and Move to Bin.

## Music identification

- When you upload an audio file, CodexJ tries to identify the song with AcoustID fingerprinting and a MusicBrainz lookup, in the background.
- If a match is found, the reader shows cover art, title, artist, album, and year (with "Show rich metadata for audio" on).

## Tagging a song without audio

- Click ♫ (Tag a song) in the editor toolbar to attach a song when you don't have the audio file.
- Search by song title, optionally with the artist (much better results). Results come from MusicBrainz.
- Picking a result downloads the audio of the top YouTube match in the background and attaches it like an upload, with title, artist, album, year, and cover art from MusicBrainz.
- Not listed? Use "Download ... as typed" to download using your title and artist as typed; that audio is then identified automatically like an upload.
- A placeholder card shows until the download finishes (usually 10-20 seconds). You can keep writing and save in the meantime. If it fails, the card shows why - delete the block and try again.
- The top YouTube match is used as-is, so occasionally it may be a live or music-video version. Results longer than 20 minutes are skipped.
- Needs ffmpeg and deno. The desktop app and server builds include them (Windows and Linux); otherwise install them on the machine running CodexJ.

## Webpage archiving

- Click 🌐︎ (Insert webpage) in the editor toolbar.
- Enter a URL and click Add Link to archive the live page with SingleFile. It runs in the background; you can save right away and the archive updates when ready.
- Or click Import Saved HTML to add a page you saved with the SingleFile browser extension.
- CodexJ auto-detects Chrome, Edge, or Chromium. Set the `CODEXJ_BROWSER_PATH` environment variable to use a different browser.

## Media storage

- Media files stay on disk while any entry references them.
- Removing a media block from an entry does not delete the file. Trim Media (sidebar, Sudo mode required) deletes media no entry references any more and reports how many were removed.

## Bin

- Move to Bin doesn't delete an entry permanently; its original workspace and journal are remembered.
- Restore to Original: Puts the entry back where it was, if that journal still exists.
- Restore: Pick any workspace, then a journal inside it, and click Restore Entry.
- Delete Permanently: Irreversibly deletes one entry (Sudo mode required).
- Purge Selected: In Sudo mode, tick entries (or Select all) and delete them all at once.
- Moving to and restoring from the Bin don't need Sudo mode, because both are reversible.

## Sudo mode

Sudo mode unlocks sensitive actions:

- Renaming, moving, and deleting workspaces and journals; editing journal descriptions.
- Moving entries between journals.
- Permanently deleting entries from the Bin.
- Export Data, Trim Media, and Shred Account.

Click Sudo Mode in the sidebar, re-enter your password, and click Enable. Click it again to turn it off.

## Data management

### Export

- Export Data (Sudo mode required) downloads all your data - workspaces, journals, entries (including binned ones), tags, and media files - as a single encrypted dump file.
- The dump is encrypted with a key derived from your hashkey. No separate passphrase is needed, but you need the hashkey to restore it.

### Restoring a dump

- On the login screen, open the Import tab, enter the hashkey and choose the dump file, then click Import & Create Account. This recreates the account from the dump.

### Shred Account

- Exports and downloads your data, then permanently deletes your account (Sudo mode required).

## Accounts and sign-in

- Register with a username (3-64 characters) and password (8-128 characters).
- After registering you are shown a one-time hashkey (64 hex characters). Save it securely - it unlocks your account if you forget your password and decrypts your exports.
- Sign in with the Password tab, or with the Hashkey tab (username plus hashkey).

## Keyboard shortcuts

- Alt+Enter: Toggle fullscreen.
- In the editor: Enter in the Name field jumps to the body. In the Tags field, Enter or comma adds a tag, arrow keys move through suggestions, Esc closes them.

## Basic usage flow

1. Create a workspace.
2. Create a journal in that workspace.
3. Open the journal and click ✦ Create Entry.
4. Write your content, and optionally add a name and tags.
5. Add media, songs, webpage archives, or links as needed.
6. Click Save Entry.

## Tips

- Keep your hashkey safe - it is your password backup and the key to your data exports.
- Binned entries are included in exports, so nothing is lost.
- Names have length limits (workspaces 128 characters; journals, entries, and tags 256; journal descriptions 512). The entry body has no limit.
