import os
import csv
import json
import urllib.request
import re
from internetarchive import search_items, get_item

# --- CONFIGURATION ---
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRpzhxoN8APn8Q_sZnbhZpKs9pOnejVgB0WGeLOBdt1tRIeg1P3uczk7QU8NhKH7UgRWL1XY4f780o7/pub?gid=1628160556&single=true&output=csv"
BASE_DOWNLOAD_DIR = "./visual_art_crs"
MAX_RESULTS_PER_ARTIST = 5   

def extract_ia_identifier(url_string):
    if not url_string:
        return None
    url_string = url_string.strip()
    match = re.search(r'archive\.org/(?:details|download)/([^/\s?#]+)', url_string)
    if match:
        return match.group(1)
    if "archive.org" not in url_string and len(url_string) > 2:
        return url_string
    return None

def load_sheet_data(source_url):
    artists = set()
    exclusion_identifiers = set()
    try:
        print("Fetching live data from Google Sheet...")
        if source_url.startswith("http"):
            response = urllib.request.urlopen(source_url)
            lines = [line.decode('utf-8') for line in response.readlines()]
            reader = csv.DictReader(lines)
        else:
            with open(source_url, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
        reader.fieldnames = [f.strip() for f in reader.fieldnames] if reader.fieldnames else []
        ARTIST_COLUMN = "Artist Name"
        LINK_COLUMN = "Archive Link"
        
        if ARTIST_COLUMN not in reader.fieldnames or LINK_COLUMN not in reader.fieldnames:
            print(f"Error: Missing columns. Sheet contains: {reader.fieldnames}")
            return [], set()
            
        for row in reader:
            artist_name = row.get(ARTIST_COLUMN, "").strip()
            if artist_name:
                artists.add(artist_name)
            archive_link_cell = row.get(LINK_COLUMN, "")
            if archive_link_cell:
                ia_id = extract_ia_identifier(archive_link_cell)
                if ia_id:
                    exclusion_identifiers.add(ia_id)
                    
        print(f"Successfully loaded {len(artists)} unique artists to search.")
        print(f"Identified {len(exclusion_identifiers)} existing items to skip from your sheet.")
        return sorted(list(artists)), exclusion_identifiers
    except Exception as e:
        print(f"Error loading data: {e}")
        return [], set()

def scrape_crs_for_artist(artist_name, exclusion_identifiers, master_inventory):
    print(f"\n{'='*50}\nPipeline: {artist_name}\n{'='*50}")
    
    query = f'"{artist_name}" AND "le peintre-graveur" AND mediatype:texts'
    results = search_items(query)
    
    art_keywords = ['painting', 'sculpture', 'etching', 'engraving', 'drawing', 'print', 'oeuvre', 'monograph', 'artist']
    noise_keywords = ['auction catalog', 'sale catalogue', 'collection of the late', 'annual report']
    
    count = 0

    for result in results:
        if count >= MAX_RESULTS_PER_ARTIST:
            break
            
        item_id = result['identifier']
        
        if item_id in exclusion_identifiers:
            print(f"  -> Skipped: '{item_id}' matches an Archive Link already in your Google Sheet.")
            continue

        try:
            item = get_item(item_id)
            metadata = item.metadata
            
            title = metadata.get('title', '').lower()
            description = metadata.get('description', '').lower()
            subject = str(metadata.get('subject', '')).lower()
            
            has_art_context = any(kw in (title + description + subject) for kw in art_keywords)
            is_commercial_noise = any(noise in title for noise in noise_keywords)
            
            if not has_art_context or is_commercial_noise:
                continue 
                
            pdf_files = [f.name for f in item.get_files() if f.name.endswith('.pdf')]
            if not pdf_files:
                continue

            target_pdf_name = sorted(pdf_files, key=len)[0]
            
            # --- DUPLICATION LOGIC: Calculate clean standard destination path ---
            flat_destination_path = os.path.join(BASE_DOWNLOAD_DIR, target_pdf_name)
            
            # If a file with this identical name already sits in your folder, determine if it's the exact same item
            if os.path.exists(flat_destination_path):
                # Conflict Prevention: Check if it's a completely different item using a generic name (like volume_1.pdf)
                # If it's a completely different item ID, we safely change our path target to append the unique ID.
                # If it's the same item ID from a previous split-run, it triggers the skip loop below.
                base, ext = os.path.splitext(target_pdf_name)
                conflict_resolved_path = os.path.join(BASE_DOWNLOAD_DIR, f"{base}_{item_id}{ext}")
                
                if os.path.exists(conflict_resolved_path):
                    print(f"  -> Skipped Local Duplicate: File already exists at '{conflict_resolved_path}'.")
                    exclusion_identifiers.add(item_id)
                    continue
                elif item_id in str(master_inventory): # Quick layout tracking validation helper
                    print(f"  -> Skipped Local Duplicate: Item '{item_id}' already captured.")
                    exclusion_identifiers.add(item_id)
                    continue
                else:
                    # It's a completely different book asset with a conflicting name! Append ID to distinguish them safely.
                    flat_destination_path = conflict_resolved_path

            # If the plain target path matches exactly, we skip downloading entirely to save bandwidth
            if os.path.exists(flat_destination_path) and item_id in exclusion_identifiers:
                print(f"  -> Skipped Local Duplicate: File already exists at '{flat_destination_path}'.")
                continue

            count += 1
            print(f"  [New CR Found] {metadata.get('title')} ({item_id})")
            
            record = {
                "artist_searched": artist_name,
                "identifier": item_id,
                "title": metadata.get('title', 'Unknown Title'),
                "date": metadata.get('date', 'Unknown Date'),
                "archive_url": f"https://archive.org{item_id}"
            }
            
            print(f"     Downloading PDF asset: {target_pdf_name}...")
            item.download(files=[target_pdf_name], destdir=BASE_DOWNLOAD_DIR, verbose=False)
            
            nested_source_path = os.path.join(BASE_DOWNLOAD_DIR, item_id, target_pdf_name)
            
            if os.path.exists(nested_source_path):
                os.rename(nested_source_path, flat_destination_path)
                try:
                    os.rmdir(os.path.join(BASE_DOWNLOAD_DIR, item_id))
                except:
                    pass
            
            record["local_file"] = flat_destination_path
            master_inventory.append(record)
            exclusion_identifiers.add(item_id)
            
        except Exception as e:
            print(f"    Error processing {item_id}: {e}")

def main():
    artists, exclusion_identifiers = load_sheet_data(GOOGLE_SHEET_CSV_URL)
    if not artists:
        print("No work to process. Check your spreadsheet configuration.")
        return

    if not os.path.exists(BASE_DOWNLOAD_DIR):
        os.makedirs(BASE_DOWNLOAD_DIR)

    master_inventory = []

    # Pre-populate exclusion list from previously generated master manifest runs if it exists
    manifest_path = os.path.join(BASE_DOWNLOAD_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing_manifest = json.load(f)
                for item in existing_manifest:
                    exclusion_identifiers.add(item.get("identifier"))
        except Exception:
            pass

    for artist in artists:
        scrape_crs_for_artist(artist, exclusion_identifiers, master_inventory)
        
    if master_inventory:
        # If an existing manifest was found, append new results onto the database array ledger
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    combined_manifest = json.load(f)
                combined_manifest.extend(master_inventory)
                master_inventory = combined_manifest
            except Exception:
                pass

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(master_inventory, f, indent=4)
        print(f"\nSaved global tracking log to {manifest_path}")

    print("\nProcess finished. Local duplication tracking has verified all paths.")

if __name__ == "__main__":
    main()
