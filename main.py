#!/usr/bin/env python3

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

def get_local_state_profile_names(local_state_path: Path) -> Dict[str, str]:
    """
    Parse 'Local State' JSON to build a mapping of profile directory names
    (e.g., 'Profile 1', 'Profile 32', etc.) to their user-friendly name.
    """
    if not local_state_path.is_file():
        debug(f"Local State file not found: {local_state_path}")
        return {}

    try:
        with local_state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})

        results = {}
        for profile_dir_name, details in info_cache.items():
            name = details.get("name")
            if not name:
                # fallback to user_name or gaia_name
                name = details.get("gaia_name") or details.get("user_name")
            if name:
                results[profile_dir_name] = name
        return results
    except (json.JSONDecodeError, OSError) as e:
        debug(f"Error reading Local State file: {e}")
        return {}

def get_profile_name(profile_dir: Path, profile_dir_to_name: Dict[str, str]) -> str:
    """
    1) Check 'Preferences' -> 'profile->name'
    2) Else see if local_state_map has a name
    3) Else fallback to folder name
    """
    preferences_path = profile_dir / "Preferences"
    if preferences_path.is_file():
        try:
            with preferences_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            pref_name = data.get("profile", {}).get("name")
            if pref_name:
                debug(f"Profile {profile_dir.name} name from Preferences: {pref_name}")
                return pref_name
        except (json.JSONDecodeError, OSError) as e:
            debug(f"Error reading Preferences for {profile_dir.name}: {e}")

    # 2) local_state_map
    if profile_dir.name in profile_dir_to_name:
        debug(f"Profile {profile_dir.name} name from Local State map: {profile_dir_to_name[profile_dir.name]}")
        return profile_dir_to_name[profile_dir.name]

    # 3) fallback
    debug(f"No friendly name found for {profile_dir.name}, using directory name.")
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
    """
    Attempt to resolve placeholders like '__MSG_name_releasebuild__' by searching
    all `_locales/*/messages.json` in the given version folder (e.g., 4.13.0_0).

    We'll look for:
      1) direct key 'name_releasebuild'
      2) if not found and there's an underscore, fallback 'name'
    """
    if not (placeholder.startswith("__MSG_") and placeholder.endswith("__")):
        debug(f"Placeholder doesn't match MSG pattern: {placeholder}")
        return None

    msg_key = placeholder.strip("_").replace("MSG_", "")  # e.g. "name_releasebuild"
    debug(f"Trying to resolve i18n placeholder '{placeholder}' => key '{msg_key}' in version folder: {version_dir}")

    locales_dir = version_dir / "_locales"
    if not locales_dir.is_dir():
        debug(f"No _locales directory found at {locales_dir}")
        return None

    def find_key_in_locales(k: str) -> Optional[str]:
        """Search all locales in `_locales/<locale>/messages.json` for key `k`."""
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

    # 1) direct match
    direct = find_key_in_locales(msg_key)
    if direct:
        return direct

    # 2) fallback if there's an underscore => 'name_releasebuild' => 'name'
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
    """
    Parse the 'manifest.json' for 'default_title' or 'name'.
    If it's an i18n placeholder, try to resolve it in `_locales`.
    """
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
    """
    Return a list of Chrome profile directories: 'Default', 'Profile 1', 'Profile N', etc.
    """
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
    local_state_map = get_local_state_profile_names(LOCAL_STATE_FILE)
    profiles = enumerate_profiles(CHROME_USER_DATA_DIR)

    # Gather (friendly_name, Path, size_bytes) for each profile
    profile_info = []
    for profile_dir in profiles:
        friendly_name = get_profile_name(profile_dir, local_state_map)
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
                # and the candidate is a non-placeholder, overwrite
                if ext_friendly_name is None:
                    ext_friendly_name = candidate_name
                else:
                    # If we still have a placeholder, but the candidate is real, overwrite
                    if ext_friendly_name.startswith("__MSG_") and not candidate_name.startswith("__MSG_"):
                        ext_friendly_name = candidate_name

            # If we never got any name, fallback to the extension folder name
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