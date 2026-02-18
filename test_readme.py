#!/usr/bin/env python3
"""
Test script for README_test.md validation
Validates all acceptance criteria for Story US-001
"""

import os
import sys
import re
from pathlib import Path

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def test_file_exists():
    """AC 1: File README_test.md exists at repository root"""
    repo_root = Path(__file__).parent
    readme_path = repo_root / "README_test.md"
    
    if readme_path.exists():
        print(f"{GREEN}✓{RESET} AC 1: README_test.md exists")
        return True, str(readme_path)
    else:
        print(f"{RED}✗{RESET} AC 1: README_test.md does not exist")
        return False, None

def test_minimum_word_count(content):
    """AC 2: File contains project description with minimum 200 words"""
    # Remove markdown formatting and count words
    text_only = re.sub(r'```.*?```', '', content, flags=re.DOTALL)  # Remove code blocks
    text_only = re.sub(r'[#*`\-\[\]]', '', text_only)  # Remove markdown symbols
    words = text_only.split()
    word_count = len(words)
    
    if word_count >= 200:
        print(f"{GREEN}✓{RESET} AC 2: Word count = {word_count} (>= 200)")
        return True
    else:
        print(f"{RED}✗{RESET} AC 2: Word count = {word_count} (< 200)")
        return False

def test_required_sections(content):
    """AC 3: File includes required sections"""
    required_sections = [
        r'##\s+Overview',
        r'##\s+Features',
        r'##\s+Tech Stack',
        r'##\s+Project Structure',
        r'##\s+Quick Start'
    ]
    
    all_present = True
    for section in required_sections:
        if re.search(section, content, re.IGNORECASE):
            section_name = section.replace(r'##\s+', '')
            print(f"{GREEN}✓{RESET} AC 3: Section '{section_name}' found")
        else:
            section_name = section.replace(r'##\s+', '')
            print(f"{RED}✗{RESET} AC 3: Section '{section_name}' missing")
            all_present = False
    
    return all_present

def test_markdown_validity(content):
    """AC 4: Markdown is valid (basic validation)"""
    # Check for balanced code blocks
    code_block_count = content.count('```')
    if code_block_count % 2 != 0:
        print(f"{RED}✗{RESET} AC 4: Unbalanced code blocks (count: {code_block_count})")
        return False
    
    # Check for basic header syntax
    lines = content.split('\n')
    invalid_headers = []
    for i, line in enumerate(lines, 1):
        if line.startswith('#'):
            # Headers should have space after #
            if not re.match(r'^#{1,6}\s+\S', line):
                invalid_headers.append((i, line[:50]))
    
    if invalid_headers:
        print(f"{RED}✗{RESET} AC 4: Invalid header syntax at lines: {[h[0] for h in invalid_headers]}")
        return False
    
    print(f"{GREEN}✓{RESET} AC 4: Markdown syntax is valid")
    return True

def test_store_mentions(content):
    """AC 5: File mentions all three scrapers"""
    stores = ['Kaufland', 'Lidl', 'Billa']
    all_mentioned = True
    
    for store in stores:
        if store in content:
            print(f"{GREEN}✓{RESET} AC 5: Store '{store}' mentioned")
        else:
            print(f"{RED}✗{RESET} AC 5: Store '{store}' not mentioned")
            all_mentioned = False
    
    return all_mentioned

def test_sqlite_documentation(content):
    """AC 6: File documents SQLite database usage"""
    sqlite_keywords = [
        'SQLite',
        'database',
        'db_pipeline',
        'promobg.db'
    ]
    
    found_count = sum(1 for keyword in sqlite_keywords if keyword in content)
    
    if found_count >= 3:
        print(f"{GREEN}✓{RESET} AC 6: SQLite database usage documented ({found_count}/{len(sqlite_keywords)} keywords found)")
        return True
    else:
        print(f"{RED}✗{RESET} AC 6: Insufficient SQLite documentation ({found_count}/{len(sqlite_keywords)} keywords found)")
        return False

def test_utf8_encoding(file_path):
    """AC 9: File is UTF-8 encoded"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        print(f"{GREEN}✓{RESET} AC 7: File is valid UTF-8")
        return True
    except UnicodeDecodeError as e:
        print(f"{RED}✗{RESET} AC 7: File has UTF-8 encoding errors: {e}")
        return False

def test_comprehensive_content(content):
    """AC 8: Additional validation for comprehensive content"""
    # Check for code blocks (Quick Start section should have examples)
    code_blocks = re.findall(r'```.*?```', content, re.DOTALL)
    
    if len(code_blocks) >= 3:
        print(f"{GREEN}✓{RESET} AC 8: Comprehensive content with {len(code_blocks)} code examples")
        return True
    else:
        print(f"{RED}✗{RESET} AC 8: Insufficient code examples ({len(code_blocks)} < 3)")
        return False

def main():
    print(f"\n{BOLD}=== README_test.md Validation Tests ==={RESET}\n")
    
    results = []
    
    # Test 1: File exists
    exists, file_path = test_file_exists()
    results.append(exists)
    
    if not exists:
        print(f"\n{RED}{BOLD}FAILED:{RESET} Cannot proceed - README_test.md not found\n")
        return 1
    
    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"{RED}✗{RESET} Failed to read file: {e}")
        return 1
    
    # Test 2: Minimum word count
    results.append(test_minimum_word_count(content))
    
    # Test 3: Required sections
    results.append(test_required_sections(content))
    
    # Test 4: Markdown validity
    results.append(test_markdown_validity(content))
    
    # Test 5: Store mentions
    results.append(test_store_mentions(content))
    
    # Test 6: SQLite documentation
    results.append(test_sqlite_documentation(content))
    
    # Test 7: UTF-8 encoding
    results.append(test_utf8_encoding(file_path))
    
    # Test 8: Comprehensive content
    results.append(test_comprehensive_content(content))
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n{BOLD}=== Summary ==={RESET}")
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print(f"{GREEN}{BOLD}✓ ALL TESTS PASSED{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}✗ SOME TESTS FAILED{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
