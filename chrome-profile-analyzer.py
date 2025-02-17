import os
import json
from pathlib import Path
from typing import Dict, List, Optional

###############################################################################
# GLOBAL CONFIG / DEBUG SWITCH
###############################################################################
DEBUG = False

def debug(msg: str) -> None:
    """Print debug messages if DEBUG is set."""
    if DEBUG:
        print(f"[DEBUG] {msg}")

###############################################################################
# GLOBAL PATHS
###############################################################################

CHROME_USER_DATA_DIR = Path(
    os.environ.get("CHROME_USER_DATA_DIR", Path.home() / "Library/Application Support/Google/Chrome")
)
LOCAL_STATE_FILE = CHROME_USER_DATA_DIR / "Local State"

###############################################################################
# PROFILE NAME RESOLUTION
###############################################################################

def load_local_state_map(local_state_path: Path) -> Dict[str, dict]:
    """
    Parse 'Local State' -> profile.info_cache -> <profile_folder>.
    Return a dict: { "Profile 1": {...}, "Default": {...}, etc. }
    Each value is the entire info_cache entry, e.g. {
       "name": "...",
       "gaia_name": "...",
       "user_name": "...",
       ...
    }
    """
    if not local_state_path.is_file():
        debug(f"Local State file not found: {local_state_path}")
        return {}

    try:
        with local_state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})
        return info_cache
    except (json.JSONDecodeError, OSError) as e:
        debug(f"Error reading Local State file: {e}")
        return {}

def load_preferences(profile_dir: Path) -> Optional[dict]:
    """
    Try to read and parse the Preferences JSON in a given profile dir.
    Return the parsed dict or None on error.
    """
    pref_path = profile_dir / "Preferences"
    if not pref_path.is_file():
        debug(f"Preferences file not found in {profile_dir}")
        return None
    try:
        with pref_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        debug(f"Error reading Preferences in {profile_dir}: {e}")
        return None

def is_generic_person_name(name: str) -> bool:
    """
    Return True if the name is basically "Person X" or empty, which isn't very descriptive.
    We'll consider 'Person 2', 'Person 1', 'Person 3' as generic placeholders.
    """
    if not name:
        return True
    lower = name.strip().lower()
    # e.g. "person 1", "person 2", "person 12"...
    if lower.startswith("person "):
        # Check if the remainder is an integer
        try:
            int(lower.replace("person ", ""))
            return True
        except ValueError:
            pass
    return False

def build_pretty_name_from_prefs(prefs: dict) -> Optional[str]:
    """
    Attempt to build a user-friendly name from:
      - prefs["profile"]["name"] if it's not generic
      - or "gaia_name" / "user_name"
      - or "account_info" array
    If everything is missing/generic, return None.
    """
    profile_section = prefs.get("profile", {})
    # 1) Use profile->name if not generic
    raw_name = profile_section.get("name")
    if raw_name and not is_generic_person_name(raw_name):
        debug(f"build_pretty_name_from_prefs: using profile->name = {raw_name}")
        return raw_name

    # 2) Check gaia_name / user_name if present
    gaia_name = profile_section.get("gaia_name")
    if gaia_name and not is_generic_person_name(gaia_name):
        debug(f"build_pretty_name_from_prefs: using gaia_name = {gaia_name}")
        return gaia_name

    user_name = profile_section.get("user_name")
    if user_name and not is_generic_person_name(user_name):
        debug(f"build_pretty_name_from_prefs: using user_name = {user_name}")
        return user_name

    # 3) Look at account_info array
    # Usually looks like:
    # "account_info": [
    #   {
    #     "email": "someone@gmail.com",
    #     "full_name": "Some Person",
    #     ...
    #   }
    # ]
    account_info = prefs.get("account_info", [])
    if isinstance(account_info, list) and len(account_info) == 1:
        info = account_info[0]
        email = info.get("email")
        full_name = info.get("full_name")
        # If we have at least an email, we can do something like "full_name (email)"
        if email or full_name:
            combined = ""
            if full_name and not is_generic_person_name(full_name):
                combined = full_name
            if email:
                combined = combined + f" ({email})" if combined else email
            if combined:
                debug(f"build_pretty_name_from_prefs: using account_info => {combined}")
                return combined

    # If we have multiple accounts, we could try more logic,
    # but for now we just skip.

    # Nothing found
    return None

def build_pretty_name_from_local_state(
    profile_dir_name: str, 
    info_cache_map: Dict[str, dict]
) -> Optional[str]:
    """
    Attempt to build a user-friendly name from local state's info_cache
    e.g. info_cache["Profile 32"] -> { "name": "Bob", "gaia_name": "Bob Smith", ... }
    """
    if profile_dir_name not in info_cache_map:
        debug(f"No info_cache entry for {profile_dir_name} in local state.")
        return None

    details = info_cache_map[profile_dir_name]
    # Typically "name" might be "Person 2" or "Alice (alice@example.com)"
    raw_name = details.get("name") or details.get("gaia_name") or details.get("user_name")
    if raw_name and not is_generic_person_name(raw_name):
        debug(f"build_pretty_name_from_local_state: using info_cache => {raw_name}")
        return raw_name

    return None

def get_profile_name(profile_dir: Path, info_cache_map: Dict[str, dict]) -> str:
    """
    Attempt a multi-step approach to get a friendly name.
      1) Preferences -> {profile->name, gaia_name, user_name, account_info}
      2) Local State info_cache
      3) Folder name
    """
    prefs = load_preferences(profile_dir)
    if prefs:
        candidate = build_pretty_name_from_prefs(prefs)
        if candidate and not is_generic_person_name(candidate):
            return candidate

    # Next check local state
    local_state_candidate = build_pretty_name_from_local_state(profile_dir.name, info_cache_map)
    if local_state_candidate and not is_generic_person_name(local_state_candidate):
        return local_state_candidate

    # Fallback
    debug(f"Falling back to raw folder name for {profile_dir}")
    return profile_dir.name

###############################################################################
# FILE SIZE / FORMATTING
###############################################################################

def get_folder_size(path: Path) -> int:
    """Recursively compute the total size (in bytes) of all files in 'path'."""
    total_size = 0
    for root, _, files in os.walk(path):
        for file in files:
            file_path = Path(root) / file
            if file_path.is_file():
                total_size += file_path.stat().st_size
    return total_size

def format_size_in_mb(size_bytes: int) -> str:
    """Convert bytes to MB using 1024*1024, formatted to 2 decimals."""
    return f"{size_bytes / (1024 * 1024):.2f} MB"

###############################################################################
# I18N PLACEHOLDER RESOLUTION
###############################################################################

def try_resolve_i18n_placeholder(placeholder: str, version_dir: Path) -> Optional[str]:
    if not (placeholder.startswith("__MSG_") and placeholder.endswith("__")):
        debug(f"Placeholder doesn't match MSG pattern: {placeholder}")
        return None

    msg_key = placeholder.strip("_").replace("MSG_", "")
    debug(f"Trying to resolve i18n placeholder '{placeholder}' => key '{msg_key}' in version folder: {version_dir}")

    locales_dir = version_dir / "_locales"
    if not locales_dir.is_dir():
        debug(f"No _locales directory found at {locales_dir}")
        return None

    def find_key_in_locales(k: str) -> Optional[str]:
        for locale_subdir in locales_dir.iterdir():
            if not locale_subdir.is_dir():
                continue
            messages_file = locale_subdir / "messages.json"
            if not messages_file.is_file():
                debug(f"[{locale_subdir.name}] messages.json not found.")
                continue

            try:
                data = json.loads(messages_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                debug(f"[{locale_subdir.name}] Error reading messages.json: {e}")
                continue

            debug(f"[{locale_subdir.name}] Checking for key '{k}' in {messages_file}")
            if k in data:
                msg_value = data[k].get("message")
                debug(f"[{locale_subdir.name}] Found key '{k}' => '{msg_value}'")
                return msg_value
            else:
                debug(f"[{locale_subdir.name}] Key '{k}' not found.")

        debug(f"No locale folder contained the key '{k}'")
        return None

    direct = find_key_in_locales(msg_key)
    if direct:
        return direct

    if "_" in msg_key:
        fallback_key = msg_key.split("_", 1)[0]
        debug(f"No direct match for '{msg_key}', trying fallback key '{fallback_key}'")
        fallback = find_key_in_locales(fallback_key)
        if fallback:
            return fallback

    debug(f"No i18n resolution found for '{placeholder}' in {version_dir}")
    return None

###############################################################################
# EXTENSION NAME EXTRACTION
###############################################################################

def get_extension_name(extension_version_dir: Path) -> str:
    manifest_path = extension_version_dir / "manifest.json"
    if not manifest_path.is_file():
        debug(f"No manifest.json in {extension_version_dir}, using parent folder name.")
        return extension_version_dir.parent.name

    debug(f"Reading manifest.json from {manifest_path}")
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        raw_name = manifest.get("default_title") or manifest.get("name")
        debug(f"Raw extension name from manifest: {raw_name}")

        if not raw_name:
            debug("Manifest has no 'default_title' or 'name', using folder name.")
            return extension_version_dir.parent.name

        if raw_name.startswith("__MSG_"):
            debug(f"Attempting i18n resolution for placeholder {raw_name}")
            resolved = try_resolve_i18n_placeholder(raw_name, extension_version_dir)
            if resolved:
                debug(f"Resolved placeholder '{raw_name}' => '{resolved}'")
                return resolved
            else:
                debug(f"Could not resolve placeholder '{raw_name}', returning placeholder.")
        return raw_name

    except (json.JSONDecodeError, OSError) as e:
        debug(f"Error reading manifest.json: {e}")
        return extension_version_dir.parent.name

###############################################################################
# PROFILE ENUMERATION
###############################################################################

def enumerate_profiles(chrome_data_dir: Path) -> List[Path]:
    if not chrome_data_dir.is_dir():
        print(f"Could not find Chrome data directory at {chrome_data_dir}")
        return []

    valid_profiles = []
    for item in chrome_data_dir.iterdir():
        if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile ")):
            valid_profiles.append(item)

    return valid_profiles

###############################################################################
# MAIN
###############################################################################

def main() -> None:
    # 1) Load the entire info_cache from Local State (for potential fallback)
    info_cache_map = load_local_state_map(LOCAL_STATE_FILE)

    # 2) Enumerate profile directories
    profiles = enumerate_profiles(CHROME_USER_DATA_DIR)

    profile_info = []
    for profile_dir in profiles:
        # Build a more descriptive name with our new approach
        friendly_name = get_profile_name(profile_dir, info_cache_map)
        size_bytes = get_folder_size(profile_dir)
        profile_info.append((friendly_name, profile_dir, size_bytes))

    # Sort by size descending
    profile_info.sort(key=lambda x: x[2], reverse=True)

    print("=== Chrome Profiles (sorted by size) ===")
    for friendly_name, profile_dir, prof_size in profile_info:
        print(f"- {friendly_name} [{profile_dir.name}] : {format_size_in_mb(prof_size)}")
        print(f"  Profile path: {profile_dir.resolve()}\n")

        extensions_dir = profile_dir / "Extensions"
        if not extensions_dir.is_dir():
            print("  (No Extensions directory found.)\n")
            continue

        extension_details = []
        for ext_id_folder in extensions_dir.iterdir():
            if not ext_id_folder.is_dir():
                continue

            total_ext_size = 0
            ext_friendly_name: Optional[str] = None

            # Summation across *all* version subfolders
            subfolders = sorted([d for d in ext_id_folder.iterdir() if d.is_dir()])
            for version_folder in subfolders:
                version_size = get_folder_size(version_folder)
                total_ext_size += version_size

                candidate_name = get_extension_name(version_folder)
                # If we currently have no name or only a placeholder
                if ext_friendly_name is None:
                    ext_friendly_name = candidate_name
                else:
                    # If we still have a placeholder, but the candidate is real, overwrite
                    if ext_friendly_name.startswith("__MSG_") and not candidate_name.startswith("__MSG_"):
                        ext_friendly_name = candidate_name

            if not ext_friendly_name:
                ext_friendly_name = ext_id_folder.name

            extension_details.append((ext_friendly_name, total_ext_size, ext_id_folder))

        # Sort extensions by size descending
        extension_details.sort(key=lambda x: x[1], reverse=True)

        print("  Extensions (sorted by size):")
        for ext_name, ext_size, ext_path in extension_details:
            print(f"    • {ext_name} : {format_size_in_mb(ext_size)} => {ext_path.resolve()}")
        print()

if __name__ == "__main__":
    main()