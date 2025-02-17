import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

###############################################################################
# GLOBAL CONFIG / DEBUG SWITCH
###############################################################################
DEBUG = True

def debug(message: str) -> None:
    """Print debug messages if DEBUG is set."""
    if DEBUG:
        print(f"[DEBUG] {message}")

###############################################################################
# GLOBAL PATHS
###############################################################################
CHROME_USER_DATA_DIR = Path(
    os.environ.get("CHROME_USER_DATA_DIR", Path.home() / "Library/Application Support/Google/Chrome")
)
LOCAL_STATE_FILE = CHROME_USER_DATA_DIR / "Local State"

###############################################################################
# HELPER: GENERIC JSON LOADER
###############################################################################
def load_json_file(file_path: Path) -> Optional[Any]:
    """Return JSON data from a file, or None if file doesn't exist or fails to parse."""
    if not file_path.is_file():
        debug(f"JSON file not found: {file_path}")
        return None
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        debug(f"Error reading JSON from {file_path}: {e}")
        return None

###############################################################################
# LOCAL STATE / PREFERENCES
###############################################################################
def load_info_cache_map(local_state_path: Path) -> Dict[str, dict]:
    """Return profile info_cache from the 'Local State' file."""
    data = load_json_file(local_state_path) or {}
    return data.get("profile", {}).get("info_cache", {})

def load_preferences(profile_dir: Path) -> Optional[dict]:
    """Return Preferences JSON dict from a given profile directory."""
    return load_json_file(profile_dir / "Preferences")

###############################################################################
# GENERIC NAME CHECK
###############################################################################
def is_generic_person_name(name: str) -> bool:
    """True if name is empty or matches 'Person X' patterns."""
    name = (name or "").strip().lower()
    if not name or not name.startswith("person "):
        return False
    try:
        # e.g. "Person 1", "Person 12" => after "person " must be int
        int(name.replace("person ", ""))
        return True
    except ValueError:
        return False

###############################################################################
# BUILD PROFILE NAMES
###############################################################################
def build_pretty_name_from_prefs(prefs: dict) -> Optional[str]:
    """
    Attempt to derive a user-friendly name from Preferences:
      - prefs["profile"]["name"] if not generic
      - or "gaia_name" / "user_name"
      - or "account_info" array
    """
    profile_section = prefs.get("profile", {})

    # 1) Check 'profile->name' if not generic
    raw_name = profile_section.get("name")
    if raw_name and not is_generic_person_name(raw_name):
        debug(f"Using profile->name = {raw_name}")
        return raw_name

    # 2) Check gaia_name / user_name
    for key in ("gaia_name", "user_name"):
        val = profile_section.get(key)
        if val and not is_generic_person_name(val):
            debug(f"Using {key} = {val}")
            return val

    # 3) Check account_info array (often has 'email'/'full_name')
    account_info = prefs.get("account_info", [])
    if isinstance(account_info, list) and len(account_info) == 1:
        info = account_info[0]
        email = info.get("email")
        full_name = info.get("full_name")
        if email or full_name:
            combined = ""
            if full_name and not is_generic_person_name(full_name):
                combined = full_name
            if email:
                combined = f"{combined} ({email})" if combined else email
            return combined or None

    return None

def build_pretty_name_from_local_state(profile_dir_name: str, info_cache_map: Dict[str, dict]) -> Optional[str]:
    """
    Attempt to derive a user-friendly name from local state's info_cache:
      - info_cache["Profile 2"]["name"] etc.
    """
    details = info_cache_map.get(profile_dir_name)
    if not details:
        return None

    raw_name = details.get("name") or details.get("gaia_name") or details.get("user_name")
    if raw_name and not is_generic_person_name(raw_name):
        debug(f"Using info_cache => {raw_name}")
        return raw_name
    return None

def get_profile_name(profile_dir: Path, info_cache_map: Dict[str, dict]) -> str:
    """Multi-step approach to find a friendly name (Preferences -> Local State -> folder name)."""
    prefs = load_preferences(profile_dir)
    if prefs:
        candidate = build_pretty_name_from_prefs(prefs)
        if candidate and not is_generic_person_name(candidate):
            return candidate

    local_state_candidate = build_pretty_name_from_local_state(profile_dir.name, info_cache_map)
    if local_state_candidate and not is_generic_person_name(local_state_candidate):
        return local_state_candidate

    # Fallback to folder name
    return profile_dir.name

###############################################################################
# I18N PLACEHOLDER RESOLUTION
###############################################################################
def try_resolve_i18n_placeholder(placeholder: str, version_dir: Path) -> Optional[str]:
    """Resolve __MSG_xxx__ placeholders from manifest.json by scanning _locales."""
    if not (placeholder.startswith("__MSG_") and placeholder.endswith("__")):
        return None

    msg_key = placeholder.strip("_").replace("MSG_", "")
    locales_dir = version_dir / "_locales"
    if not locales_dir.is_dir():
        return None

    def find_key_in_locales(key: str) -> Optional[str]:
        for locale_subdir in locales_dir.iterdir():
            if not locale_subdir.is_dir():
                continue
            messages_data = load_json_file(locale_subdir / "messages.json") or {}
            if key in messages_data:
                return messages_data[key].get("message")
        return None

    # Try direct key
    direct = find_key_in_locales(msg_key)
    if direct:
        return direct

    # Try fallback: if there's an underscore, use the left side
    if "_" in msg_key:
        fallback_key = msg_key.split("_", 1)[0]
        return find_key_in_locales(fallback_key)

    return None

###############################################################################
# EXTENSION NAME EXTRACTION
###############################################################################
def get_extension_name(extension_version_dir: Path) -> str:
    """Return a user-friendly extension name by reading manifest.json (including i18n resolution)."""
    manifest_path = extension_version_dir / "manifest.json"
    if not manifest_path.is_file():
        return extension_version_dir.parent.name  # fallback to parent folder name

    manifest = load_json_file(manifest_path) or {}
    raw_name = manifest.get("default_title") or manifest.get("name")
    if not raw_name:
        return extension_version_dir.parent.name

    # Attempt i18n resolution if needed
    if raw_name.startswith("__MSG_"):
        resolved = try_resolve_i18n_placeholder(raw_name, extension_version_dir)
        return resolved if resolved else raw_name

    return raw_name

###############################################################################
# PROFILE ENUMERATION & SIZE HELPERS
###############################################################################
def enumerate_profiles(chrome_data_dir: Path) -> List[Path]:
    """Return paths for all Chrome profiles in the data dir (Default + Profile X...)."""
    if not chrome_data_dir.is_dir():
        print(f"Could not find Chrome data directory at {chrome_data_dir}")
        return []
    return [
        p for p in chrome_data_dir.iterdir()
        if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile "))
    ]

def get_folder_size(path: Path) -> int:
    """Recursively compute the total size (in bytes) of all files in 'path'."""
    total = 0
    for root, _, files in os.walk(path):
        for file in files:
            file_path = Path(root) / file
            if file_path.is_file():
                total += file_path.stat().st_size
    return total

def format_size_in_mb(size_bytes: int) -> str:
    """Convert bytes to MB (1024 * 1024) with 2 decimals."""
    return f"{size_bytes / (1024 * 1024):.2f} MB"

###############################################################################
# MAIN EXECUTION
###############################################################################
def main() -> None:
    # 1) Load the local info cache map
    info_cache_map = load_info_cache_map(LOCAL_STATE_FILE)

    # 2) Enumerate all profile directories
    profiles = enumerate_profiles(CHROME_USER_DATA_DIR)

    # 3) Gather profile info (friendly name + size)
    profile_data = []
    for profile_dir in profiles:
        friendly_name = get_profile_name(profile_dir, info_cache_map)
        size_bytes = get_folder_size(profile_dir)
        profile_data.append((friendly_name, profile_dir, size_bytes))

    # 4) Sort profiles by size descending
    profile_data.sort(key=lambda x: x[2], reverse=True)

    print("=== Chrome Profiles (sorted by size) ===")
    for friendly_name, profile_dir, prof_size in profile_data:
        print(f"- {friendly_name} [{profile_dir.name}] : {format_size_in_mb(prof_size)}")
        print(f"  Profile path: {profile_dir.resolve()}\n")

        extensions_dir = profile_dir / "Extensions"
        if not extensions_dir.is_dir():
            print("  (No Extensions directory found.)\n")
            continue

        # Summarize each extension (all version subfolders)
        extension_info = []
        for ext_id_folder in extensions_dir.iterdir():
            if not ext_id_folder.is_dir():
                continue

            total_ext_size = 0
            ext_name_candidate: Optional[str] = None

            for version_folder in sorted(d for d in ext_id_folder.iterdir() if d.is_dir()):
                version_size = get_folder_size(version_folder)
                total_ext_size += version_size

                name = get_extension_name(version_folder)
                # If no name yet or if we only have a placeholder, prefer a real name
                if ext_name_candidate is None or ext_name_candidate.startswith("__MSG_"):
                    ext_name_candidate = name

            extension_info.append((ext_name_candidate or ext_id_folder.name, total_ext_size, ext_id_folder))

        # Sort extensions by size descending
        extension_info.sort(key=lambda x: x[1], reverse=True)

        print("  Extensions (sorted by size):")
        for ext_name, ext_size, ext_path in extension_info:
            print(f"    • {ext_name} : {format_size_in_mb(ext_size)} => {ext_path.resolve()}")
        print()

if __name__ == "__main__":
    main()