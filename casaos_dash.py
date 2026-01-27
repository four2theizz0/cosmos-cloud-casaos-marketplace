import requests
import os
from datetime import datetime
from urllib.parse import quote
import json
import yaml
import base64

# Load environment variables from .env file if it exists
from pathlib import Path
if Path(".env").exists():
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

# -----------------------------
# CONFIGURATION
# -----------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Recommended
CACHE_DIR = "compose_cache"
SCREENSHOTS_DIR = "screenshots"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else "",
    "Accept": "application/vnd.github+json"
}

REPOS = [
    ("IceWhaleTech", "CasaOS-AppStore"),
    ("WisdomSky", "CasaOS-LinuxServer-AppStore"),
    ("WisdomSky", "CasaOS-Coolstore"),
    ("mr-manuel", "CasaOS-HomeAutomation-AppStore"),
    ("bigbeartechworld", "big-bear-casaos"),
    ("mariosemes", "CasaOS-TMCstore"),
    ("justserdar", "ZimaOS-AppStore")
]

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def list_app_folders(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/Apps"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"❌ Couldn't list /Apps for {owner}/{repo} - Status: {response.status_code}")
            if response.status_code == 403:
                print(f"   Rate limit exceeded. Remaining: {response.headers.get('X-RateLimit-Remaining', 'Unknown')}")
                print(f"   Reset time: {response.headers.get('X-RateLimit-Reset', 'Unknown')}")
            elif response.status_code == 401:
                print(f"   Authentication failed - check your GITHUB_TOKEN")
            elif response.status_code == 404:
                print(f"   Repository or /Apps directory not found")
            else:
                print(f"   Error details: {response.text[:200]}")
            return []
        return [item['name'] for item in response.json() if item['type'] == 'dir']
    except requests.exceptions.Timeout:
        print(f"❌ Timeout listing apps for {owner}/{repo}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error listing apps for {owner}/{repo}: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error listing apps for {owner}/{repo}: {e}")
        return []

def get_creation_date(owner, repo, folder):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?path=Apps/{folder}&per_page=100"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None
        commits = response.json()
        return commits[-1]['commit']['author']['date'] if commits else None
    except Exception as e:
        print(f"   ⚠️ Error getting creation date for {folder}: {e}")
        return None

def get_repo_stats(owner, repo):
    """Get repository statistics including stars, forks, and default branch"""
    # Use cache for repo stats (valid for 1 hour)
    cache_file = os.path.join("cache", f"repo_stats_{owner}_{repo}.json")
    
    if os.path.exists(cache_file):
        file_age = datetime.now().timestamp() - os.path.getmtime(cache_file)
        if file_age < 3600:  # 1 hour
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
    
    url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            repo_data = response.json()
            stats = {
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "default_branch": repo_data.get("default_branch", "main"),
                "updated_at": datetime.now().isoformat()
            }
            
            # Cache the stats
            try:
                if not os.path.exists("cache"):
                    os.makedirs("cache")
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(stats, f, indent=2)
            except Exception as e:
                print(f"   ⚠️ Failed to cache repo stats: {e}")
            
            return stats
    except Exception as e:
        print(f"   ⚠️ Error getting repo stats for {owner}/{repo}: {e}")
    
    return {"stars": 0, "forks": 0, "default_branch": "main"}

def get_app_screenshots(owner, repo, folder, branch="main"):
    """Detect and download screenshots from app directory"""
    # Create screenshots directory if it doesn't exist
    app_screenshots_dir = os.path.join(SCREENSHOTS_DIR, f"{owner}_{repo}_{folder}")
    if not os.path.exists(app_screenshots_dir):
        os.makedirs(app_screenshots_dir, exist_ok=True)
    
    # Check cache for screenshot info
    cache_file = os.path.join("cache", f"screenshots_{owner}_{repo}_{folder}.json")
    if os.path.exists(cache_file):
        file_age = datetime.now().timestamp() - os.path.getmtime(cache_file)
        if file_age < 86400:  # 24 hours
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
    
    # Common screenshot file patterns to look for
    screenshot_patterns = [
        'screenshot-1.png', 'screenshot-2.png', 'screenshot-3.png', 'screenshot-4.png', 'screenshot-5.png',
        'screenshot1.png', 'screenshot2.png', 'screenshot3.png',
        'screen1.png', 'screen2.png', 'screen3.png',
        'image1.png', 'image2.png', 'image3.png',
        'preview1.png', 'preview2.png', 'preview3.png',
        'demo1.png', 'demo2.png', 'demo3.png'
    ]
    
    screenshots = []
    
    for screenshot_file in screenshot_patterns:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/Apps/{folder}/{screenshot_file}"
        local_path = os.path.join(app_screenshots_dir, screenshot_file)
        
        # Skip if already downloaded
        if os.path.exists(local_path):
            screenshots.append({
                "filename": screenshot_file,
                "local_path": local_path,
                "url": url
            })
            continue
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Verify it's actually an image by checking content type
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('image/'):
                    # Save the image
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    
                    screenshots.append({
                        "filename": screenshot_file,
                        "local_path": local_path,
                        "url": url
                    })
                    print(f"   📸 Downloaded {screenshot_file}")
        except Exception as e:
            # Silently continue - missing screenshots are expected
            continue
    
    # Cache the screenshot info
    screenshot_data = {
        "screenshots": screenshots,
        "count": len(screenshots),
        "updated_at": datetime.now().isoformat()
    }
    
    try:
        if not os.path.exists("cache"):
            os.makedirs("cache")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(screenshot_data, f, indent=2)
    except Exception as e:
        print(f"   ⚠️ Failed to cache screenshot data: {e}")
    
    return screenshot_data

def get_conf_json(owner, repo, folder):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/Apps/{folder}/conf.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return {}
    try:
        content = response.json().get('content', '')
        content = content.encode('ascii')  # raw base64 sometimes returns unicode
        decoded = base64.b64decode(content).decode('utf-8')
        return json.loads(decoded)
    except:
        return {}

def get_conf_json_raw(owner, repo, folder, branch="main"):
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/Apps/{folder}/conf.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"   ⚠️ Error fetching conf.json for {folder}: {e}")
    return {}

def get_docker_compose(owner, repo, folder, branch="main"):
    """Fetch docker-compose.yml file from app directory with caching"""
    # Create cache directory if it doesn't exist
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    
    cache_file = os.path.join(CACHE_DIR, f"compose_{owner}_{repo}_{folder}.yml")
    
    # Check if cached file exists and is recent (less than 24 hours old)
    if os.path.exists(cache_file):
        file_age = datetime.now().timestamp() - os.path.getmtime(cache_file)
        if file_age < 86400:  # 24 hours in seconds
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                print(f"   ⚠️ Cache read error for {folder}: {e}")
    
    # Fetch from GitHub using the specified branch
    compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
    last_error = None
    
    for compose_file in compose_files:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/Apps/{folder}/{compose_file}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                try:
                    compose_data = yaml.safe_load(response.text)
                    
                    # Cache the file
                    try:
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            yaml.dump(compose_data, f)
                    except Exception as cache_error:
                        print(f"   ⚠️ Cache write error for {folder}: {cache_error}")
                    
                    return compose_data
                except yaml.YAMLError as yaml_error:
                    print(f"   ⚠️ YAML parse error in {compose_file}: {yaml_error}")
                    continue
            elif response.status_code == 404:
                # Expected for non-existent files, continue to next
                continue
            else:
                last_error = f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            print(f"   ⚠️ Timeout fetching {compose_file} from {owner}/{repo}/{folder}")
        except requests.exceptions.RequestException as e:
            last_error = f"Network error: {e}"
        except Exception as e:
            last_error = f"Unexpected error: {e}"
    
    # Only log if it's not just missing compose files (404s are expected)
    if last_error and "404" not in str(last_error):
        print(f"   ❌ Failed to fetch compose files for {owner}/{repo}/{folder}: {last_error}")
    
    return {}

def extract_compose_metadata(compose_data, conf_data):
    """Extract metadata from docker-compose file"""
    if not compose_data:
        return {}
    
    metadata = {}
    
    # Extract from x-casaos section (root level) - this is the primary source for CasaOS apps
    casaos_info = compose_data.get('x-casaos', {})
    
    # Get services data
    services = compose_data.get('services', {})
    main_service = next(iter(services.values())) if services else {}
    
    # Extract from service labels as fallback
    labels = main_service.get('labels', [])
    if isinstance(labels, list):
        # Convert list format to dict
        label_dict = {}
        for label in labels:
            if '=' in label:
                key, value = label.split('=', 1)
                label_dict[key] = value
    else:
        label_dict = labels or {}
    
    # Extract metadata with priority: x-casaos > service labels > conf.json
    
    # Title - handle multi-language format
    title = casaos_info.get('title')
    if isinstance(title, dict):
        title = title.get('en_US', title.get('en_us', title.get('en', '')))
    
    metadata['title'] = (
        title or 
        label_dict.get('casaos.title') or 
        conf_data.get('title', '')
    )
    
    # Icon
    metadata['icon'] = (
        casaos_info.get('icon') or 
        label_dict.get('casaos.icon') or 
        conf_data.get('icon', '')
    )
    
    # Description - extract from x-casaos description (en_US, en_us, en if available)
    description = casaos_info.get('description')
    if isinstance(description, dict):
        description = description.get('en_US', description.get('en_us', description.get('en', '')))
    
    # Fallback to tagline if no description
    if not description:
        tagline = casaos_info.get('tagline')
        if isinstance(tagline, dict):
            description = tagline.get('en_US', tagline.get('en_us', tagline.get('en', '')))
        elif isinstance(tagline, str):
            description = tagline
    
    metadata['description'] = (
        description or
        label_dict.get('casaos.description') or 
        conf_data.get('description', '')
    )
    
    # Category - x-casaos is the primary source
    category = (
        casaos_info.get('category') or 
        label_dict.get('casaos.category') or 
        conf_data.get('category')
    )
    
    # If still no category, try to infer from app name
    if not category:
        app_name = (metadata['title'] or conf_data.get('title', '')).lower()
        
        # Category mapping based on common app names
        category_mapping = {
            'Media': ['plex', 'jellyfin', 'emby', 'kodi', 'sonarr', 'radarr', 'lidarr', 'bazarr', 'tautulli', 'overseerr', 'jellyseerr', 'navidrome'],
            'Downloader': ['qbittorrent', 'transmission', 'deluge', 'sabnzbd', 'nzbget', 'jackett', 'prowlarr', 'autobrr'],
            'Cloud': ['nextcloud', 'owncloud', 'seafile', 'syncthing', 'filebrowser'],
            'Database': ['mariadb', 'mysql', 'postgres', 'mongodb', 'redis', 'influxdb'],
            'Network': ['pihole', 'adguard', 'nginx', 'traefik', 'cloudflared', 'wireguard', 'ddns'],
            'Home Automation': ['homeassistant', 'openhab', 'node-red', 'mosquitto', 'zigbee2mqtt', 'esphome'],
            'Utilities': ['portainer', 'watchtower', 'duplicati', 'resilio', 'uptime', 'grafana', 'netdata'],
            'AI': ['ollama', 'stable-diffusion', 'chatgpt', 'open-webui', 'anythingllm', 'flowise', 'dify'],
            'Notes': ['trilium', 'obsidian', 'joplin', 'memos', 'hedgedoc', 'logseq'],
            'Developer': ['gitea', 'jenkins', 'code-server', 'vscode'],
            'Finance': ['firefly', 'actual', 'budget']
        }
        
        for cat, apps in category_mapping.items():
            if any(app in app_name for app in apps):
                category = cat
                break
    
    metadata['category'] = category or 'Uncategorized'
    
    # Author
    metadata['author'] = (
        casaos_info.get('author') or 
        label_dict.get('casaos.author') or 
        conf_data.get('author', '')
    )
    metadata['version'] = label_dict.get('casaos.version', main_service.get('image', '').split(':')[-1] if ':' in main_service.get('image', '') else '')
    
    # Extract ports
    ports = main_service.get('ports', [])
    if ports:
        # Get first port mapping
        first_port = ports[0]
        if isinstance(first_port, dict):
            # Handle complex port object
            target = first_port.get('target', first_port.get('published', ''))
            metadata['port'] = str(target) if target else ''
        elif ':' in str(first_port):
            # Handle "host:container" format
            metadata['port'] = str(first_port).split(':')[0]
        else:
            metadata['port'] = str(first_port)
    
    # Extract volumes
    volumes = main_service.get('volumes', [])
    metadata['volumes'] = volumes if volumes else []
    
    # Extract environment variables
    environment = main_service.get('environment', [])
    if isinstance(environment, list):
        env_dict = {}
        for env in environment:
            if '=' in env:
                key, value = env.split('=', 1)
                env_dict[key] = value
        metadata['environment'] = env_dict
    else:
        metadata['environment'] = environment
    
    # Memory limits
    if 'deploy' in main_service and 'resources' in main_service['deploy']:
        limits = main_service['deploy']['resources'].get('limits', {})
        metadata['memory'] = limits.get('memory', '')
    
    return metadata

def format_date(iso_str):
    if not iso_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except:
        return "Unknown"

# -----------------------------
# MAIN LOGIC
# -----------------------------

print("🔍 Gathering apps from all stores...\n")

# Load last run timestamp to detect new apps
last_run_file = "cache/last_run.json"
last_run_time = None
if os.path.exists(last_run_file):
    try:
        with open(last_run_file, 'r') as f:
            data = json.load(f)
            last_run_time = datetime.fromisoformat(data.get('last_run', ''))
    except:
        pass

apps = []
repo_stats_cache = {}  # Cache repo stats per repo to avoid duplicate API calls

for owner, repo in REPOS:
    # Get repo stats once per repo
    repo_key = f"{owner}/{repo}"
    if repo_key not in repo_stats_cache:
        print(f"📊 Getting stats for {repo_key}")
        repo_stats_cache[repo_key] = get_repo_stats(owner, repo)
    
    folders = list_app_folders(owner, repo)
    for folder in folders:
        print(f"📦 {repo}/{folder}", end="")
        
        # Check if we have cached app data
        cache_file = os.path.join("cache", f"app_{owner}_{repo}_{folder}.json")
        app_data = {}
        
        if os.path.exists(cache_file):
            # Check if cache is recent (less than 24 hours)
            file_age = datetime.now().timestamp() - os.path.getmtime(cache_file)
            if file_age < 86400:  # 24 hours
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        app_data = json.load(f)
                        print(" 🔄 Using cached data")
                except:
                    pass
        
        if not app_data:
            # Get both conf.json and docker-compose files
            try:
                # Get the default branch for this repo
                repo_stats = repo_stats_cache.get(f"{owner}/{repo}", {"default_branch": "main"})
                branch = repo_stats.get("default_branch", "main")
                
                conf = get_conf_json_raw(owner, repo, folder, branch)
                compose = get_docker_compose(owner, repo, folder, branch)
                screenshots = get_app_screenshots(owner, repo, folder, branch)
                
                if compose:
                    print(" ✅ Docker Compose found")
                else:
                    print(" ⚠️  No Docker Compose")
                
                # Extract metadata from compose file, fallback to conf.json
                compose_metadata = extract_compose_metadata(compose, conf)
                
                title = compose_metadata.get("title") or conf.get("title") or folder
                desc = compose_metadata.get("description") or conf.get("description") or "No description available."
                icon = compose_metadata.get("icon") or conf.get("icon", "https://via.placeholder.com/64")
                category = compose_metadata.get("category", "Uncategorized")
                author = compose_metadata.get("author", "Unknown")
                version = compose_metadata.get("version", "Unknown")
                website = conf.get("website") or conf.get("url") or f"https://github.com/{owner}/{repo}/tree/{branch}/Apps/{folder}"
                created = get_creation_date(owner, repo, folder)
                
                # Determine if this app is "new" since last run
                is_new = False
                if last_run_time and created:
                    try:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        is_new = created_dt > last_run_time
                    except:
                        pass
                elif not os.path.exists(cache_file):
                    # If no cache file exists, consider it new
                    is_new = True

                # Get repo stats
                repo_stats = repo_stats_cache.get(f"{owner}/{repo}", {"stars": 0, "forks": 0})

                app_data = {
                    "title": title,
                    "description": desc,
                    "icon": icon,
                    "category": category,
                    "repo": f"{owner}/{repo}",
                    "url": website,
                    "created": created,
                    "author": author,
                    "version": version,
                    "port": compose_metadata.get("port"),
                    "volumes": compose_metadata.get("volumes", []),
                    "environment": compose_metadata.get("environment", {}),
                    "memory": compose_metadata.get("memory"),
                    "compose_available": bool(compose),
                    "stars": repo_stats["stars"],
                    "forks": repo_stats["forks"],
                    "is_new": is_new,
                    "screenshots": screenshots.get("screenshots", []),
                    "screenshot_count": screenshots.get("count", 0),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Cache the app data
                try:
                    if not os.path.exists("cache"):
                        os.makedirs("cache")
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(app_data, f, indent=2)
                except Exception as cache_error:
                    print(f"   ⚠️ Failed to cache app data for {folder}: {cache_error}")
                    
            except Exception as e:
                print(f"   ❌ Error processing {folder}: {e}")
                # Get repo stats even for failed apps
                repo_stats = repo_stats_cache.get(f"{owner}/{repo}", {"stars": 0, "forks": 0, "default_branch": "main"})
                branch = repo_stats.get("default_branch", "main")
                
                # Create minimal app data for failed apps
                app_data = {
                    "title": folder,
                    "description": "Error loading app data",
                    "icon": "https://via.placeholder.com/64",
                    "category": "Error",
                    "repo": f"{owner}/{repo}",
                    "url": f"https://github.com/{owner}/{repo}/tree/{branch}/Apps/{folder}",
                    "created": None,
                    "author": "Unknown",
                    "version": "Unknown",
                    "port": None,
                    "volumes": [],
                    "environment": {},
                    "memory": None,
                    "compose_available": False,
                    "stars": repo_stats["stars"],
                    "forks": repo_stats["forks"],
                    "is_new": False,
                    "screenshots": [],
                    "screenshot_count": 0,
                    "updated_at": datetime.now().isoformat()
                }
        
        apps.append(app_data)

# Save current run timestamp
try:
    if not os.path.exists("cache"):
        os.makedirs("cache")
    with open(last_run_file, 'w') as f:
        json.dump({"last_run": datetime.now().isoformat()}, f)
except Exception as e:
    print(f"⚠️ Failed to save run timestamp: {e}")

# Sort newest first (default)
apps.sort(key=lambda x: x["created"] or "", reverse=True)

# -----------------------------
# HTML OUTPUT
# -----------------------------

html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CasaOS App Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 2em; background: #f4f4f4; margin: 0; }
        h1 { font-size: 2em; margin-bottom: 0.5em; color: #333; }
        .filters { margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 15px; align-items: center; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        select, input[type="text"] { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        input[type="text"] { min-width: 250px; }
        .search-box, .filter-group { display: flex; flex-direction: column; }
        .search-box label, .filter-group label { margin-bottom: 4px; font-weight: 600; color: #555; font-size: 0.9em; }
        .counter { margin-bottom: 15px; color: #333; font-weight: bold; display: flex; gap: 20px; align-items: center; }
        .highlight { background-color: yellow; font-weight: bold; }
        
        /* Card Grid Layout */
        #appList { 
            display: grid; 
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); 
            gap: 20px; 
            margin-top: 20px; 
        }
        
        .app { 
            background: white; 
            border-radius: 12px; 
            padding: 20px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.1); 
            transition: all 0.3s ease; 
            border: 1px solid #e0e0e0;
            position: relative;
        }
        .app:hover { 
            box-shadow: 0 8px 25px rgba(0,0,0,0.15); 
            transform: translateY(-2px); 
        }
        
        .app-header {
            display: flex;
            align-items: flex-start;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .app-icon { 
            width: 64px; 
            height: 64px; 
            border-radius: 12px; 
            object-fit: contain; 
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            flex-shrink: 0;
        }
        
        .app-info {
            flex: 1;
            min-width: 0;
        }
        
        .app-title { 
            margin: 0 0 8px 0; 
            font-size: 1.2em; 
            font-weight: 600;
            color: #1a1a1a;
            line-height: 1.3;
        }
        
        .app-title a {
            text-decoration: none;
            color: inherit;
        }
        
        .app-title a:hover {
            color: #007bff;
        }
        
        .app-badges {
            display: flex;
            gap: 6px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }
        
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .compose-badge { 
            background: #17a2b8; 
            color: white; 
        }
        
        .new-badge { 
            background: #28a745; 
            color: white; 
        }
        
        .screenshots-badge { 
            background: #6f42c1; 
            color: white; 
        }
        
        .app-description { 
            margin: 0 0 15px 0; 
            color: #666; 
            line-height: 1.5;
            font-size: 0.9em;
        }
        
        .app-meta { 
            font-size: 0.8em; 
            color: #888; 
            margin-bottom: 12px;
        }
        
        .app-stats {
            display: flex;
            gap: 15px;
            margin-bottom: 10px;
            font-size: 0.85em;
        }
        
        .stat {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #666;
        }
        
        .stat-icon {
            width: 16px;
            height: 16px;
        }
        
        .tech-info { 
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }
        
        .tech-info span { 
            background: #f8f9fa; 
            color: #495057;
            padding: 4px 8px; 
            border-radius: 4px; 
            font-size: 0.75em;
            font-weight: 500;
            border: 1px solid #e9ecef;
        }
        
        /* Dark Mode Styles */
        body.dark-mode {
            background: #1a1a1a;
            color: #e0e0e0;
        }
        
        body.dark-mode h1 {
            color: #ffffff;
        }
        
        body.dark-mode .filters {
            background: #2d2d2d;
            border: 1px solid #404040;
        }
        
        body.dark-mode .filter-group label {
            color: #b0b0b0;
        }
        
        body.dark-mode select,
        body.dark-mode input[type="text"] {
            background: #3d3d3d;
            border: 1px solid #555;
            color: #e0e0e0;
        }
        
        body.dark-mode select:focus,
        body.dark-mode input[type="text"]:focus {
            border-color: #007bff;
            outline: none;
        }
        
        body.dark-mode .app {
            background: #2d2d2d;
            border: 1px solid #404040;
        }
        
        body.dark-mode .app:hover {
            box-shadow: 0 8px 25px rgba(255,255,255,0.1);
        }
        
        body.dark-mode .app-title {
            color: #ffffff;
        }
        
        body.dark-mode .app-title a:hover {
            color: #66b3ff;
        }
        
        body.dark-mode .app-description {
            color: #b0b0b0;
        }
        
        body.dark-mode .app-meta {
            color: #888;
        }
        
        body.dark-mode .stat {
            color: #b0b0b0;
        }
        
        body.dark-mode .tech-info span {
            background: #3d3d3d;
            color: #e0e0e0;
            border: 1px solid #555;
        }
        
        body.dark-mode .app-icon {
            background: #3d3d3d;
            border: 1px solid #555;
        }
        
        body.dark-mode .highlight {
            background-color: #ffa500;
            color: #000;
        }

        /* Dark Mode Toggle */
        .header-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .dark-mode-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            padding: 8px 16px;
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 20px;
            transition: all 0.3s ease;
            user-select: none;
        }
        
        .dark-mode-toggle:hover {
            background: #e9ecef;
        }
        
        body.dark-mode .dark-mode-toggle {
            background: #3d3d3d;
            border: 1px solid #555;
            color: #e0e0e0;
        }
        
        body.dark-mode .dark-mode-toggle:hover {
            background: #4d4d4d;
        }
        
        .toggle-switch {
            position: relative;
            width: 44px;
            height: 24px;
            background: #ccc;
            border-radius: 12px;
            transition: background 0.3s ease;
        }
        
        .toggle-switch::after {
            content: '';
            position: absolute;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: white;
            top: 2px;
            left: 2px;
            transition: transform 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        
        body.dark-mode .toggle-switch {
            background: #007bff;
        }
        
        body.dark-mode .toggle-switch::after {
            transform: translateX(20px);
        }
        
        /* Screenshot Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.9);
            animation: fadeIn 0.3s ease;
        }
        
        .modal-content {
            position: relative;
            margin: auto;
            padding: 20px;
            width: 90%;
            max-width: 1000px;
            height: 90%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        
        .modal-header {
            color: white;
            text-align: center;
            margin-bottom: 20px;
        }
        
        .modal-header h2 {
            margin: 0;
            font-size: 1.5em;
        }
        
        .screenshot-container {
            position: relative;
            width: 100%;
            height: 80%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .screenshot-image {
            max-width: 100%;
            max-height: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        }
        
        .screenshot-nav {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            font-size: 24px;
            padding: 10px 15px;
            border-radius: 50%;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .screenshot-nav:hover {
            background: rgba(255, 255, 255, 0.4);
        }
        
        .screenshot-nav.prev {
            left: 20px;
        }
        
        .screenshot-nav.next {
            right: 20px;
        }
        
        .screenshot-counter {
            color: white;
            text-align: center;
            margin-top: 15px;
            font-size: 0.9em;
        }
        
        .close-modal {
            position: absolute;
            top: 15px;
            right: 25px;
            color: white;
            font-size: 35px;
            font-weight: bold;
            cursor: pointer;
            background: none;
            border: none;
            padding: 0;
            line-height: 1;
        }
        
        .close-modal:hover {
            opacity: 0.7;
        }
        
        .has-screenshots {
            cursor: pointer;
        }
        
        .has-screenshots:hover {
            transform: translateY(-3px);
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        /* Mobile responsive */
        @media (max-width: 768px) {
            body { padding: 1em; }
            #appList { 
                grid-template-columns: 1fr; 
                gap: 15px; 
            }
            .filters { 
                flex-direction: column; 
                align-items: stretch; 
                gap: 10px; 
            }
            .counter {
                flex-direction: column;
                gap: 10px;
                align-items: flex-start;
            }
            .header-controls {
                flex-direction: column;
                gap: 15px;
                align-items: flex-start;
            }
        }
    </style>
</head>
<body>
<div class="header-controls">
    <h1>🏠 CasaOS App Dashboard</h1>
    <div class="dark-mode-toggle" onclick="toggleDarkMode()">
        <span id="darkModeText">🌙 Dark Mode</span>
        <div class="toggle-switch"></div>
    </div>
</div>
<div class="counter">
    <div>Total Apps: <span id="appCount">{count}</span> | Filtered: <span id="filteredCount">{count}</span></div>
    <div style="font-size: 0.9em; color: #666;">Click on app names to visit their repositories</div>
</div>

<div class="filters">
    <div class="search-box">
        <label for="searchInput">🔍 Search Apps:</label>
        <input type="text" id="searchInput" placeholder="Search by name, description, or category...">
    </div>
    
    <div class="filter-group">
        <label for="sortBy">📊 Sort By:</label>
        <select id="sortBy">
            <option value="created">Newest First</option>
            <option value="name">Name A-Z</option>
            <option value="stars">Most Stars</option>
            <option value="category">Category</option>
            <option value="repo">Repository</option>
        </select>
    </div>
    
    <div class="filter-group">
        <label for="repoFilter">🏪 Store:</label>
        <select id="repoFilter">
            <option value="All">All Stores</option>
            {repo_options}
        </select>
    </div>

    <div class="filter-group">
        <label for="catFilter">📂 Category:</label>
        <select id="catFilter">
            <option value="All">All Categories</option>
            {cat_options}
        </select>
    </div>
    
    <div class="filter-group">
        <label for="composeFilter">🐳 Docker Compose:</label>
        <select id="composeFilter">
            <option value="All">All</option>
            <option value="Yes">With Compose</option>
            <option value="No">Without Compose</option>
        </select>
    </div>
    
    <div class="filter-group">
        <label for="newFilter">✨ New Apps:</label>
        <select id="newFilter">
            <option value="All">All Apps</option>
            <option value="New">New Only</option>
        </select>
    </div>
</div>

<!-- Screenshot Modal -->
<div id="screenshotModal" class="modal">
    <div class="modal-content">
        <button class="close-modal" onclick="closeScreenshotModal()">&times;</button>
        <div class="modal-header">
            <h2 id="modalAppTitle">App Screenshots</h2>
        </div>
        <div class="screenshot-container">
            <button class="screenshot-nav prev" onclick="previousScreenshot()">&#8249;</button>
            <img id="modalScreenshot" class="screenshot-image" src="" alt="Screenshot">
            <button class="screenshot-nav next" onclick="nextScreenshot()">&#8250;</button>
        </div>
        <div class="screenshot-counter">
            <span id="screenshotCounter">1 / 1</span>
        </div>
    </div>
</div>

<div id="appList">
""".strip()

# Generate dynamic options
all_repos = sorted(set(app['repo'] for app in apps))
all_cats = sorted(set(app['category'] for app in apps if app['category'] and app['category'] != 'Uncategorized'))
# Add Uncategorized at the end if it exists
if any(app['category'] == 'Uncategorized' for app in apps):
    all_cats.append('Uncategorized')

repo_options = "\n".join(f"<option value='{r}'>{r}</option>" for r in all_repos)
cat_options = "\n".join(f"<option value='{c}'>{c}</option>" for c in all_cats)

# Insert into template
html = html.replace("{repo_options}", repo_options)
html = html.replace("{cat_options}", cat_options)
html = html.replace("{count}", str(len(apps)))

# App entries
app_entries = ""
for app in apps:
    # Badges
    badges = []
    if app.get('compose_available'):
        badges.append('<span class="badge compose-badge">Docker</span>')
    if app.get('is_new'):
        badges.append('<span class="badge new-badge">New</span>')
    if app.get('screenshot_count', 0) > 0:
        count = app.get('screenshot_count')
        badges.append(f'<span class="badge screenshots-badge">📸 {count}</span>')
    badges_html = f'<div class="app-badges">{"".join(badges)}</div>' if badges else ''
    
    # Technical info
    tech_info = []
    if app.get('version') and app['version'] != 'Unknown':
        tech_info.append(f"v{app['version']}")
    if app.get('author') and app['author'] != 'Unknown':
        tech_info.append(f"by {app['author']}")
    if app.get('port'):
        tech_info.append(f"Port: {app['port']}")
    if app.get('memory'):
        tech_info.append(f"RAM: {app['memory']}")
    
    tech_info_html = ''
    if tech_info:
        tech_spans = ''.join(f'<span>{info}</span>' for info in tech_info)
        tech_info_html = f'<div class="tech-info">{tech_spans}</div>'
    
    # Handle titles and descriptions that might be dicts
    title_text = app['title']
    if isinstance(title_text, dict):
        title_text = title_text.get('en_us') or title_text.get('en') or title_text.get('en_US') or str(list(title_text.values())[0]) if title_text else 'Unknown'
    
    desc_text = app['description']  
    if isinstance(desc_text, dict):
        desc_text = desc_text.get('en_us') or desc_text.get('en') or desc_text.get('en_US') or str(list(desc_text.values())[0]) if desc_text else 'No description available.'
    
    # Truncate long descriptions
    if len(str(desc_text)) > 120:
        desc_text = str(desc_text)[:117] + "..."
    
    # Escape quotes in data attributes
    title_escaped = str(title_text).replace('"', '&quot;')
    desc_escaped = str(desc_text).replace('"', '&quot;')
    
    # Stats
    stars = app.get('stars', 0)
    forks = app.get('forks', 0)
    stats_html = f'''
    <div class="app-stats">
        <div class="stat">
            <svg class="stat-icon" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
            </svg>
            <span>{stars:,}</span>
        </div>
        <div class="stat">
            <svg class="stat-icon" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M7.707 3.293a1 1 0 010 1.414L5.414 7H11a7 7 0 017 7v2a1 1 0 11-2 0v-2a5 5 0 00-5-5H5.414l2.293 2.293a1 1 0 11-1.414 1.414L2.586 7l3.707-3.707a1 1 0 011.414 0z" clip-rule="evenodd"/>
            </svg>
            <span>{forks:,}</span>
        </div>
    </div>''' if stars > 0 or forks > 0 else ''
    
    # Generate screenshot data for the modal
    screenshot_data = ""
    if app.get('screenshots'):
        screenshot_urls = []
        for screenshot in app['screenshots']:
            # Convert local path to relative web path
            rel_path = screenshot['local_path'].replace('\\', '/')
            screenshot_urls.append(screenshot['url'])  # Use GitHub URL for now
        screenshot_data = json.dumps(screenshot_urls).replace('"', '&quot;')
    
    # Make card clickable if it has screenshots
    card_class = "app"
    card_onclick = ""
    if app.get('screenshot_count', 0) > 0:
        card_class += " has-screenshots"
        card_onclick = f'onclick="openScreenshotModal(this)" data-screenshots=\'{screenshot_data}\''
    
    app_entries += f"""
    <div class="{card_class}" data-repo="{app['repo']}" data-cat="{app['category']}" data-compose="{str(app.get('compose_available', False)).lower()}" data-new="{str(app.get('is_new', False)).lower()}" data-title="{title_escaped}" data-desc="{desc_escaped}" data-stars="{stars}" data-created="{app.get('created', '')}" {card_onclick}>
        <div class="app-header">
            <img class="app-icon" src="{app['icon']}" alt="{title_text}">
            <div class="app-info">
                <h3 class="app-title">
                    <a href="{app['url']}" target="_blank" onclick="event.stopPropagation()">{title_text}</a>
                </h3>
                {badges_html}
            </div>
        </div>
        <p class="app-description">{desc_text}</p>
        {stats_html}
        <div class="app-meta">{app['repo']} | {app['category']} | Created: {format_date(app['created'])}</div>
        {tech_info_html}
    </div>
    """

html += app_entries

# Closing tags + JS
html += """
</div>
<script>
    const repoFilter = document.getElementById('repoFilter');
    const catFilter = document.getElementById('catFilter');
    const composeFilter = document.getElementById('composeFilter');
    const newFilter = document.getElementById('newFilter');
    const sortBy = document.getElementById('sortBy');
    const searchInput = document.getElementById('searchInput');
    const appList = document.getElementById('appList');
    const appCount = document.getElementById('appCount');
    const filteredCount = document.getElementById('filteredCount');
    
    let apps = Array.from(document.querySelectorAll('.app'));

    // Debounce function for search input
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function highlightSearchTerms(text, searchTerms) {
        if (!searchTerms.length) return text;
        
        let highlightedText = text;
        searchTerms.forEach(term => {
            if (term.length > 1) {
                const regex = new RegExp(`(${term})`, 'gi');
                highlightedText = highlightedText.replace(regex, '<span class="highlight">$1</span>');
            }
        });
        return highlightedText;
    }
    
    function sortApps() {
        const sortValue = sortBy.value;
        
        apps.sort((a, b) => {
            switch(sortValue) {
                case 'name':
                    return a.dataset.title.localeCompare(b.dataset.title);
                case 'stars':
                    return parseInt(b.dataset.stars || 0) - parseInt(a.dataset.stars || 0);
                case 'category':
                    const catCompare = a.dataset.cat.localeCompare(b.dataset.cat);
                    return catCompare !== 0 ? catCompare : a.dataset.title.localeCompare(b.dataset.title);
                case 'repo':
                    const repoCompare = a.dataset.repo.localeCompare(b.dataset.repo);
                    return repoCompare !== 0 ? repoCompare : a.dataset.title.localeCompare(b.dataset.title);
                case 'created':
                default:
                    const aDate = a.dataset.created || '';
                    const bDate = b.dataset.created || '';
                    return bDate.localeCompare(aDate); // Newest first
            }
        });
        
        // Re-append sorted apps
        apps.forEach(app => appList.appendChild(app));
    }

    function filterApps() {
        const selectedRepo = repoFilter.value;
        const selectedCat = catFilter.value;
        const selectedCompose = composeFilter.value;
        const selectedNew = newFilter.value;
        const searchTerm = searchInput.value.toLowerCase().trim();
        const searchTerms = searchTerm.split(' ').filter(term => term.length > 0);
        
        let visible = 0;

        apps.forEach(app => {
            // Reset highlights first
            const titleElement = app.querySelector('.app-title a');
            const descElement = app.querySelector('.app-description');
            const originalTitle = app.dataset.title;
            const originalDesc = app.dataset.desc;
            
            const matchRepo = selectedRepo === "All" || app.dataset.repo === selectedRepo;
            const matchCat = selectedCat === "All" || app.dataset.cat === selectedCat;
            const hasCompose = app.dataset.compose === "true";
            const matchCompose = selectedCompose === "All" || 
                (selectedCompose === "Yes" && hasCompose) || 
                (selectedCompose === "No" && !hasCompose);
            const isNew = app.dataset.new === "true";
            const matchNew = selectedNew === "All" || 
                (selectedNew === "New" && isNew);
            
            // Search matching
            let matchSearch = true;
            if (searchTerm) {
                const searchableText = `${originalTitle} ${originalDesc} ${app.dataset.cat}`.toLowerCase();
                matchSearch = searchTerms.every(term => searchableText.includes(term));
            }
            
            if (matchRepo && matchCat && matchCompose && matchNew && matchSearch) {
                app.style.display = "block";
                visible++;
                
                // Apply highlighting if there's a search term
                if (searchTerm) {
                    titleElement.innerHTML = highlightSearchTerms(originalTitle, searchTerms);
                    descElement.innerHTML = highlightSearchTerms(originalDesc, searchTerms);
                } else {
                    titleElement.innerHTML = originalTitle;
                    descElement.innerHTML = originalDesc;
                }
            } else {
                app.style.display = "none";
            }
        });

        filteredCount.textContent = visible;
    }

    // Event listeners
    repoFilter.addEventListener("change", filterApps);
    catFilter.addEventListener("change", filterApps);
    composeFilter.addEventListener("change", filterApps);
    newFilter.addEventListener("change", filterApps);
    sortBy.addEventListener("change", () => {
        sortApps();
        filterApps();
    });
    searchInput.addEventListener("input", debounce(filterApps, 300));
    
    // Clear search with Escape key
    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            this.value = '';
            filterApps();
        }
    });
    
    // Dark Mode Functionality
    function toggleDarkMode() {
        const body = document.body;
        const darkModeText = document.getElementById('darkModeText');
        
        body.classList.toggle('dark-mode');
        
        if (body.classList.contains('dark-mode')) {
            darkModeText.textContent = '☀️ Light Mode';
            localStorage.setItem('darkMode', 'enabled');
        } else {
            darkModeText.textContent = '🌙 Dark Mode';
            localStorage.setItem('darkMode', 'disabled');
        }
    }
    
    // Initialize dark mode based on saved preference
    function initDarkMode() {
        const darkMode = localStorage.getItem('darkMode');
        const body = document.body;
        const darkModeText = document.getElementById('darkModeText');
        
        if (darkMode === 'enabled') {
            body.classList.add('dark-mode');
            darkModeText.textContent = '☀️ Light Mode';
        } else {
            darkModeText.textContent = '🌙 Dark Mode';
        }
    }
    
    // Screenshot Modal Functionality
    let currentScreenshots = [];
    let currentScreenshotIndex = 0;
    
    function openScreenshotModal(cardElement) {
        const screenshotsData = cardElement.getAttribute('data-screenshots');
        const appTitle = cardElement.getAttribute('data-title');
        
        if (!screenshotsData) return;
        
        try {
            currentScreenshots = JSON.parse(screenshotsData);
            currentScreenshotIndex = 0;
            
            document.getElementById('modalAppTitle').textContent = appTitle + ' Screenshots';
            document.getElementById('screenshotModal').style.display = 'block';
            
            showCurrentScreenshot();
            
            // Prevent body scroll when modal is open
            document.body.style.overflow = 'hidden';
        } catch (e) {
            console.error('Error opening screenshot modal:', e);
        }
    }
    
    function closeScreenshotModal() {
        document.getElementById('screenshotModal').style.display = 'none';
        document.body.style.overflow = 'auto';
    }
    
    function showCurrentScreenshot() {
        if (currentScreenshots.length === 0) return;
        
        const screenshot = currentScreenshots[currentScreenshotIndex];
        const img = document.getElementById('modalScreenshot');
        const counter = document.getElementById('screenshotCounter');
        
        img.src = screenshot;
        counter.textContent = `${currentScreenshotIndex + 1} / ${currentScreenshots.length}`;
        
        // Show/hide navigation buttons
        const prevBtn = document.querySelector('.screenshot-nav.prev');
        const nextBtn = document.querySelector('.screenshot-nav.next');
        
        prevBtn.style.display = currentScreenshots.length > 1 ? 'block' : 'none';
        nextBtn.style.display = currentScreenshots.length > 1 ? 'block' : 'none';
    }
    
    function previousScreenshot() {
        if (currentScreenshots.length <= 1) return;
        currentScreenshotIndex = currentScreenshotIndex > 0 ? currentScreenshotIndex - 1 : currentScreenshots.length - 1;
        showCurrentScreenshot();
    }
    
    function nextScreenshot() {
        if (currentScreenshots.length <= 1) return;
        currentScreenshotIndex = currentScreenshotIndex < currentScreenshots.length - 1 ? currentScreenshotIndex + 1 : 0;
        showCurrentScreenshot();
    }
    
    // Close modal on background click
    document.getElementById('screenshotModal').addEventListener('click', function(e) {
        if (e.target === this) {
            closeScreenshotModal();
        }
    });
    
    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeScreenshotModal();
        } else if (e.key === 'ArrowLeft') {
            previousScreenshot();
        } else if (e.key === 'ArrowRight') {
            nextScreenshot();
        }
    });

    // Initialize everything
    initDarkMode();
    sortApps();
</script>
</body>
</html>
"""

# Save to file
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

# Get absolute path for clickable link
dashboard_path = Path("index.html").absolute()
file_url = f"file://{dashboard_path}"

print(f"\n✅ Dashboard saved as index.html")
print(f"🔗 Open: {file_url}")

