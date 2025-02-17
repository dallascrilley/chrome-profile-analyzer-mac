## Chrome Profile Analyzer

Chrome Profiles and extensions can take up a lot of space on your Mac. Unfortunately, there is not a straightforward way to see what is taking up the space. 

Chrome Profile Analyzer is a Python-based tool designed to help you see what is taking up space in your Chrome profiles. It parses and analyzes Google Chrome user profiles. It extracts useful information such as friendly profile names, folder sizes, and details about installed extensions. The tool leverages JSON parsing and file system traversal to build a detailed report of your Chrome profiles.

---

## Features

- **Profile Name Resolution:**  
  Extracts a user-friendly name for each Chrome profile using data from both the `Preferences` file and the `Local State` file. Falls back to the directory name if necessary.

- **Profile Size Calculation:**  
  Recursively calculates the total disk usage of each profile, formatted in megabytes.

- **Extension Analysis:**  
  Enumerates installed extensions, resolves their names (including i18n placeholder resolution), and computes their sizes.

- **Sorting & Reporting:**  
  Lists profiles and extensions sorted by size in descending order for quick insights into disk usage.

---

## Requirements

- **Python 3.8+**

- **Standard Libraries:**  
  The project uses built-in modules (`os`, `json`, `pathlib`, `typing`) and does not require any external dependencies.

---

## Usage

1. **Set the Environment Variable (Optional):**  
   If you have a custom Chrome user data directory, set the `CHROME_USER_DATA_DIR` environment variable.  
   ```bash
   export CHROME_USER_DATA_DIR="/path/to/chrome/user/data"

2. **Run the Script:**
    Simply run the script in your terminal.
    ```bash
    python chrome-profile-analyzer.py
    ```

    The script will output a list of Chrome profiles with their friendly names, sizes, and extension details.

## Debugging

The project includes a simple debug mechanism controlled by the global DEBUG flag. Set DEBUG = True in the script to enable verbose output for troubleshooting.

## License

This project is licensed under the MIT License.

## Author
- **Name**: Dallas Crilley
- **Website**: [dallascrilley.com](https://dallascrilley.com)
