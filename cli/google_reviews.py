#!/usr/bin/env python3
"""
Google My Business Reviews CLI

A command-line tool to fetch and display Google My Business reviews
across all your restaurant locations.

This script imports core API logic from app.services.google_api.

Usage:
    python -m cli.google_reviews              # Normal mode: show all reviews
    python -m cli.google_reviews --debug      # Debug mode: show all location details
"""

import sys
import json
from app.services.google_api import authenticate, get_all_accounts, get_locations_for_account, get_reviews


def main():
    """Authenticate and display reviews for all business locations."""
    debug = '--debug' in sys.argv

    print("Authenticating with Google My Business API...")
    creds = authenticate()

    print("\nFetching locations...")

    if debug:
        print("\n[DEBUG MODE] Fetching all accounts and locations...\n")

        # First, list all accounts
        print("=" * 60)
        print("STEP 1: Listing all accounts")
        print("=" * 60)
        accounts = get_all_accounts(creds)
        if accounts:
            print(f"Found {len(accounts)} account(s):\n")
            for i, account in enumerate(accounts, 1):
                print(f"Account {i}:")
                print(json.dumps(account, indent=2))
                print()
        else:
            print("No accounts found.\n")
            return

        # Then list all locations for each account
        print("=" * 60)
        print("STEP 2: Listing all locations for each account")
        print("=" * 60)

        # Build the discovery service once
        from googleapiclient.discovery import build
        service = build('mybusinessbusinessinformation', 'v1', credentials=creds)

        all_account_locations = []
        total_locations = 0
        for account in accounts:
            account_id = account['name']
            account_name = account.get('accountName', 'Unknown')
            locations = get_locations_for_account(service, account_id)
            total_locations += len(locations)

            print(f"\nAccount: {account_name} ({account_id})")
            print(f"Locations found: {len(locations)}")
            if locations:
                for i, loc in enumerate(locations, 1):
                    loc_name = loc.get('name', 'Unknown')
                    loc_title = loc.get('title', 'Unknown Title')
                    print(f"  {i}. {loc_title} ({loc_name})")
            else:
                print("  (No locations)")

        print(f"\nTotal locations across all accounts: {total_locations}\n")
        return

    # Normal mode: fetch and display reviews
    accounts = get_all_accounts(creds)
    if not accounts:
        print("No accounts found.")
        return

    # Collect all locations from all accounts
    from googleapiclient.discovery import build
    service = build('mybusinessbusinessinformation', 'v1', credentials=creds)

    all_locations = []
    for account in accounts:
        account_id = account['name']
        locations = get_locations_for_account(service, account_id)
        all_locations.extend(locations)

    if not all_locations:
        print("No locations found. Make sure your Google My Business account is set up.")
        print("\nTip: Run with --debug flag to see all location data:")
        print("  python -m cli.google_reviews --debug")
        return

    print(f"Found {len(all_locations)} location(s):\n")

    for location in all_locations:
        location_name = location['name']
        business_name = location.get('title', 'Unknown Business')

        print(f"📍 {business_name}")
        print(f"   Location: {location_name}")

        # Fetch reviews
        reviews = get_reviews(creds, location_name)
        print(f"   Reviews: {len(reviews)}")

        if reviews:
            print("   Recent reviews:")
            for review in reviews[:5]:  # Show first 5
                author = review.get('reviewer', {}).get('displayName', 'Anonymous')
                rating = review.get('starRating', 'N/A')
                # Convert rating format (FIVE -> 5, FOUR -> 4, etc.)
                if isinstance(rating, str):
                    rating_map = {'FIVE': '5', 'FOUR': '4', 'THREE': '3', 'TWO': '2', 'ONE': '1'}
                    rating = rating_map.get(rating, rating)
                text = review.get('comment', 'No text')[:100]
                print(f"      ⭐ {rating}/5 - {author}: {text}...")

        print()


if __name__ == '__main__':
    main()
