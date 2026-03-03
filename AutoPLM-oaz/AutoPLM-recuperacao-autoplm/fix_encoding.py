"""Fix emoji characters in Python files to prevent Windows cp1252 encoding crashes."""
import os

APP_DIR = r"c:\Users\USER\Downloads\oaz\FGcategoriaprodutooaz\app"

REPLACEMENTS = {
    '\u2714': '[OK]',    # ✔
    '\u2713': '[OK]',    # ✓
    '\u2705': '[OK]',    # ✅
    '\u274c': '[ERRO]',  # ❌
    '\u2716': '[X]',     # ✖
    '\u2717': '[X]',     # ✗
    '\u2718': '[X]',     # ✘
    '\u26a0\ufe0f': '[AVISO]',  # ⚠️
    '\u26a0': '[AVISO]',        # ⚠
    '\U0001f4e6': '[PKG]',      # 📦
    '\u2757': '[!]',     # ❗
    '\u2139\ufe0f': '[i]',      # ℹ️
    '\u2192': '->',      # →
    '\u2190': '<-',      # ←
    '\u2014': '--',      # —
}

fixed_count = 0

for root, dirs, files in os.walk(APP_DIR):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        for emoji, replacement in REPLACEMENTS.items():
            content = content.replace(emoji, replacement)
        
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            fixed_count += 1
            print(f"  FIXED: {os.path.relpath(fpath, APP_DIR)}")

# Also fix routes directory
ROUTES_DIR = os.path.join(APP_DIR, "routes")
print(f"\nTotal files fixed: {fixed_count}")
