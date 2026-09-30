import os
import csv
import json
import urllib.request
import re
import time
import pandas as pd
from internetarchive import search_items, get_item

# --- CONFIGURATION ---
GOOGLE_SHEET_CSV_URL = "https://google.com"
BASE_DOWNLOAD_DIR = "./visual_art_crs"
NEWLY_FOUND_EXCEL = "newly_found_crs.xlsx"
MAX_ITEMS_TO_CRAWL = 500  

# This version (4) has an Automated Cleanup and Quarantine Engine to your script.: When the crawler runs, it can scan your existing ./visual_art_crs directory. If it reads a local file path or parses an item ID that matches your updated non_art_domains list, it will halt, print a clear warning alert, and ask you for permission (y/n) to delete the specific file on the spot.
# Unified Master Blacklist across all non-art academic frameworks
NON_ART_DOMAINS = [
    'astrology', 'astronomy', 'occult', 'magic', 'horoscope', 'zodiac',
    'medicine', 'medical', 'law', 'legal', 'physics', 'chemistry', 'science',
    'economics', 'mathematics', 'geometry', 'stamp collecting', 'philately',
    'literature', 'poetry', 'manuscripts (historical)', 'theology', 'religion',
    'anarchism', 'anarchisme', 'syndicalism', 'syndicalisme', 'political', 'politique',
    'historian', 'historien', 'bakounine', 'bakunin', 'social sciences', 'sociology',
    'volcans', 'volcano', 'volcanoes', 'etna', 'lipari', 'geology', 'géologie', 
    'mineral', 'minerals', 'mineralogy', 'produits de l\'etna', 'dolomieu'
]
LITERARY_EXCLUSIONS = [
    "poèmes", "poems", "poésie", "poetry", "proses", "prose", "théâtre", "theatre", 
    "drame", "drama", "playwright", "tragedy", "comédie", "comedy", "roman", "novel", 
    "tome", "volume", "anthology", "literary", "skuespill", "dikte"
]

SCIENTIFIC_KEYWORDS = [
    "volcan", "volcano", "etna", "lava", "lave", "basalt", "basalte", "mineral", 
    "géologie", "geology", "rock", "fossil", "specimen", "cristaux", "crystals",
    "flora", "fauna", "botanical", "zoological", "specie", "espèces", "anatomy", 
    "médicale", "medical", "plantes", "plants", "insect", "oiseaux", "birds",
    "manuscript", "charter", "coin", "monnaie", "militaria", "weapon"
]

WEB_ENCYCLOPEDIA_KEYWORDS = [
    "wikipedia", "encyclopedia", "encyklopädie", "encyclopédie", "wikilinks",
    "inhaltsverzeichnis", "weblinks", "wiktionary", "wikimedia", "mediawiki",
    "retrieved from", "bdfutbol", "biography summary", "article text"
]

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

def run_local_folder_cleanup():
    """
    Scans the existing local folder on startup, flags any previously downloaded files 
    matching the non-art domain list, and prompts the user for interactive deletion.
    """
    if not os.path.exists(BASE_DOWNLOAD_DIR):
        return

    print(f"\n{'='*60}\nRunning Pre-Crawl Local Directory Scan & Cleanup\n{'='*60}")
    local_files = [f for f in os.listdir(BASE_DOWNLOAD_DIR) if f.endswith('.pdf')]
    flagged_count = 0

    for file_name in local_files:
        file_clean = file_name.lower()
        # Scan if the filename matches any restricted non-art terms
        if any(domain in file_clean for domain in NON_ART_DOMAINS):
            flagged_count += 1
            full_file_path = os.path.join(BASE_DOWNLOAD_DIR, file_name)
            print(f"\n⚠️  [NON-ART FILE DETECTED]: {file_name}")
            
            # Request explicit user terminal permission to delete
            choice = input("   Would you like to permanently delete this file? (y/n): ").strip().lower()
            if choice == 'y':
                try:
                    os.remove(full_file_path)
                    print(f"   🗑️  Successfully deleted: {file_name}")
                except Exception as err:
                    print(f"   [-] Failed to delete file: {err}")
            else:
                print("   [x] Kept file on disk (Skipped deletion).")

    if flagged_count == 0:
        print("[+] Directory clean! No mismatched non-art science files found on disk.")
    print(f"{'='*60}\n")

def load_sheet_exclusion_list(source_url):
    exclusion_identifiers = set()
    try:
        print("Fetching live exclusions from your Google Sheet tracking layer...")
        if source_url.startswith("http"):
            response = urllib.request.urlopen(source_url)
            lines = [line.decode('utf-8') for line in response.readlines()]
            reader = csv.DictReader(lines)
        else:
            with open(source_url, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
        reader.fieldnames = [f.strip() for f in reader.fieldnames] if reader.fieldnames else []
        LINK_COLUMN = "Archive Link"
        
        if LINK_COLUMN in reader.fieldnames:
            for row in reader:
                archive_link_cell = row.get(LINK_COLUMN, "")
                if archive_link_cell:
                    ia_id = extract_ia_identifier(archive_link_cell)
                    if ia_id:
                        exclusion_identifiers.add(ia_id)
                        
        print(f"Identified {len(exclusion_identifiers)} existing items to skip based on your sheet.")
        return exclusion_identifiers
    except Exception as e:
        print(f"Warning: Could not check spreadsheet exclusion logs: {e}")
        return set()

def parse_artist_chronology(title_string, subject_string):
    artist_chronology_regex = r"\b([a-zA-Z\s\-]{3,}),\s*(\d{4})\s*[\-\–\s]\s*(\d{4})\b"
    
    subject_match = re.search(artist_chronology_regex, subject_string)
    if subject_match:
        return subject_match.group(1).strip().title()
        
    title_match = re.search(artist_chronology_regex, title_string)
    if title_match:
        return title_match.group(1).strip().title()
        
    return None

def execute_blind_crawler_pipeline(crawler_query, exclusion_identifiers, master_inventory):
    noise_keywords = [
        'auction catalog', 'sale catalogue', 'collection of the late', 
        'annual report', 'selected works', 'great works', 'picture book', 'guidebook'
    ]
    
    processed_count = 0
    downloaded_count = 0
    newly_downloaded_records = []

    results = search_items(crawler_query)

    for result in results:
        if processed_count >= MAX_ITEMS_TO_CRAWL:
            print("[Crawler Status] Reached the execution run ceiling limit.")
            break
            
        item_id = result['identifier']
        processed_count += 1
        
        if item_id in exclusion_identifiers:
            continue

        try:
            item = get_item(item_id)
            metadata = item.metadata
            
            title = metadata.get('title', '')
            description = metadata.get('description', '').lower()
            subject = str(metadata.get('subject', ''))
            
            combined_text_block = (title + " " + description + " " + subject).lower()

            if any(domain in combined_text_block for domain in NON_ART_DOMAINS):
                continue

            if any(noise in title.lower() for noise in noise_keywords):
                continue
                
            has_cr_tag = any(indicator in subject.lower() for indicator in ["-- catalogs", "-- catalogue raisonne", "ragionato"])
            has_cr_title = any(indicator in title.lower() for indicator in ["raisonne", "ragionato", "werkverzeichnis", "complètes"])
            
            if not (has_cr_tag or has_cr_title):
                continue

            detected_artist = parse_artist_chronology(title, subject)
            if not detected_artist:
                cleaned_title = re.sub(r'(?i)catalogue raisonn[eé]|oeuvres complètes|werkverzeichnis|volume\s?\d+', '', title)
                cleaned_title = re.sub(r'[\d\-\(\)\[\]\.\,:\;\/\+]', ' ', cleaned_title)
                detected_artist = " ".join(cleaned_title.split()).title()
                
            if not detected_artist or len(detected_artist) < 3:
                detected_artist = "Unknown/Unspecified Artist"

            if detected_artist.startswith("A ") and len(detected_artist.split()) > 3:
                detected_artist = "Unknown/Unspecified Artist"

            pdf_files = [f.name for f in item.get_files() if f.name.endswith('.pdf')]
            if not pdf_files:
                continue

            sorted_pdfs = sorted(pdf_files, key=len)
            target_pdf_name = sorted_pdfs[0]
            
            safe_artist_string = re.sub(r'[\\/*?:"<>|]', "", detected_artist)
            standardized_filename = f"{safe_artist_string}_{target_pdf_name}"
            flat_destination_path = os.path.join(BASE_DOWNLOAD_DIR, standardized_filename)
            
            base_name, ext = os.path.splitext(standardized_filename)
            alternative_conflict_path = os.path.join(BASE_DOWNLOAD_DIR, f"{base_name}_{item_id}{ext}")

            if os.path.exists(flat_destination_path) or os.path.exists(alternative_conflict_path):
                print(f"  -> Skipped Local Duplicate: '{standardized_filename}' is already stored in your folder.")
                exclusion_identifiers.add(item_id)
                continue

            print(f"🎉 [TRUE CR LOCATED] Artist: {detected_artist} | Title: {title} ({item_id})")
            print(f"     Downloading file target: {target_pdf_name}...")
            
            item.download(files=[target_pdf_name], destdir=BASE_DOWNLOAD_DIR, verbose=False)
            nested_source_path = os.path.join(BASE_DOWNLOAD_DIR, item_id, target_pdf_name)
            
            if os.path.exists(nested_source_path):
                os.rename(nested_source_path, flat_destination_path)
                try:
                    os.rmdir(os.path.join(BASE_DOWNLOAD_DIR, item_id))
                except Exception:
                    pass
            
            record = {
                "artist_detected": detected_artist,
                "identifier": item_id,
                "title": title,
                "date": metadata.get('date', 'Unknown Date'),
                "archive_url": f"https://archive.org{item_id}",
                "local_file": flat_destination_path
            }
            master_inventory.append(record)
            
            newly_downloaded_records.append({
                "Artist Name": detected_artist,
                "Title": title,
                "Archive Link": f"https://archive.org{item_id}"
            })
            
            exclusion_identifiers.add(item_id)
            downloaded_count += 1
            
            time.sleep(1.5)  
            
        except Exception as e:
            print(f"    Error processing {item_id}: {e}")
            
    if downloaded_count > 0:
        print(f"  -> Query Complete. Downloaded: {downloaded_count} items.")
    return newly_downloaded_records

def main():
    # Trigger the interactive scanner before running exclusions or deployment networks
    run_local_folder_cleanup()
    
    exclusion_identifiers = load_sheet_exclusion_list(GOOGLE_SHEET_CSV_URL)

    if not os.path.exists(BASE_DOWNLOAD_DIR):
        os.makedirs(BASE_DOWNLOAD_DIR)

    master_inventory = []
    manifest_path = os.path.join(BASE_DOWNLOAD_DIR, "manifest.json")
    known_artists = set()
    
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for entry in old_data:
                    if "identifier" in entry:
                        exclusion_identifiers.add(entry["identifier"])
                    if "artist_detected" in entry and entry["artist_detected"] != "Unknown/Unspecified Artist":
                        known_artists.add(entry["artist_detected"])
                master_inventory.extend(old_data)
            print(f"Pre-loaded {len(old_data)} entries from local manifest. Found {len(known_artists)} unique artists.")
        except Exception as e:
            print(f"Note: Resetting fresh manifest tracking file: {e}")

    universal_search_queries = [
        '(subject:"catalogue raisonne" OR title:"catalogue raisonne") AND mediatype:texts', 
        '(subject:"oeuvres completes" OR title:"oeuvres completes") AND mediatype:texts', 
        '(subject:"werkverzeichnis" OR title:"werkverzeichnis") AND mediatype:texts',
        '(subject:"catalogo ragionato" OR title:"catalogo ragionato") AND mediatype:texts'
        '(subject:"werkverzeichnis" OR title:"werkverzeichnis") AND mediatype:texts', 
        '(subject:"oeuvrecatalogue" OR title:"oeuvrecatalogue") AND mediatype:texts', 
        '(subject:"complete works" OR title:"complete works") AND mediatype:texts',
        '(subject:"gesamtwerk" OR title:"gesamtwerk") AND mediatype:texts'
        '(subject:"sämtliche werke" OR title:"sämtliche werke") AND mediatype:texts', 
        '(subject:"catalogo generale" OR title:"catalogo generale") AND mediatype:texts', 
        '(subject:"werkverzeichnis" OR title:"werkverzeichnis") AND mediatype:texts',
        '(subject:"opera completa" OR title:"opera completa") AND mediatype:texts'
        '(subject:"catálogo razonado" OR title:"catálogo razonado") AND mediatype:texts', 
        '(subject:"obra completa" OR title:"obra completa") AND mediatype:texts', 
        '(subject:"catálogo general" OR title:"catálogo general") AND mediatype:texts',
        '(subject:"oeuvre-catalogus" OR title:"oeuvre-catalogus") AND mediatype:texts'
        '(subject:"complete catalog" OR title:"complete catalog") AND mediatype:texts', 
        '(subject:"critical catalogue" OR title:"critical catalogue") AND mediatype:texts', 
        '(subject:"painting" OR title:"painting") AND mediatype:texts',
        '(subject:"sculpture" OR title:"sculpture") AND mediatype:texts'
        '(subject:"etching" OR title:"etching") AND mediatype:texts', 
        '(subject:"engraving" OR title:"engraving") AND mediatype:texts', 
        '(subject:"drawing" OR title:"drawing") AND mediatype:texts',
        '(subject:"print" OR title:"print") AND mediatype:texts'
        '(subject:"oeuvre" OR title:"oeuvre") AND mediatype:texts', 
        '(subject:"monograph" OR title:"monograph") AND mediatype:texts', 
        '(subject:"artist" OR title:"artist") AND mediatype:texts',
    ]

    for artist in sorted(list(known_artists)):
        clean_search_name = re.sub(r'\b(Sanzio|Sarto|Da|Van|De)\b', '', artist).strip()
        if len(clean_search_name) > 3:
            expanded_query = f'"{clean_search_name}" AND ("catalogue raisonne" OR "werkverzeichnis" OR "catalogo ragionato") AND mediatype:texts'
            universal_search_queries.append(expanded_query)

    print(f"[*] Generated {len(universal_search_queries)} search vectors for this crawl run loop phase.")

    all_new_items = []
    
    for current_query in universal_search_queries:
        print(f"\n[*] Deploying Net: {current_query[:90]}...")
        session_downloads = execute_blind_crawler_pipeline(current_query, exclusion_identifiers, master_inventory)
        all_new_items.extend(session_downloads)

    if all_new_items:
        print(f"\n[*] Processing session data... Creating Excel manifest ledger layout: {NEWLY_FOUND_EXCEL}")
        try:
            df_new = pd.DataFrame(all_new_items)
            df_new = df_new[["Artist Name", "Title", "Archive Link"]]
            df_new.to_excel(NEWLY_FOUND_EXCEL, index=False)
            print(f"🎉 SUCCESS: Excel spreadsheet file containing {len(all_new_items)} new records generated at '{NEWLY_FOUND_EXCEL}'.")
        except Exception as sheet_err:
            print(f"[-] Excel file export task encountered an error: {sheet_err}")
    else:
        print("\n[-] No new unique Catalogues Raisonnés downloaded in this specific crawl run session. Excel generation skipped.")

    if master_inventory:
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(master_inventory, f, indent=4, ensure_ascii=False)
            print(f"Global historical manifest ledger updated. Total tracked: {len(master_inventory)} items.")
        except Exception as e:
            print(f"Error saving tracking manifest file: {e}")

if __name__ == "__main__":
    main()