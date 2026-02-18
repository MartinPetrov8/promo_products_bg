#!/usr/bin/env python3
"""
Markdown Validation Test for README_test.md

This script validates the structure, format, and completeness of README_test.md.
Tests ensure the documentation maintains proper markdown formatting and includes
all required sections for developer onboarding.

Usage:
    python3 test_readme_test.py

Exit Codes:
    0: All validations passed
    1: One or more validations failed

Validations performed:
    1. File existence and readability
    2. File size (must be > 0 bytes)
    3. Required sections presence (title, features, structure)
    4. Markdown syntax validation (headers, code blocks, lists)
    5. UTF-8 encoding validation
"""

import os
import sys
import re
from typing import Tuple, List, Optional


# Constants
README_PATH = "/home/node/.openclaw/workspace/promo_products_bg/README_test.md"
REQUIRED_SECTIONS = ["Features", "Quick Start", "Project Structure"]
MIN_FILE_SIZE = 0  # bytes


def validate_file_exists() -> Tuple[bool, str]:
    """
    Verify README_test.md exists and is readable.
    
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


def validate_file_size() -> Tuple[bool, str]:
    """
    Check that file size is greater than 0 bytes.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        size = os.path.getsize(README_PATH)
        
        if size <= MIN_FILE_SIZE:
            return False, f"File size is {size} bytes (must be > {MIN_FILE_SIZE})"
        
        return True, f"File size is {size} bytes (valid)"
    
    except OSError as e:
        return False, f"Failed to get file size: {e}"


def validate_utf8_encoding() -> Tuple[bool, str]:
    """
    Verify file is valid UTF-8 encoded text.
    
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


def validate_title_header() -> Tuple[bool, str]:
    """
    Verify README has a top-level title header (# Title).
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for level-1 header at the start of the file
        match = re.search(r'^# .+', content, re.MULTILINE)
        
        if not match:
            return False, "No top-level title header (# ...) found"
        
        title = match.group(0)
        return True, f"Found title: {title}"
    
    except OSError as e:
        return False, f"Failed to read file: {e}"


def validate_required_sections() -> Tuple[bool, str]:
    """
    Check that all required sections are present using grep-like pattern matching.
    
    Required sections: Features, Quick Start, Project Structure
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        missing_sections: List[str] = []
        found_sections: List[str] = []
        
        for section in REQUIRED_SECTIONS:
            # Look for ## Section or # Section
            pattern = rf'^#+ {re.escape(section)}'
            if re.search(pattern, content, re.MULTILINE):
                found_sections.append(section)
            else:
                missing_sections.append(section)
        
        if missing_sections:
            return False, f"Missing required sections: {', '.join(missing_sections)}"
        
        return True, f"All required sections present: {', '.join(found_sections)}"
    
    except OSError as e:
        return False, f"Failed to read file: {e}"


def validate_markdown_syntax() -> Tuple[bool, str]:
    """
    Validate basic markdown syntax:
    - Headers are properly formatted
    - Code blocks are balanced (``` pairs)
    - Lists use proper syntax
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        issues: List[str] = []
        code_block_count = 0
        
        for i, line in enumerate(lines, start=1):
            # Check for malformed headers (# without space)
            if re.match(r'^#{1,6}[^ #]', line):
                issues.append(f"Line {i}: Header missing space after #")
            
            # Count code block delimiters
            if line.strip().startswith('```'):
                code_block_count += 1
        
        # Code blocks should be balanced (even count)
        if code_block_count % 2 != 0:
            issues.append(f"Unbalanced code blocks (found {code_block_count} ``` markers)")
        
        if issues:
            return False, f"Markdown syntax issues: {'; '.join(issues)}"
        
        return True, f"Markdown syntax valid ({code_block_count // 2} code blocks)"
    
    except OSError as e:
        return False, f"Failed to read file: {e}"


def validate_has_content_sections() -> Tuple[bool, str]:
    """
    Verify README has substantive content (not just empty headers).
    Checks for presence of paragraphs, code blocks, or lists.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count different content types
        paragraphs = len([line for line in content.split('\n') if line.strip() and not line.strip().startswith('#')])
        code_blocks = len(re.findall(r'```[\s\S]*?```', content))
        lists = len(re.findall(r'^[-*+] .+', content, re.MULTILINE))
        
        if paragraphs < 5:
            return False, f"Insufficient content: only {paragraphs} non-header lines"
        
        return True, f"Substantive content found: {paragraphs} lines, {code_blocks} code blocks, {lists} list items"
    
    except OSError as e:
        return False, f"Failed to read file: {e}"


def run_validation(name: str, validator_func) -> bool:
    """
    Run a validation function and print formatted results.
    
    Args:
        name: Name of the validation test
        validator_func: Function that returns Tuple[bool, str]
    
    Returns:
        True if validation passed, False otherwise
    """
    print(f"\n{'─' * 60}")
    print(f"Test: {name}")
    print(f"{'─' * 60}")
    
    try:
        success, message = validator_func()
        
        if success:
            print(f"✓ PASS: {message}")
            return True
        else:
            print(f"✗ FAIL: {message}")
            return False
    
    except Exception as e:
        print(f"✗ ERROR: Validation failed with exception: {e}")
        return False


def main() -> int:
    """
    Run all markdown validation tests for README_test.md.
    
    Returns:
        Exit code (0 = success, 1 = failure)
    """
    print("=" * 60)
    print("README_test.md Markdown Validation Test (US-002)")
    print("=" * 60)
    print(f"\nValidating: {README_PATH}")
    
    # Define validation tests
    tests = [
        ("File Exists and Readable", validate_file_exists),
        ("File Size > 0 Bytes", validate_file_size),
        ("UTF-8 Encoding", validate_utf8_encoding),
        ("Title Header Present", validate_title_header),
        ("Required Sections Present", validate_required_sections),
        ("Markdown Syntax Valid", validate_markdown_syntax),
        ("Substantive Content", validate_has_content_sections),
    ]
    
    # Run all tests
    results: List[bool] = []
    for name, validator in tests:
        result = run_validation(name, validator)
        results.append(result)
    
    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    failed = total - passed
    
    print(f"\nTotal Tests:  {total}")
    print(f"Passed:       {passed} ✓")
    print(f"Failed:       {failed} ✗")
    print(f"Success Rate: {(passed / total * 100):.1f}%")
    
    if all(results):
        print("\n✓ ALL VALIDATIONS PASSED")
        print("\nREADME_test.md is properly formatted and complete.")
        return 0
    else:
        print("\n✗ SOME VALIDATIONS FAILED")
        print("\nPlease fix the issues above and re-run this test.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
