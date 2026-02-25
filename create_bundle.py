"""
OAZ StyleSheet PLM - Bundle Generator
======================================
Generates a single bundle.txt with all project source files.
"""

import os
import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "bundle.txt")

# Extensions to include
INCLUDE_EXTENSIONS = {
    '.py', '.html', '.css', '.js', '.json', '.md', '.txt',
    '.toml', '.cfg', '.ini', '.yml', '.yaml',
}

# Files/dirs to exclude
EXCLUDE_DIRS = {
    '__pycache__', '.git', '.pytest_cache', '.venv', 'venv',
    'node_modules', '.replit', 'uploads', 'attached_assets',
    'thumbnails', 'drawings', 'covers', 'product_images', 'images',
}

EXCLUDE_FILES = {
    'bundle.txt', 'filelist.txt', 'filelist_filtered.txt',
    'uv.lock', 'flux_retorno_raw.html', 'logfile.txt',
    '_inspect_output.txt', 'tmp_test.py', 'replit.md',
}

# Skip files larger than 100KB
MAX_FILE_SIZE = 100 * 1024


def should_include(filepath, filename):
    """Determine if a file should be included in the bundle."""
    if filename in EXCLUDE_FILES:
        return False
    if filename.startswith('.'):
        return False
    _, ext = os.path.splitext(filename)
    if ext not in INCLUDE_EXTENSIONS:
        return False
    if os.path.getsize(filepath) > MAX_FILE_SIZE:
        return False
    return True


def collect_files():
    """Walk the project tree and collect files to bundle."""
    files = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # Filter out excluded directories (in-place)
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS
        ]
        dirnames.sort()

        for filename in sorted(filenames):
            filepath = os.path.join(dirpath, filename)
            if should_include(filepath, filename):
                relpath = os.path.relpath(filepath, PROJECT_ROOT)
                files.append((relpath, filepath))
    return files


def main():
    files = collect_files()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        # Header
        out.write("=" * 80 + "\n")
        out.write("OAZ StyleSheet PLM - Project Bundle\n")
        out.write(f"Generated: {now}\n")
        out.write(f"Total files: {len(files)}\n")
        out.write("Description: Complete project source code bundle\n")
        out.write("=" * 80 + "\n\n")

        # Index
        out.write("PROJECT FILE INDEX\n")
        out.write("-" * 40 + "\n")
        for i, (relpath, _) in enumerate(files, 1):
            out.write(f"  {i:3d}. {relpath}\n")
        out.write("-" * 40 + "\n\n")

        # File contents
        for relpath, filepath in files:
            out.write("=" * 80 + "\n")
            out.write(f"FILE: {relpath}\n")
            out.write("=" * 80 + "\n")
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                out.write(content)
                if not content.endswith('\n'):
                    out.write('\n')
            except Exception as e:
                out.write(f"[ERROR reading file: {e}]\n")
            out.write("\n\n")

    print(f"Bundle generated: {OUTPUT_FILE}")
    print(f"Total files bundled: {len(files)}")
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"Bundle size: {size_kb:.1f} KB")


if __name__ == '__main__':
    main()
