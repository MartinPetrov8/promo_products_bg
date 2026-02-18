#!/usr/bin/env python3
"""
Test script for README_test.md validation
Tests all acceptance criteria for US-001
"""

import os
import sys
import re

def test_file_exists():
    """AC 1: File README_test.md exists in repository root"""
    file_path = "/home/node/.openclaw/workspace/promo_products_bg/README_test.md"
    if not os.path.exists(file_path):
        print("❌ FAIL: README_test.md does not exist")
        return False
    print("✓ PASS: README_test.md exists in repository root")
    return True

def test_top_level_header():
    """AC 2: File contains a top-level header '# Promo Products BG' or similar"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    if re.search(r'^# Promo Products BG', content, re.MULTILINE):
        print("✓ PASS: Contains top-level header '# Promo Products BG'")
        return True
    else:
        print("❌ FAIL: Missing top-level header '# Promo Products BG'")
        return False

def test_required_sections():
    """AC 3: File includes sections for: Features, Quick Start, Project Structure, Matching Pipeline, Database, and API/Frontend"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_sections = [
        "Features",
        "Quick Start",
        "Project Structure",
        "Matching Pipeline",
        "Database",
        "API/Frontend"
    ]
    
    all_found = True
    for section in required_sections:
        if re.search(rf'^## {section}', content, re.MULTILINE):
            print(f"  ✓ Found section: {section}")
        else:
            print(f"  ❌ Missing section: {section}")
            all_found = False
    
    if all_found:
        print("✓ PASS: All required sections present")
    else:
        print("❌ FAIL: Some required sections missing")
    
    return all_found

def test_code_blocks():
    """AC 4: File contains code blocks showing installation and usage commands"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count code blocks (```...```)
    code_blocks = re.findall(r'```[\s\S]*?```', content)
    
    if len(code_blocks) >= 1:
        print(f"✓ PASS: Contains {len(code_blocks)} code block(s) with commands")
        return True
    else:
        print("❌ FAIL: No code blocks found")
        return False

def test_statistics_table():
    """AC 5: File includes a table showing matching pipeline statistics"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Look for table with matching statistics
    if re.search(r'\| Total products \|', content) or re.search(r'\| Match rate \|', content):
        print("✓ PASS: Contains matching pipeline statistics table")
        return True
    else:
        print("❌ FAIL: Missing matching pipeline statistics table")
        return False

def test_three_stores():
    """AC 6: File documents all three stores: Kaufland, Lidl, and Billa"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    stores = ["Kaufland", "Lidl", "Billa"]
    all_found = True
    
    for store in stores:
        if store in content:
            print(f"  ✓ Found store: {store}")
        else:
            print(f"  ❌ Missing store: {store}")
            all_found = False
    
    if all_found:
        print("✓ PASS: All three stores documented")
    else:
        print("❌ FAIL: Some stores missing")
    
    return all_found

def test_openfoodfacts_integration():
    """AC 7: File mentions OpenFoodFacts integration and match rate (63%+)"""
    with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_off = "OpenFoodFacts" in content or "OFF" in content
    has_match_rate = re.search(r'63[.%]', content) or re.search(r'63\.3%', content)
    
    if has_off and has_match_rate:
        print("✓ PASS: OpenFoodFacts integration and match rate (63%+) documented")
        return True
    elif has_off:
        print("❌ FAIL: OpenFoodFacts mentioned but match rate missing")
        return False
    else:
        print("❌ FAIL: OpenFoodFacts integration not mentioned")
        return False

def test_file_size():
    """AC 8: File size is greater than 500 bytes"""
    file_path = "/home/node/.openclaw/workspace/promo_products_bg/README_test.md"
    file_size = os.path.getsize(file_path)
    
    if file_size > 500:
        print(f"✓ PASS: File size is {file_size} bytes (> 500)")
        return True
    else:
        print(f"❌ FAIL: File size is {file_size} bytes (<= 500)")
        return False

def test_utf8_encoding():
    """AC 9: File is valid UTF-8 encoded text"""
    try:
        with open("/home/node/.openclaw/workspace/promo_products_bg/README_test.md", 'r', encoding='utf-8') as f:
            f.read()
        print("✓ PASS: File is valid UTF-8 encoded text")
        return True
    except UnicodeDecodeError:
        print("❌ FAIL: File is not valid UTF-8")
        return False

def test_cat_displays():
    """AC 10: Running 'cat README_test.md' displays the content without errors"""
    import subprocess
    try:
        result = subprocess.run(
            ['cat', '/home/node/.openclaw/workspace/promo_products_bg/README_test.md'],
            capture_output=True,
            check=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✓ PASS: 'cat README_test.md' executes without errors")
            return True
        else:
            print("❌ FAIL: 'cat README_test.md' returned non-zero exit code")
            return False
    except Exception as e:
        print(f"❌ FAIL: 'cat README_test.md' failed with error: {e}")
        return False

def main():
    """Run all validation tests"""
    print("=" * 60)
    print("README_test.md Validation Tests (US-001)")
    print("=" * 60)
    print()
    
    tests = [
        ("AC 1: File exists", test_file_exists),
        ("AC 2: Top-level header", test_top_level_header),
        ("AC 3: Required sections", test_required_sections),
        ("AC 4: Code blocks", test_code_blocks),
        ("AC 5: Statistics table", test_statistics_table),
        ("AC 6: Three stores", test_three_stores),
        ("AC 7: OpenFoodFacts integration", test_openfoodfacts_integration),
        ("AC 8: File size > 500 bytes", test_file_size),
        ("AC 9: UTF-8 encoding", test_utf8_encoding),
        ("AC 10: Cat displays content", test_cat_displays),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\nTest: {name}")
        print("-" * 60)
        result = test_func()
        results.append(result)
        print()
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if all(results):
        print("\n✓ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
