#!/usr/bin/env python3
"""
Markdown Validation Test for README_test.md

Tests all acceptance criteria for README_test.md validation.
Script validates the structure, format, and completeness of README_test.md.

Usage:
    python3 test_readme_test.py

Exit Codes:
    0: All tests passed
    1: One or more tests failed
"""

import os
import sys
import re
from typing import Tuple, List

# ANSI Color Codes
GREEN = '\033[32m'
RED = '\033[31m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Constants
README_PATH = "/home/node/.openclaw/workspace/promo_products_bg/README_test.md"
REQUIRED_SECTIONS = ["Features", "Technology Stack", "Project Structure"]
REQUIRED_STORES = ["Kaufland", "Lidl", "Billa"]
MIN_FILE_SIZE = 0  # bytes
MIN_WORD_COUNT = 200  # words


def test_file_exists() -> Tuple[bool, str]:
    """
    AC 4: Verify README_test.md exists in repository root.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not os.path.exists(README_PATH):
        return False, f"File does not exist: {README_PATH}"
    if not os.path.isfile(README_PATH):
        return False, f"Path is not a file: {README_PATH}"
    if not os.access(README_PATH, os.R_OK):
        return False, f"File is not readable: {README_PATH}"
    return True, f"File exists and is readable: {README_PATH}"


def test_minimum_word_count() -> Tuple[bool, str]:
    """
    AC 5: Count words and verify >= 200.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        words = content.split()
        word_count = len(words)
        if word_count < MIN_WORD_COUNT:
            return False, f"Insufficient word count: {word_count} words (minimum {MIN_WORD_COUNT} required)"
        return True, f"Word count: {word_count} words (exceeds minimum of {MIN_WORD_COUNT})"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_required_sections() -> Tuple[bool, str]:
    """
    AC 6: Regex match for all 5 required sections.
    Required sections: Features, Technology Stack, Project Structure, Matching Pipeline, Database
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for 5 required sections
        all_required = ["Features", "Technology Stack", "Project Structure", "Matching Pipeline", "Database"]
        missing_sections: List[str] = []
        found_sections: List[str] = []
        
        for section in all_required:
            pattern = rf'^#+ {re.escape(section)}'
            if re.search(pattern, content, re.MULTILINE):
                found_sections.append(section)
            else:
                missing_sections.append(section)
        
        if missing_sections:
            return False, f"Missing required sections: {', '.join(missing_sections)}"
        return True, f"All 5 required sections present: {', '.join(found_sections)}"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_markdown_validity() -> Tuple[bool, str]:
    """
    AC 7: Check balanced code blocks and header syntax.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        issues: List[str] = []
        code_block_count = 0
        
        for i, line in enumerate(lines, start=1):
            if re.match(r'^#{1,6}[^ #]', line):
                issues.append(f"Line {i}: Header missing space after #")
            if line.strip().startswith('```'):
                code_block_count += 1
        
        if code_block_count % 2 != 0:
            issues.append(f"Unbalanced code blocks (found {code_block_count} ``` markers)")
        
        if issues:
            return False, f"Markdown syntax issues: {'; '.join(issues)}"
        return True, f"Markdown syntax valid ({code_block_count // 2} code blocks)"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_store_mentions() -> Tuple[bool, str]:
    """
    AC 8: Verify all three stores are mentioned (Kaufland, Lidl, Billa).
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        missing_stores: List[str] = []
        found_stores: List[str] = []
        
        for store in REQUIRED_STORES:
            if store in content:
                found_stores.append(store)
            else:
                missing_stores.append(store)
        
        if missing_stores:
            return False, f"Missing store names: {', '.join(missing_stores)}"
        return True, f"All three stores mentioned: {', '.join(found_stores)}"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_sqlite_documentation() -> Tuple[bool, str]:
    """
    AC 9: Check for SQLite-related keywords.
    Keywords: SQLite, database, promobg.db, off_bulgaria.db
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        sqlite_keywords = ["SQLite", "database", "promobg.db", "off_bulgaria.db"]
        found_keywords: List[str] = []
        missing_keywords: List[str] = []
        
        for keyword in sqlite_keywords:
            if keyword.lower() in content.lower():
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)
        
        if len(found_keywords) < 2:  # At least 2 keywords should be present
            return False, f"Insufficient SQLite documentation. Missing: {', '.join(missing_keywords)}"
        return True, f"SQLite documentation present. Found: {', '.join(found_keywords)}"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_utf8_encoding() -> Tuple[bool, str]:
    """
    AC 10: Attempt UTF-8 decode and catch errors.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        if not content:
            return False, "File is empty"
        return True, f"File is valid UTF-8 ({len(content)} characters)"
    except UnicodeDecodeError as e:
        return False, f"Invalid UTF-8 encoding: {e}"
    except OSError as e:
        return False, f"Failed to read file: {e}"


def test_comprehensive_content() -> Tuple[bool, str]:
    """
    AC 11: Verify code examples present.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        code_blocks = len(re.findall(r'```[\s\S]*?```', content))
        paragraphs = len([line for line in content.split('\n') if line.strip() and not line.strip().startswith('#')])
        lists = len(re.findall(r'^[-*+] .+', content, re.MULTILINE))
        
        if code_blocks < 1:
            return False, f"No code examples found (found {code_blocks} code blocks)"
        if paragraphs < 5:
            return False, f"Insufficient content: only {paragraphs} non-header lines"
        return True, f"Comprehensive content: {paragraphs} lines, {code_blocks} code blocks, {lists} list items"
    except OSError as e: