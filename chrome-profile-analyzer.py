#!/usr/bin/env python3
import os
import json
import csv
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    import colorama
    colorama.init()  # Initialize colorama for Windows support
except ImportError:
    # If colorama not installed, we'll just use raw ANSI codes below.
    pass

###############################################################################
# GLOBAL DEFAULT PATHS
###############################################################################
DEFAULT_CHROME_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome"
LOCAL_STATE_FILENAME = "Local State"

###############################################################################
# ARGUMENT PARSING
###############################################################################
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List Chrome Profiles and Extension sizes with optional JSON/CSV export."
    )
    parser.add_argument(
        "--chrome-data-dir",
        type=str,
        default=str(DEFAULT_CHROME_USER_DATA_DIR),
        help="Path to the Chrome User Data directory (default on macOS)."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides --log-level)."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."
    )
    parser.add_argument(
        "--min-size-mb",
        type=float,
        default=50.0,
        help="Minimum size threshold in MB for displaying profiles/extensions. Default=50.0"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output data in JSON format instead of human-readable text."
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output data in CSV format instead of human-readable text."
    )
    return parser.parse_args()

###############################################################################
# LOGGING SETUP
###############################################################################
def setup_logging(args: argparse.Namespace) -> None:
    # If --debug is present, force DEBUG level
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        return

    # Otherwise, respect --log-level
    log_level_str = args.log_level.upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(level=numeric_level)

###############################################################################
# FILE & JSON LOADING HELPERS
###############################################################################
def load_json_file(file_path: Path) -> Optional[Any]:
    """Return JSON data from a file, or None if file doesn't exist or fails to parse."""
    if not file_path.is_file():
        logging.debug(f"JSON file not found: {file_path}")
        return None
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.debug(f"Error reading JSON from {file_path}: {e}")
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
        int(name.replace("person ", ""))  # e.g. "Person 1"
        return True
    except ValueError:
        return False

###############################################################################
# PROFILE NAME DERIVATION
###############################################################################
def build_pretty_name_from_prefs(prefs: dict) -> Optional[str]:
    """
    Attempt to derive a user-friendly name from Preferences:
      - prefs["profile"]["name"] if not generic
      - or "gaia_name" / "user_name"
      - or from "account_info"
    """
    profile_section = prefs.get("profile", {})

    # 1) Check 'profile->name' if not generic
    raw_name = profile_section.get("name")
    if raw_name and not is_generic_person_name(raw_name):
        logging.debug(f"Using profile->name = {raw_name}")
        return raw_name

    # 2) Check gaia_name / user_name
    for key in ("gaia_name", "user_name"):
        val = profile_section.get(key)
        if val and not is_generic_person_name(val):
            logging.debug(f"Using {key} = {val}")
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
        logging.debug(f"Using info_cache => {raw_name}")
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
# SIZE / ENUMERATION HELPERS
###############################################################################
def enumerate_profiles(chrome_data_dir: Path) -> List[Path]:
    """Return paths for all Chrome profiles in the data dir (Default + Profile X...)."""
    if not chrome_data_dir.is_dir():
        logging.warning(f"Could not find Chrome data directory at {chrome_data_dir}")
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

def format_size_in_mb(size_bytes: int) -> float:
    """Convert bytes to MB (1024 * 1024)."""
    return size_bytes / (1024 * 1024)

###############################################################################
# COLORING HELPER
###############################################################################
def color_if_large(size_mb: float, text: str) -> str:
    """
    If size_mb > 1 GB (1024 MB), color text in red.
    Adjust threshold or coloring as needed.
    """
    if size_mb > 1024.0:  # 1GB
        return f"\033[91m{text}\033[0m"  # Red
    return text

###############################################################################
# MAIN DATA GATHERING
###############################################################################
def gather_profiles_and_extensions(
    chrome_data_dir: Path,
    min_size_mb: float
) -> Tuple[List[dict], List[dict]]:
    """
    Enumerate profiles in chrome_data_dir, collect their sizes,
    and gather extension info. Skip details if below min_size_mb.
    
    Returns:
      (profile_list, extension_list) 
      where profile_list is a list of dict with:
        {
          "profile_name": str,
          "profile_dir": str,
          "profile_size_bytes": int,
          "extensions": [ ... ]
        }
      and extension_list is a flattened list of all extensions for global comparisons.
    """
    local_state_file = chrome_data_dir / LOCAL_STATE_FILENAME
    info_cache_map = load_info_cache_map(local_state_file)

    profiles_paths = enumerate_profiles(chrome_data_dir)
    result_profiles = []
    all_extensions = []

    for profile_dir in profiles_paths:
        profile_name = get_profile_name(profile_dir, info_cache_map)
        prof_size_bytes = get_folder_size(profile_dir)
        prof_size_mb = format_size_in_mb(prof_size_bytes)

        # Collect extension info
        exts_dir = profile_dir / "Extensions"
        extensions_data = []
        if exts_dir.is_dir():
            for ext_id_folder in exts_dir.iterdir():
                if not ext_id_folder.is_dir():
                    continue

                total_ext_size = 0
                ext_name_candidate: Optional[str] = None

                # Sum all version folders
                for version_folder in sorted([d for d in ext_id_folder.iterdir() if d.is_dir()]):
                    version_size = get_folder_size(version_folder)
                    total_ext_size += version_size
                    nm = get_extension_name(version_folder)
                    # If no name yet or if it's a placeholder, prefer a real name
                    if ext_name_candidate is None or ext_name_candidate.startswith("__MSG_"):
                        ext_name_candidate = nm

                ext_name = ext_name_candidate or ext_id_folder.name
                ext_size_bytes = total_ext_size
                ext_size_mb = format_size_in_mb(ext_size_bytes)

                # Skip extension if below threshold
                if ext_size_mb < min_size_mb:
                    continue

                extension_dict = {
                    "extension_name": ext_name,
                    "extension_dir": str(ext_id_folder.resolve()),
                    "extension_size_bytes": ext_size_bytes,
                    "extension_size_mb": ext_size_mb,
                    "profile_name": profile_name,
                }
                extensions_data.append(extension_dict)
                all_extensions.append(extension_dict)

        # Skip profile if below threshold
        if prof_size_mb < min_size_mb:
            continue

        profile_dict = {
            "profile_name": profile_name,
            "profile_dir": str(profile_dir.resolve()),
            "profile_size_bytes": prof_size_bytes,
            "profile_size_mb": prof_size_mb,
            "extensions": extensions_data,
        }
        result_profiles.append(profile_dict)

    return result_profiles, all_extensions

###############################################################################
# OUTPUT FORMATTING (TEXT, JSON, CSV)
###############################################################################
def print_human_readable(
    profiles: List[dict],
    all_extensions: List[dict]
) -> None:
    """
    Print profiles and extensions in a human-readable text format.
    Also prints summary: total profiles, total usage, top 5 largest extensions.
    """
    if not profiles:
        print("No profiles found or none above the specified threshold.")
        return

    # Sort profiles by size descending
    profiles_sorted = sorted(
        profiles,
        key=lambda x: x["profile_size_bytes"],
        reverse=True
    )

    print("\n=== Chrome Profiles (sorted by size) ===")
    for prof in profiles_sorted:
        prof_mb_str = f"{prof['profile_size_mb']:.2f} MB"
        colored_prof_mb_str = color_if_large(prof["profile_size_mb"], prof_mb_str)
        print(f"- {prof['profile_name']} [{prof['profile_dir']}] : {colored_prof_mb_str}")

        # Sort extensions by size descending
        extensions_sorted = sorted(
            prof["extensions"],
            key=lambda x: x["extension_size_bytes"],
            reverse=True
        )
        if not extensions_sorted:
            print("  (No Extensions or all under threshold)\n")
            continue

        print("  Extensions (sorted by size):")
        for ext in extensions_sorted:
            ext_mb_str = f"{ext['extension_size_mb']:.2f} MB"
            colored_ext_mb_str = color_if_large(ext["extension_size_mb"], ext_mb_str)
            print(f"    • {ext['extension_name']}: {colored_ext_mb_str} => {ext['extension_dir']}")
        print()

    # Summaries
    total_profiles = len(profiles)
    total_usage_bytes = sum(p["profile_size_bytes"] for p in profiles)
    total_usage_mb = total_usage_bytes / (1024 * 1024)
    print(f"Total profiles displayed: {total_profiles}")
    print(f"Total disk usage (above threshold): {total_usage_mb:.2f} MB")

    if all_extensions:
        # Sort globally for top 5
        sorted_extensions = sorted(all_extensions, key=lambda x: x["extension_size_bytes"], reverse=True)
        top_5_ext = sorted_extensions[:5]
        print("\nTop 5 Largest Extensions (global):")
        for ext in top_5_ext:
            ext_mb_str = f"{ext['extension_size_mb']:.2f} MB"
            colored_ext_mb_str = color_if_large(ext["extension_size_mb"], ext_mb_str)
            print(f"  • {ext['extension_name']}: {colored_ext_mb_str} (Profile: {ext['profile_name']})")
    print()

def output_json(profiles: List[dict]) -> None:
    """Dump profiles data as JSON."""
    print(json.dumps(profiles, indent=2))

def output_csv(profiles: List[dict]) -> None:
    """
    Dump CSV rows. 
    One row per extension. If a profile has no extensions, we still output one row with just profile info.
    """
    csv_writer = csv.writer(os.sys.stdout)
    # Write header
    csv_writer.writerow([
        "profile_name", "profile_dir", "profile_size_mb",
        "extension_name", "extension_dir", "extension_size_mb"
    ])

    for prof in profiles:
        # If no extensions, output a row with empty extension fields
        if not prof["extensions"]:
            csv_writer.writerow([
                prof["profile_name"],
                prof["profile_dir"],
                f"{prof['profile_size_mb']:.2f}",
                "",  # ext name
                "",  # ext dir
                ""   # ext size
            ])
        else:
            for ext in prof["extensions"]:
                csv_writer.writerow([
                    prof["profile_name"],
                    prof["profile_dir"],
                    f"{prof['profile_size_mb']:.2f}",
                    ext["extension_name"],
                    ext["extension_dir"],
                    f"{ext['extension_size_mb']:.2f}",
                ])

###############################################################################
# MAIN
###############################################################################
def main() -> None:
    args = parse_args()
    setup_logging(args)

    # Gather data
    chrome_data_dir = Path(args.chrome_data_dir)
    min_size_mb = args.min_size_mb

    profiles_data, all_extensions_data = gather_profiles_and_extensions(
        chrome_data_dir=chrome_data_dir,
        min_size_mb=min_size_mb
    )

    # Output
    if args.json:
        output_json(profiles_data)
    elif args.csv:
        output_csv(profiles_data)
    else:
        print_human_readable(profiles_data, all_extensions_data)

if __name__ == "__main__":
    main()