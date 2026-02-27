"""
Sprint 3 Bulk Migration Script
Strips shared CSS/sidebar from dark standalone templates,
wraps content in layout.html blocks.
"""
import re
import os

TEMPLATE_DIR = r"c:\Users\USER\Downloads\oaz\FGcategoriaprodutooaz\templates"

# Templates to migrate (those still standalone)
TEMPLATES = [
    "admin_dashboard.html",
    "user_dashboard.html",
    "suppliers.html",
    "technical_drawings.html",
    "upload_pdf.html",
    "edit_specification.html",
    "view_specification.html",
    "view_collection.html",
    "oaz_banco_import.html",
    "ficha_tecnica_import.html",
    "ficha_tecnica_table.html",
    "ficha_tecnica_item_edit.html",
]

def is_shared_css(line):
    """Check if a CSS line is from the shared design system (sidebar/nav/layout/etc)"""
    shared_selectors = [
        '* {', 'body {', '.app-container', '.sidebar', '.logo', '.nav-menu',
        '.nav-item', '.user-profile', '.user-avatar', '.user-info', '.user-name',
        '.user-role', '.logout-btn', '.main-content', '.settings-section',
        '.settings-btn',
    ]
    stripped = line.strip()
    for sel in shared_selectors:
        if stripped.startswith(sel):
            return True
    return False

def extract_title(html):
    """Extract <title> content"""
    m = re.search(r'<title>(.*?)</title>', html)
    return m.group(1) if m else 'StyleFlow'

def find_style_boundaries(lines):
    """Find the <style> and </style> tag positions"""
    style_start = None
    style_end = None
    for i, line in enumerate(lines):
        if '<style>' in line and style_start is None:
            style_start = i
        if '</style>' in line and style_start is not None:
            style_end = i
            break
    return style_start, style_end

def find_sidebar_boundaries(lines):
    """Find sidebar start and end"""
    sidebar_start = None
    sidebar_end = None
    depth = 0
    for i, line in enumerate(lines):
        if '<aside' in line and 'sidebar' in line:
            sidebar_start = i
            depth = 1
        elif sidebar_start is not None and sidebar_end is None:
            depth += line.count('<aside') + line.count('<div')
            depth -= line.count('</aside') + line.count('</div')
            if '</aside>' in line:
                sidebar_end = i
                break
    return sidebar_start, sidebar_end

def find_main_content_start(lines):
    """Find <main class="main-content"> start"""
    for i, line in enumerate(lines):
        if '<main' in line and 'main-content' in line:
            return i
    return None

def find_scripts(lines):
    """Find all <script> blocks' content"""
    scripts = []
    in_script = False
    current_script = []
    for i, line in enumerate(lines):
        if '<script>' in line or '<script ' in line:
            in_script = True
            current_script = []
            # Include inline if <script> has content after tag
            after = line.split('<script>')[1] if '<script>' in line else ''
            if after.strip() and '</script>' not in after:
                current_script.append(after)
            continue
        if '</script>' in line:
            in_script = False
            before = line.split('</script>')[0]
            if before.strip():
                current_script.append(before)
            scripts.append('\n'.join(current_script))
            continue
        if in_script:
            current_script.append(line)
    return scripts

def find_modals(lines, main_end_idx):
    """Find modal divs after main content"""
    modals = []
    modal_start = None
    for i in range(main_end_idx, len(lines)):
        line = lines[i]
        if 'class="modal' in line and 'modal-overlay' not in line and '<div' in line:
            modal_start = i
        if modal_start is not None and '</div>' in line:
            # Check if this closes the modal (rough heuristic)
            pass
    return modals  # We'll handle modals inline with content

def extract_page_css(style_content):
    """
    Extract only page-specific CSS, removing shared sidebar/nav/layout styles.
    Uses a block-based approach: parse CSS rules and skip shared ones.
    """
    shared_selectors_starts = [
        '*', 'body', '.app-container', '.sidebar', '.logo ', '.logo img',
        '.logo span', '.logo-text', '.nav-menu', '.nav-item', '.nav-item:hover',
        '.nav-item.active', '.nav-item i', '.user-profile', '.user-avatar',
        '.user-info', '.user-name', '.user-role', '.logout-btn', '.logout-btn:hover',
        '.logout-btn i', '.main-content', '.settings-section', '.settings-btn',
        '.settings-btn:hover', '.settings-btn i', '.page-title', '.page-subtitle',
        '.header-top', '.page-header',
    ]
    
    # Parse blocks
    page_css_lines = []
    lines = style_content.split('\n')
    skip_depth = 0
    skipping = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check if this is a selector we should skip
        if not skipping and skip_depth == 0:
            should_skip = False
            for sel in shared_selectors_starts:
                if stripped.startswith(sel + ' {') or stripped.startswith(sel + '{') or stripped == sel + ' {' or stripped == sel + '{':
                    should_skip = True
                    break
                # Handle comma selectors
                if ',' in stripped:
                    parts = [p.strip() for p in stripped.rstrip('{').split(',')]
                    if all(any(p.startswith(s) for s in shared_selectors_starts) for p in parts if p):
                        should_skip = True
                        break
            
            if should_skip:
                skipping = True
                skip_depth = stripped.count('{') - stripped.count('}')
                if skip_depth <= 0:
                    skipping = False
                    skip_depth = 0
                continue
        
        if skipping:
            skip_depth += stripped.count('{') - stripped.count('}')
            if skip_depth <= 0:
                skipping = False
                skip_depth = 0
            continue
        
        page_css_lines.append(line)
    
    result = '\n'.join(page_css_lines).strip()
    return result

def migrate_template(filename):
    filepath = os.path.join(TEMPLATE_DIR, filename)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Skip if already migrated
    if '{% extends' in content:
        print(f"  SKIP {filename} -- already migrated")
        return False
    
    lines = content.split('\n')
    title = extract_title(content)
    
    # Find boundaries
    style_start, style_end = find_style_boundaries(lines)
    main_start = find_main_content_start(lines)
    
    if main_start is None:
        print(f"  ERROR {filename} -- no <main> found")
        return False
    
    # Extract style content (between <style> and </style>)
    if style_start is not None and style_end is not None:
        style_lines = lines[style_start+1:style_end]
        style_content = '\n'.join(style_lines)
        page_css = extract_page_css(style_content)
    else:
        page_css = ''
    
    # Extract main content (from <main...> to </main>)
    main_end = None
    for i in range(len(lines)-1, main_start, -1):
        if '</main>' in lines[i]:
            main_end = i
            break
    
    if main_end is None:
        print(f"  ERROR {filename} -- no </main> found")
        return False
    
    # Get content between <main> and </main>
    main_content_lines = lines[main_start+1:main_end]
    main_content = '\n'.join(main_content_lines)
    
    # Remove one level of indentation (content was inside <main>)
    dedented_lines = []
    for line in main_content_lines:
        if line.startswith('            '):
            dedented_lines.append(line[12:])
        elif line.startswith('        '):
            dedented_lines.append(line[8:])
        elif line.startswith('    '):
            dedented_lines.append(line[4:])
        else:
            dedented_lines.append(line)
    main_content = '\n'.join(dedented_lines)
    
    # Extract scripts (after </main>)
    script_lines = lines[main_end:]
    scripts = find_scripts(script_lines)
    
    # Also check for scripts within main content
    main_scripts = find_scripts(main_content_lines)
    
    # Check for modals (divs with class="modal" after main)
    post_main = '\n'.join(lines[main_end+1:])
    modal_content = ''
    # Find modal divs
    modal_matches = re.findall(r'(<div class="modal.*?</div>\s*</div>)', post_main, re.DOTALL)
    if modal_matches:
        modal_content = '\n'.join(modal_matches)
    
    # Build new template
    output_parts = []
    output_parts.append('{%- extends "layout.html" -%}')
    output_parts.append('')
    output_parts.append(f'{{% block title %}}{title}{{% endblock %}}')
    output_parts.append('')
    
    if page_css.strip():
        output_parts.append('{% block styles %}')
        output_parts.append('<style>')
        output_parts.append(page_css)
        output_parts.append('</style>')
        output_parts.append('{% endblock %}')
        output_parts.append('')
    
    output_parts.append('{% block content %}')
    output_parts.append(main_content)
    output_parts.append('{% endblock %}')
    
    all_scripts = scripts + main_scripts
    if all_scripts:
        output_parts.append('')
        output_parts.append('{% block scripts %}')
        for script in all_scripts:
            output_parts.append('<script>')
            output_parts.append(script)
            output_parts.append('</script>')
        output_parts.append('{% endblock %}')
    
    new_content = '\n'.join(output_parts)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    old_lines = len(lines)
    new_lines = len(new_content.split('\n'))
    print(f"  OK {filename}: {old_lines} -> {new_lines} lines (removed {old_lines - new_lines} lines)")
    return True

def main():
    print("Sprint 3 -- Bulk Template Migration")
    print("=" * 50)
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for tmpl in TEMPLATES:
        try:
            result = migrate_template(tmpl)
            if result:
                migrated += 1
            elif result is False:
                skipped += 1
        except Exception as e:
            print(f"  FAIL {tmpl}: {e}")
            errors += 1
    
    print("=" * 50)
    print(f"Done: {migrated} migrated, {skipped} skipped, {errors} errors")

if __name__ == '__main__':
    main()
