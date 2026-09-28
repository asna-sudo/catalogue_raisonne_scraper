## Internet Archive Catalogues Raisonnés Scraper

An automated Python pipeline designed for art historians and researchers to systematically source, filter, and download digital *catalogues raisonnés* (CRs) and fine-art monographs from the **Internet Archive (archive.org)**. 

The script uses a live **Google Sheet as a dynamic configuration controller**, allowing users to manage target artists and cataloged links remotely without modifying code.

### 🚀 Key Features

* **Google Sheets Integration:** Dynamically fetches target artist names and tracks previously cataloged assets directly from a published CSV endpoint.
* **Smart Content Filtering:** Uses art-historical metadata filtering to isolate critical reference books (e.g., *le peintre-graveur*, monographs, etchings) while explicitly ignoring commercial noise like auction and sales catalogs.
* **Robust Duplicate & Conflict Prevention:** 
  * Prevents redundant downloads by cross-referencing a local `manifest.json` and your remote Google Sheet tracking links.
  * Auto-resolves filename collisions (e.g., generic file titles like `volume_1.pdf`) by appending unique Internet Archive identifiers to prevent data overwriting.
* **Directory Flattening:** Automatically cleans up the messy nested folders native to the `internetarchive` download API, organizing all downloaded PDFs into a single, flat local directory.

### 📋 Prerequisites & Setup

1. **Install Dependencies:**
   ```bash
   pip install internetarchive
   ```
2. **Configure Spreadsheet:** Publish your tracking Google Sheet to the web as a `.csv` and replace the `GOOGLE_SHEET_CSV_URL` variable in the script. Ensure your sheet contains the headers `Artist Name` and `Archive Link`.
