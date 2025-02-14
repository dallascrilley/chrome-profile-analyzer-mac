#!/usr/bin/env python3

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CHROME_USER_DATA_DIR = Path(os.environ.get("CHROME_USER_DATA_DIR", Path.home() / "Library/Application Support/Google/Chrome"))


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


def get_profile_name(profile_dir: Path) -> str:
    """
    Given a Chrome profile directory, parse the friendly name from Preferences.
    If not found, default to folder name.
    """
    preferences_path = profile_dir / "Preferences"
    if not preferences_path.is_file():
        return profile_dir.name  # Fallback if no Preferences file

    try:
        with preferences_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("profile", {}).get("name", profile_dir.name)
    except (json.JSONDecodeError, OSError):
        return profile_dir.name


def get_extension_name(extension_version_dir: Path) -> str:
    """
    Find and parse the 'manifest.json' inside an extension's version folder.
    Prefer 'default_title'; otherwise fallback to 'name'. If neither is found, use folder name.
    """
    manifest_path = extension_version_dir / "manifest.json"
    if not manifest_path.is_file():
        return extension_version_dir.parent.name  # Use the extension ID folder name as fallback

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
        # Some manifests use 'default_title', some use 'name'
        if "default_title" in manifest:
            return manifest["default_title"]
        return manifest.get("name", extension_version_dir.parent.name)
    except (json.JSONDecodeError, OSError):
        return extension_version_dir.parent.name


def format_size_in_mb(size_bytes: int) -> str:
    # Convert bytes to megabytes using 1024*1024 as the conversion factor, formatted to 2 decimals.
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def enumerate_profiles(chrome_data_dir: Path) -> List[Path]:
    """
    Return a list of all valid Chrome profile directories under 'chrome_data_dir'.
    Typically these are named 'Profile 1', 'Profile 2', ... or 'Default'.
    """
    valid_profiles = []
    if not chrome_data_dir.is_dir():
        print(f"Could not find Chrome data directory at {chrome_data_dir}")
        return valid_profiles

    for item in chrome_data_dir.iterdir():
        if item.is_dir():
            # Common Chrome profiles are 'Default' or 'Profile N'
            # Adjust if you have Beta/Canary or custom-named profiles
            if item.name == "Default" or item.name.startswith("Profile "):
                valid_profiles.append(item)
    return valid_profiles


def main() -> None:
    profiles = enumerate_profiles(CHROME_USER_DATA_DIR)
    # Build a list of (profile_friendly_name, profile_path, profile_size)
    profile_info = []

    for profile_dir in profiles:
        friendly_name = get_profile_name(profile_dir)
        size_bytes = get_folder_size(profile_dir)
        profile_info.append((friendly_name, profile_dir, size_bytes))

    # Sort profiles by size descending
    profile_info.sort(key=lambda x: x[2], reverse=True)

    print("=== Chrome Profiles (sorted by size) ===")
    for friendly_name, profile_dir, prof_size in profile_info:
        print(f"- {friendly_name} [{profile_dir.name}] : {format_size_in_mb(prof_size)}")
        # Within each profile, examine Extensions folder
        extensions_dir = profile_dir / "Extensions"
        if not extensions_dir.is_dir():
            print("  (No Extensions directory found.)")
            continue

        # Gather extension info: (extension_friendly_name, total_size)
        extension_details = []
        for ext_id_folder in extensions_dir.iterdir():
            if not ext_id_folder.is_dir():
                continue

            # Each extension ID folder often has multiple version subfolders
            # We sum them up and choose the "manifest.json" from the largest or latest subfolder
            total_ext_size = 0
            ext_friendly_name: Optional[str] = None

            # You could pick the "largest" version folder or the "latest" version folder.
            # We'll just parse each version folder's manifest and pick the first friendly name found.
            for version_folder in ext_id_folder.iterdir():
                if version_folder.is_dir():
                    total_ext_size += get_folder_size(version_folder)
                    # If we haven't assigned a user-friendly name yet, parse it
                    if ext_friendly_name is None:
                        ext_friendly_name = get_extension_name(version_folder)

            # Fallback if no manifest found anywhere
            if not ext_friendly_name:
                ext_friendly_name = ext_id_folder.name

            extension_details.append((ext_friendly_name, total_ext_size))

        # Sort extensions by size descending
        extension_details.sort(key=lambda x: x[1], reverse=True)

        # Print extension details
        print("  Extensions (sorted by size):")
        for ext_name, ext_size in extension_details:
            print(f"    • {ext_name} : {format_size_in_mb(ext_size)}")
        print()

if __name__ == "__main__":
    main()