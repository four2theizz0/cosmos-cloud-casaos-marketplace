#!/usr/bin/env python3
"""
Generate Cosmos Cloud marketplace JSON from CasaOS app data.
Creates a servapps.json file compatible with Cosmos Cloud custom markets.
"""

import json
import re
from pathlib import Path

def extract_app_folder_from_url(url):
    """Extract the app folder name from GitHub URL."""
    # URL format: https://github.com/owner/repo/tree/branch/Apps/folder
    match = re.search(r'/Apps/([^/]+)/?$', url)
    if match:
        return match.group(1)
    return None

def get_branch_from_url(url):
    """Extract branch name from GitHub URL."""
    match = re.search(r'/tree/([^/]+)/', url)
    if match:
        return match.group(1)
    return "main"

def sanitize_id(name):
    """Create a URL-safe ID from app name."""
    # Remove special characters, convert spaces to hyphens, lowercase
    sanitized = re.sub(r'[^a-zA-Z0-9\s-]', '', str(name))
    sanitized = re.sub(r'\s+', '-', sanitized).strip('-')
    return sanitized.lower()

def get_tags_from_category(category):
    """Convert category to tags array."""
    if not category or category == "Uncategorized":
        return ["self-hosted"]

    # Split category if it contains multiple parts
    tags = [category]

    # Add common related tags based on category
    category_tags = {
        "Media": ["media", "streaming", "entertainment"],
        "Downloader": ["download", "torrent", "usenet"],
        "Cloud": ["cloud", "storage", "sync"],
        "Database": ["database", "sql", "data"],
        "Network": ["network", "dns", "proxy"],
        "Home Automation": ["home-automation", "iot", "smart-home"],
        "Utilities": ["utilities", "tools"],
        "AI": ["ai", "machine-learning", "llm"],
        "Notes": ["notes", "productivity", "documentation"],
        "Developer": ["developer", "devops", "git"],
        "Finance": ["finance", "budget", "money"],
        "Photos": ["photos", "gallery", "images"],
        "Documents": ["documents", "office", "pdf"],
    }

    for cat, extra_tags in category_tags.items():
        if cat.lower() in category.lower():
            tags.extend(extra_tags)
            break

    # Add self-hosted tag to all
    if "self-hosted" not in tags:
        tags.append("self-hosted")

    return list(set(tags))  # Remove duplicates

def format_long_description(app):
    """Create HTML-formatted long description."""
    desc = app.get('description', '')
    if isinstance(desc, dict):
        desc = desc.get('en_us') or desc.get('en') or desc.get('en_US') or str(list(desc.values())[0]) if desc else ''

    parts = [f"<p>{desc}</p>"]

    # Add metadata
    meta = []
    if app.get('author') and app['author'] != 'Unknown':
        meta.append(f"<b>Author:</b> {app['author']}")
    if app.get('version') and app['version'] != 'Unknown':
        meta.append(f"<b>Version:</b> {app['version']}")
    if app.get('port'):
        meta.append(f"<b>Default Port:</b> {app['port']}")

    if meta:
        parts.append("<p>" + " | ".join(meta) + "</p>")

    # Add source info
    parts.append(f"<p><i>Source: CasaOS App Store ({app.get('repo', 'Unknown')})</i></p>")

    return "\n".join(parts)

def convert_app_to_cosmos(app):
    """Convert a CasaOS app entry to Cosmos marketplace format."""

    # Extract title
    title = app.get('title', 'Unknown')
    if isinstance(title, dict):
        title = title.get('en_us') or title.get('en') or title.get('en_US') or str(list(title.values())[0]) if title else 'Unknown'

    # Extract description
    desc = app.get('description', '')
    if isinstance(desc, dict):
        desc = desc.get('en_us') or desc.get('en') or desc.get('en_US') or str(list(desc.values())[0]) if desc else ''

    # Get folder and branch from URL
    app_url = app.get('url', '')
    folder = extract_app_folder_from_url(app_url)
    branch = get_branch_from_url(app_url)
    repo = app.get('repo', '')

    # Construct compose URL (try docker-compose.yml first)
    compose_url = ""
    if repo and folder:
        compose_url = f"https://raw.githubusercontent.com/{repo}/{branch}/Apps/{folder}/docker-compose.yml"

    # Get screenshots URLs
    screenshots = []
    for screenshot in app.get('screenshots', []):
        if isinstance(screenshot, dict) and screenshot.get('url'):
            screenshots.append(screenshot['url'])
        elif isinstance(screenshot, str):
            screenshots.append(screenshot)

    # Build Cosmos app entry
    cosmos_app = {
        "name": str(title),
        "longDescription": format_long_description(app),
        "description": str(desc)[:200] if desc else "No description available.",
        "tags": get_tags_from_category(app.get('category', '')),
        "repository": app_url if app_url else f"https://github.com/{repo}",
        "image": "",  # Docker Hub URL - would need to parse compose to get this
        "supported_architectures": ["amd64", "arm64"],
        "id": sanitize_id(title),
        "screenshots": screenshots,
        "logo": [],
        "icon": app.get('icon', ''),
        "artefacts": {},
        "compose": compose_url
    }

    return cosmos_app

def main():
    # Load apps data
    apps_file = Path("apps_data.json")
    if not apps_file.exists():
        print("Error: apps_data.json not found")
        return

    print("Loading apps_data.json...")
    with open(apps_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    apps = data.get('apps', [])
    stats = data.get('stats', {})

    print(f"Found {len(apps)} apps")

    # Convert apps to Cosmos format
    cosmos_apps = []
    skipped = 0
    seen_ids = set()

    for app in apps:
        # Skip apps without compose
        if not app.get('compose_available', False):
            skipped += 1
            continue

        cosmos_app = convert_app_to_cosmos(app)

        # Skip if no compose URL could be generated
        if not cosmos_app['compose']:
            skipped += 1
            continue

        # Handle duplicate IDs by appending repo suffix
        original_id = cosmos_app['id']
        if original_id in seen_ids:
            # Add repo suffix to make unique
            repo_suffix = app.get('repo', '').split('/')[-1][:10].lower()
            cosmos_app['id'] = f"{original_id}-{repo_suffix}"

        # Still duplicate? Add counter
        counter = 1
        while cosmos_app['id'] in seen_ids:
            cosmos_app['id'] = f"{original_id}-{counter}"
            counter += 1

        seen_ids.add(cosmos_app['id'])
        cosmos_apps.append(cosmos_app)

    print(f"Converted {len(cosmos_apps)} apps (skipped {skipped} without compose)")

    # Save as plain array (Cosmos marketplace format)
    output_file = Path("servapps.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cosmos_apps, f, indent=2, ensure_ascii=False)

    print(f"\nGenerated {output_file}")
    print(f"Total apps: {len(cosmos_apps)}")
    print(f"\nNext steps:")
    print("1. Update the 'source' URL in servapps.json to your GitHub Pages URL")
    print("2. Push to a GitHub repo with GitHub Pages enabled")
    print("3. Add the servapps.json URL to Cosmos: Settings > Marketplace Sources")

if __name__ == "__main__":
    main()
