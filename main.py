#!/usr/bin/env python3

import os
import json
from pathlib import Path
from typing import Dict, List, Optional

CHROME_USER_DATA_DIR = Path(os.environ.get("CHROME_USER_DATA_DIR", Path.home() / "Library/Application Support/Google/Chrome"))
LOCAL_STATE_FILE = CHROME_USER_DATA_DIR / "Local State"

def get_local_state_profile_names(local_state_path: Path) -> Dict[str, str]:
    """
    Parse the 'Local State' JSON to build a mapping of profile directory names
    (e.g. 'Profile 1', 'Profile 32', etc.) to their user-friendly name.
    Returns a dict: { 'Profile 1': 'My Person (myemail@gmail.com)', ... }
    """
    if not local_state_path.is_file():
        return {}

    try:
        with local_state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})
        # info_cache typically looks like:
        # "Profile 1": {
        #     "name": "Some Person",
        #     "user_name": "some@some.com",
        #     ...
        # }
        results = {}
        for profile_dir_name, details in info_cache.items():
            # "name" field often includes the Gmail or user’s name
            name = details.get("name")
            if not name:
                # fallback to user_name or gaia_name
                name = details.get("gaia_name") or details.get("user_name")
            if name:
                results[profile_dir_name] = name
        return results
    except (json.JSONDecodeError, OSError):
        return {}


def get_folder_size(path: Path) -> int:
    """
    Recursively compute the total size (in bytes) of all files in 'path'.
    """
    total_size = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = Path(root) / file
            if file_path.is_file():
                total_size += file_path.stat().st_size
    return total_size


def get_profile_name(profile_dir: Path, profile_dir_to_name: Dict[str, str]) -> str:
    """
    Given a Chrome profile directory, try:
      1) The 'Preferences' file's 'profile->name'
      2) The 'Local State' file's info_cache mapping
      3) Fallback to the folder name
    """
    # 1) If Preferences has a name, use it
    preferences_path = profile_dir / "Preferences"
    if preferences_path.is_file():
        try:
            with preferences_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            pref_name = data.get("profile", {}).get("name")
            if pref_name:
                return pref_name
        except (json.JSONDecodeError, OSError):
            pass

    # 2) Else see if the local_state mapping has a name
    if profile_dir.name in profile_dir_to_name:
        return profile_dir_to_name[profile_dir.name]

    # 3) Fallback
    return profile_dir.name


def format_size_in_mb(size_bytes: int) -> str:
    """Convert bytes to MB (using 1024*1024) and format to 2 decimals."""
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def try_resolve_i18n_placeholder(
    placeholder: str,
    manifest: Dict,
    extension_folder: Path
) -> Optional[str]:
    """
    If 'placeholder' looks like '__MSG_xyz__', attempt to resolve it using the extension's
    default_locale from manifest + the matching '_locales/<locale>/messages.json'.
    Returns None if resolution fails.
    """
    # For example, placeholders can look like: "__MSG_extName__"
    if not placeholder.startswith("__MSG_") or not placeholder.endswith("__"):
        return None

    # The extension might define default_locale in the manifest
    default_locale = manifest.get("default_locale", "en_US")

    # The actual key in messages.json would be everything inside the placeholder
    # e.g., "__MSG_extName__" => "extName"
    msg_key = placeholder.strip("_").replace("MSG_", "")
    

    if default_locale != "en_US":
        locales_dir = extension_folder / "_locales/en_GB"
        messages_path = locales_dir / "messages.json"
    else:
        locales_dir = extension_folder / "_locales/es"
        messages_path = locales_dir / "messages.json"
        
    if not messages_path.is_file():
        # Attempt fallback to "en" if default_locale is not "en"
        if default_locale != "en":
            locales_dir = extension_folder / "_locales/en"
            messages_path = locales_dir / "messages.json"
            if not messages_path.is_file():
                return None
        else:
            return None

    try:
        with messages_path.open("r", encoding="utf-8") as f:
            locale_data = json.load(f)
        # Typically the file has structure like:
        # {
        #   "extName": {
        #       "message": "My Friendly Name"
        #   },
        #   ...
        # }
        if msg_key in locale_data:
            return locale_data[msg_key].get("message", None)
        return None
    except (json.JSONDecodeError, OSError):
        return None


def get_extension_name(extension_version_dir: Path) -> str:
    """
    Find and parse the 'manifest.json' inside an extension's version folder.
    Prefer 'default_title'; otherwise fallback to 'name'.
    If those hold an i18n placeholder like '__MSG_whatever__',
    try to resolve it via _locales/<locale>/messages.json.
    """
    manifest_path = extension_version_dir / "manifest.json"
    if not manifest_path.is_file():
        return extension_version_dir.parent.name  # Use extension ID folder name as fallback

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Attempt to get extension name
        # Step 1: pick the field (default_title or name)
        raw_name = None
        if "default_title" in manifest:
            raw_name = manifest["default_title"]
        else:
            raw_name = manifest.get("name", extension_version_dir.parent.name)

        # Step 2: if it's an i18n placeholder, try to resolve it
        if raw_name.startswith("__MSG_"):
            resolved = try_resolve_i18n_placeholder(raw_name, manifest, extension_version_dir.parent)
            if resolved:
                return resolved
        return raw_name
    except (json.JSONDecodeError, OSError):
        return extension_version_dir.parent.name


def enumerate_profiles(chrome_data_dir: Path) -> List[Path]:
    """
    Return a list of all valid Chrome profile directories under 'chrome_data_dir'.
    Typically 'Default', 'Profile 1', 'Profile 2', etc.
    """
    valid_profiles = []
    if not chrome_data_dir.is_dir():
        print(f"Could not find Chrome data directory at {chrome_data_dir}")
        return valid_profiles

    for item in chrome_data_dir.iterdir():
        if item.is_dir():
            # Common Chrome profiles: 'Default' or 'Profile N'
            if item.name == "Default" or item.name.startswith("Profile "):
                valid_profiles.append(item)
    return valid_profiles


def main() -> None:
    # 1) Build a name map from "Local State" to help with additional fallback naming
    local_state_map = get_local_state_profile_names(LOCAL_STATE_FILE)

    # 2) Enumerate all profile directories
    profiles = enumerate_profiles(CHROME_USER_DATA_DIR)
    profile_info = []
    for profile_dir in profiles:
        friendly_name = get_profile_name(profile_dir, local_state_map)
        size_bytes = get_folder_size(profile_dir)
        profile_info.append((friendly_name, profile_dir, size_bytes))

    # Sort profiles by size descending
    profile_info.sort(key=lambda x: x[2], reverse=True)

    print("=== Chrome Profiles (sorted by size) ===")
    for friendly_name, profile_dir, prof_size in profile_info:
        print(f"- {friendly_name} [{profile_dir.name}] : {format_size_in_mb(prof_size)}")
        print(f"  Profile path: {profile_dir.resolve()}")
        
        # Within each profile, examine Extensions folder
        extensions_dir = profile_dir / "Extensions"
        if not extensions_dir.is_dir():
            print("  (No Extensions directory found.)\n")
            continue

        # Gather extension info: (extension_friendly_name, total_size, extension_folder)
        extension_details = []
        for ext_id_folder in extensions_dir.iterdir():
            if not ext_id_folder.is_dir():
                continue

            # Sum up all version subfolders
            total_ext_size = 0
            ext_friendly_name: Optional[str] = None
            # We'll store the ext_id_folder path for easy removal references
            for version_folder in ext_id_folder.iterdir():
                if version_folder.is_dir():
                    total_ext_size += get_folder_size(version_folder)
                    # If we haven't assigned a user-friendly name yet, parse it
                    if ext_friendly_name is None:
                        ext_friendly_name = get_extension_name(version_folder)

            # Fallback if no manifest found anywhere
            if not ext_friendly_name:
                ext_friendly_name = ext_id_folder.name

            extension_details.append((ext_friendly_name, total_ext_size, ext_id_folder))

        # Sort extensions by size descending
        extension_details.sort(key=lambda x: x[1], reverse=True)

        print("  Extensions (sorted by size):")
        for ext_name, ext_size, ext_path in extension_details:
            print(
                f"    • {ext_name} : {format_size_in_mb(ext_size)} "
                f"=> {ext_path.resolve()}"
            )
        print()


if __name__ == "__main__":
    main()