## Chrome Profile Analyzer

Chrome Profiles and their extensions can take up a lot of space on your Mac. Unfortunately, there is not a straightforward way to see what is taking up that space. 

**Chrome Profile Analyzer** is a Python-based CLI tool that helps you visualize disk usage for each of your Chrome profiles. It parses Google Chrome’s user profiles, locates friendly profile names, calculates disk usage, and extracts details about installed extensions. The tool uses JSON parsing and file system traversal to build detailed usage reports, and now provides several command-line options for customized output.

---
## Features

### 1. Profile Name Resolution
- Derives user-friendly names from each Chrome profile by reading both the Preferences file and the Local State file.
- Falls back to the directory name if no user-friendly name is found.

### 2. Profile & Extension Size Calculation
- Recursively calculates total disk usage for each profile, displayed in MB.
- Enumerates and computes extension sizes, including all version subfolders.

### 3. Threshold-Based Skipping
- Skip listing profiles or extensions smaller than a user-defined minimum size (default 50 MB).
- Displays a note indicating if items were skipped because they were under the threshold.

### 4. Sorting & Reporting
- Lists profiles and extensions sorted by size in descending order.
- Provides overall summary statistics:
  - Total number of profiles scanned
  - Total disk usage across all profiles
  - Top 5 largest extensions (globally)

### 5. Export Options
- **JSON Output**: `--json` for a machine-readable JSON dump of all results.
- **CSV Output**: `--csv` for a row-by-row CSV export.

### 6. Colorized Output
- Profiles or extensions over 1 GB are highlighted in red (ANSI escape codes) in human-readable mode.

### 7. Help & Usage
- `--help` displays usage instructions and a summary of all available command-line arguments.

### 8. Logging
- Uses Python’s built-in logging module.
- `--debug` sets the logger to `DEBUG` level for verbose output. Otherwise, you can specify `--log-level INFO`, `--log-level WARNING`, etc.

---

## Requirements

- Python 3.8+
- Standard Libraries (`os`, `json`, `pathlib`, `typing`, `argparse`, `logging`, `csv`)
- **Optional**: `colorama` for cross-platform color support. On many terminals, ANSI colors work fine without it. If you are on Windows, installing `colorama` is recommended for proper color output.

---

## Usage

```sh
pip install -r requirements.txt
```

After installing the dependencies, the script can be run as follows:

```sh
python chrome-profile-analyzer.py [options]
```

The script will output a list of Chrome profiles with their friendly names, sizes, and extension details.

### Command-Line Arguments

| Argument          | Description                                                | Default                                                      |
|-------------------|------------------------------------------------------------|--------------------------------------------------------------|
| --chrome-data-dir | Path to the Chrome User Data directory.                   | ~/Library/Application Support/Google/Chrome (macOS)          |
| --debug           | Enable debug logging (overrides --log-level).             | Disabled                                                     |
| --log-level       | Set logging level (DEBUG, INFO, WARNING, etc.).            | INFO                                                         |
| --min-size-mb     | Minimum size (in MB) to display profiles/extensions.       | 50.0                                                         |
| --json            | Output data in JSON format (overrides human-readable output). | Disabled                                                     |
| --csv             | Output data in CSV format (overrides human-readable output). | Disabled                                                     |
| --help            | Show usage instructions and available arguments.         | -                                                            |

### Examples

1. **Basic usage (human-readable output):**

```sh
python chrome-profile-analyzer.py
```

   • Scans the default Chrome user data directory and prints profiles/extensions ≥ 50 MB.

2. **Specify a custom Chrome data directory:**

```sh
python chrome-profile-analyzer.py --chrome-data-dir "/path/to/chrome/user/data"
```

3. **Enable debug logging:**

```sh
python chrome-profile-analyzer.py --debug
```

or

```sh
python chrome-profile-analyzer.py --log-level DEBUG
```

4. **Skip profiles/extensions under 100 MB:**

```sh
python chrome-profile-analyzer.py --min-size-mb 100
```

5. **Export output to JSON:**

```sh
python chrome-profile-analyzer.py --json > profiles.json
```

6. **Export output to CSV:**

```sh
python chrome-profile-analyzer.py --csv > profiles.csv
```

### Output Examples

#### Human-Readable (Default)

Displays each profile’s name, path, and size, followed by its extensions. Over-1GB items are highlighted in red.

#### JSON Output

A JSON list of profiles, where each profile contains:

```json
[
  {
    "profile_name": "My Profile",
    "profile_dir": "/Users/John/Library/Application Support/Google/Chrome/Profile 1",
    "profile_size_bytes": 123456789,
    "profile_size_mb": 117.74,
    "extensions": [
      {
        "extension_name": "AdBlock",
        "extension_dir": "/Users/John/Library/Application Support/Google/Chrome/Profile 1/Extensions/...",
        "extension_size_bytes": 321654,
        "extension_size_mb": 0.31,
        "profile_name": "My Profile"
      }
    ]
  }
]
```

#### CSV Output

Each row corresponds to a single extension. Profiles with no extensions (or whose extensions are below the threshold) will appear as a single row with empty extension fields.

## Debugging

The tool uses Python’s built-in logging system. You can specify a log level for more detailed output:

```sh
python chrome-profile-analyzer.py --log-level DEBUG
```

If you just want a quick toggle for verbose output, use:

```sh
python chrome-profile-analyzer.py --debug
```
## License

This project is licensed under the MIT License.

## Author
- **Name**: Dallas Crilley
- **Website**: [dallascrilley.com](https://dallascrilley.com)
