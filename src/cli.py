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
    ocr_parser.add_argument("--parallel", action="store_true", help="Use parallel processing")
    ocr_parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search photos by jersey")
    search_parser.add_argument("jersey", help="Jersey number to search for")
    search_parser.add_argument("--db", default="photo_catalog.db", help="Database path")

    # Info command
    info_parser = subparsers.add_parser("info", help="Show database info")
    info_parser.add_argument("--db", default="photo_catalog.db", help="Database path")

    # Roster command
    roster_parser = subparsers.add_parser("roster", help="Manage rosters")
    roster_subparsers = roster_parser.add_subparsers(dest="roster_command")

    roster_load = roster_subparsers.add_parser("load", help="Load roster file")
    roster_load.add_argument("file", help="Roster JSON file path")
    roster_load.add_argument("--db", default="photo_catalog.db")

    roster_list = roster_subparsers.add_parser("list", help="List loaded rosters")
    roster_list.add_argument("--db", default="photo_catalog.db")

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
    elif args.command == "roster":
        cmd_roster(args)
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
        results = ocr_engine.process_batch(photo_ids)
    else:
        photos = db.photos.get_all_photos()
        photo_ids = [p["id"] for p in photos]

        if args.parallel:
            print(f"🔍 Processing {len(photo_ids)} photos in parallel...")
            results = ocr_engine.process_batch_parallel(photo_ids=photo_ids, max_workers=args.workers)
        else:
            print(f"🔍 Processing {len(photo_ids)} photos...")
            results = ocr_engine.process_batch(photo_ids)

    print(f"✅ Processed: {results['photos_processed']} photos")
    print(f"🏃 Jersey found: {results['jerseys_found']} photos")

    if "faces_detected" in results:
        print(f"👤 Faces detected: {results['faces_detected']}")

    if "elapsed_time" in results:
        print(f"⏱️  Time: {results['elapsed_time']:.1f}s")

    if results.get('errors', 0) > 0:
        print(f"❌ Errors: {results['errors']}")

    db.close()

def cmd_search(args):
    """Search command: find photos by jersey number."""
    db = Database(args.db)
    db.init_schema()

    jersey = args.jersey.strip()
    print(f"🔎 Searching for jersey: {jersey}")

    results = db.photos.get_photo_by_jersey(jersey)

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

    photos = db.photos.get_all_photos()

    print(f"📊 Database: {args.db}")
    print(f"📸 Total photos: {len(photos)}")

    if photos:
        total_size = sum(p.get("file_size") or 0 for p in photos)
        print(f"💾 Total size: {format_size(total_size)}")

    db.close()

def cmd_roster(args):
    """Roster management commands."""
    from src.roster import RosterManager

    if args.roster_command == "load":
        manager = RosterManager()
        try:
            manager.load_roster(args.file)
            print(f"✅ Loaded roster: {args.file}")

            # Save to database
            db = Database(args.db)
            db.init_schema()
            for team_name in manager.get_all_teams():
                for year in manager.get_team_years(team_name):
                    jerseys = manager.rosters[team_name][year]
                    for jersey, player_name in jerseys.items():
                        db.add_roster_entry(team_name, year, jersey, player_name)
            db.close()
            print(f"✅ Saved roster to database")
        except Exception as e:
            print(f"❌ Error loading roster: {e}")

    elif args.roster_command == "list":
        db = Database(args.db)
        db.init_schema()

        # List rosters from database
        cursor = db.conn.cursor()
        cursor.execute("SELECT DISTINCT team_name, team_year FROM rosters")
        rosters = cursor.fetchall()

        if rosters:
            print("📋 Loaded rosters:")
            for team_name, year in rosters:
                cursor.execute("SELECT COUNT(*) FROM rosters WHERE team_name = ? AND team_year = ?",
                             (team_name, year))
                count = cursor.fetchone()[0]
                print(f"  {team_name} ({year}): {count} players")
        else:
            print("❌ No rosters loaded")

        db.close()

if __name__ == "__main__":
    main()
