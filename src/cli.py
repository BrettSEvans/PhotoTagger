import argparse
import sys
from pathlib import Path
from src.db import Database
from src.crawler import PhotoCrawler
from src.ocr import OCREngine
from src.utils import setup_logging, format_size
import logging

logger = logging.getLogger(__name__)

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PhotoTagger: Find photos by jersey number"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Crawl photo directory")
    crawl_parser.add_argument("--photos", default="./photos", help="Photo directory path")
    crawl_parser.add_argument("--db", default="photo_catalog.db", help="Database path")

    # OCR command
    ocr_parser = subparsers.add_parser("ocr", help="Process OCR on photos")
    ocr_parser.add_argument("--db", default="photo_catalog.db", help="Database path")
    ocr_parser.add_argument("--photo-id", type=int, help="Optional: process specific photo ID")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search photos by jersey")
    search_parser.add_argument("jersey", help="Jersey number to search for")
    search_parser.add_argument("--db", default="photo_catalog.db", help="Database path")

    # Info command
    info_parser = subparsers.add_parser("info", help="Show database info")
    info_parser.add_argument("--db", default="photo_catalog.db", help="Database path")

    args = parser.parse_args()

    # Setup logging
    setup_logging(logging.INFO)

    if args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "ocr":
        cmd_ocr(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "info":
        cmd_info(args)
    else:
        parser.print_help()
        sys.exit(1)

def cmd_crawl(args):
    """Crawl command: scan photo directory."""
    db = Database(args.db)
    db.init_schema()

    crawler = PhotoCrawler(db)
    photo_dir = Path(args.photos)

    if not photo_dir.exists():
        print(f"❌ Photo directory not found: {photo_dir}")
        sys.exit(1)

    print(f"📁 Crawling: {photo_dir.absolute()}")
    results = crawler.crawl(str(photo_dir))

    print(f"✅ Found: {results['photos_found']} images")
    print(f"✅ Ingested: {results['photos_ingested']} new photos")
    print(f"⏭️  Skipped: {results['duplicates_skipped']} duplicates")

    if results['errors'] > 0:
        print(f"❌ Errors: {results['errors']}")

    db.close()

def cmd_ocr(args):
    """OCR command: process photos."""
    db = Database(args.db)
    db.init_schema()

    ocr_engine = OCREngine(db)

    if args.photo_id:
        print(f"🔍 Processing photo ID: {args.photo_id}")
        photo_ids = [args.photo_id]
    else:
        print(f"🔍 Processing all photos...")
        photos = db.get_all_photos()
        photo_ids = [p["id"] for p in photos]

    results = ocr_engine.process_batch(photo_ids)

    print(f"✅ Processed: {results['photos_processed']} photos")
    print(f"🏃 Jersey found: {results['jerseys_found']} photos")

    if results['errors'] > 0:
        print(f"❌ Errors: {results['errors']}")

    db.close()

def cmd_search(args):
    """Search command: find photos by jersey number."""
    db = Database(args.db)
    db.init_schema()

    jersey = args.jersey.strip()
    print(f"🔎 Searching for jersey: {jersey}")

    results = db.get_photo_by_jersey(jersey)

    if not results:
        print(f"❌ No photos found with jersey {jersey}")
        db.close()
        return

    print(f"✅ Found {len(results)} photo(s):\n")

    for result in results:
        print(f"  📸 {result['file_path']}")
        print(f"     Jersey: {result['jersey_number']}, Confidence: {result['confidence']:.2%}")
        print()

    db.close()

def cmd_info(args):
    """Info command: show database statistics."""
    db = Database(args.db)
    db.init_schema()

    photos = db.get_all_photos()

    print(f"📊 Database: {args.db}")
    print(f"📸 Total photos: {len(photos)}")

    if photos:
        total_size = sum(p["file_size"] for p in photos if p["file_size"])
        print(f"💾 Total size: {format_size(total_size)}")

    db.close()

if __name__ == "__main__":
    main()
