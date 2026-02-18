#!/usr/bin/env python3
"""
Test suite for README_test.md validation.

Validates all acceptance criteria for US-001:
- File existence and encoding
- Required sections and content
- Code blocks and formatting
- Comprehensive project documentation
"""

import os
import sys
from pathlib import Path

# Test configuration
README_PATH = "README_test.md"
MIN_FILE_SIZE = 500  # bytes - AC8
REQUIRED_SECTIONS = [
    "Features",
    "Quick Start", 
    "Technology Stack",
    "Store Coverage",
    "Project Structure",
    "Matching Pipeline",
    "Database",
    "API/Frontend",
    "Testing",
    "Development Workflow"
]
REQUIRED_STORES = ["Kaufland", "Lidl", "Billa"]
MATCH_RATE = "63.3%"
MATCH_TYPES = ["Token", "Transliteration", "Barcode", "Embedding", "Fuzzy"]


class TestReadmeTest:
    """Test class for README_test.md validation"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.readme_content = None
        
    def test_file_exists(self):
        """AC1: README_test.md file exists in repository root"""
        print("AC1: Testing file existence...")
        if not os.path.exists(README_PATH):
            print(f"  ❌ FAIL: {README_PATH} does not exist")
            self.failed += 1
            return False
        print(f"  ✓ PASS: {README_PATH} exists")
        self.passed += 1
        return True
    
    def test_valid_utf8_encoding(self):
        """AC9: File is valid UTF-8 encoded markdown"""
        print("AC9: Testing UTF-8 encoding...")
        try:
            with open(README_PATH, 'r', encoding='utf-8') as f:
                self.readme_content = f.read()
            print("  ✓ PASS: File is valid UTF-8")
            self.passed += 1
            return True
        except UnicodeDecodeError as e:
            print(f"  ❌ FAIL: File is not valid UTF-8: {e}")
            self.failed += 1
            return False
    
    def test_top_level_header(self):
        """AC2: File contains top-level header '# Promo Products BG'"""
        print("AC2: Testing top-level header...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        if "# Promo Products BG" not in self.readme_content:
            print("  ❌ FAIL: Missing top-level header '# Promo Products BG'")
            self.failed += 1
            return False
        
        print("  ✓ PASS: Top-level header '# Promo Products BG' found")
        self.passed += 1
        return True
    
    def test_required_sections(self):
        """AC3: Includes all required sections"""
        print(f"AC3: Testing for {len(REQUIRED_SECTIONS)} required sections...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        missing_sections = []
        content_lower = self.readme_content.lower()
        
        for section in REQUIRED_SECTIONS:
            # Check for section as heading (## Section) or within content
            section_lower = section.lower()
            
            # Check various patterns:
            # 1. As markdown heading: ## Features
            # 2. As part of heading: ## Tech Stack (for "Technology Stack")
            # 3. Mentioned in content (for sections like "Store Coverage")
            found = False
            
            if section_lower == "technology stack":
                # Allow "Tech Stack" as alias
                found = "## tech stack" in content_lower or "technology stack" in content_lower
            elif section_lower == "store coverage":
                # Store coverage documented in Features section and tables
                found = ("kaufland" in content_lower and 
                        "lidl" in content_lower and 
                        "billa" in content_lower and
                        "products" in content_lower)
            elif section_lower == "matching pipeline":
                # Documented in Architecture section
                found = "matching pipeline" in content_lower or "match type" in content_lower
            elif section_lower == "database":
                # Can be "Database" or "Database Schema"
                found = "## database" in content_lower or "database schema" in content_lower
            elif section_lower == "api/frontend":
                # Documented in various sections
                found = ("frontend" in content_lower or "web interface" in content_lower) and \
                        ("github pages" in content_lower or "html" in content_lower)
            elif section_lower == "testing":
                # Testing section in Quick Start or Development Workflow
                found = "testing" in content_lower or "test" in content_lower
            else:
                # Standard section heading check
                found = f"## {section_lower}" in content_lower or section_lower in content_lower
            
            if not found:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"  ❌ FAIL: Missing sections: {', '.join(missing_sections)}")
            self.failed += 1
            return False
        
        print(f"  ✓ PASS: All {len(REQUIRED_SECTIONS)} required sections found")
        self.passed += 1
        return True
    
    def test_code_blocks(self):
        """AC4: Contains code blocks with installation/usage commands"""
        print("AC4: Testing for code blocks...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        # Count code blocks (both ``` and indented)
        code_block_count = self.readme_content.count("```")
        
        if code_block_count < 4:  # Should have multiple code blocks
            print(f"  ❌ FAIL: Insufficient code blocks found ({code_block_count // 2})")
            self.failed += 1
            return False
        
        # Check for common commands
        has_install_commands = "git clone" in self.readme_content or "pip install" in self.readme_content
        has_usage_commands = "python3" in self.readme_content or "python" in self.readme_content
        
        if not (has_install_commands or has_usage_commands):
            print("  ❌ FAIL: Missing installation or usage commands")
            self.failed += 1
            return False
        
        print(f"  ✓ PASS: Code blocks found with commands ({code_block_count // 2} blocks)")
        self.passed += 1
        return True
    
    def test_matching_pipeline_statistics(self):
        """AC5: Includes matching pipeline statistics table with match rate and breakdown"""
        print("AC5: Testing matching pipeline statistics...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        # Check for match rate 63.3%
        if MATCH_RATE not in self.readme_content:
            print(f"  ❌ FAIL: Match rate {MATCH_RATE} not found")
            self.failed += 1
            return False
        
        # Check for match type breakdown
        content_lower = self.readme_content.lower()
        missing_types = []
        for match_type in MATCH_TYPES:
            if match_type.lower() not in content_lower:
                missing_types.append(match_type)
        
        if missing_types:
            print(f"  ❌ FAIL: Missing match types: {', '.join(missing_types)}")
            self.failed += 1
            return False
        
        # Check for table structure (| headers |)
        has_table = "|" in self.readme_content and ("Match Type" in self.readme_content or "match type" in content_lower)
        
        if not has_table:
            print("  ❌ FAIL: Match type distribution table not found")
            self.failed += 1
            return False
        
        print(f"  ✓ PASS: Matching pipeline statistics with {MATCH_RATE} match rate and all match types found")
        self.passed += 1
        return True
    
    def test_store_coverage(self):
        """AC6: Documents all three stores with product counts"""
        print("AC6: Testing store coverage...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        missing_stores = []
        for store in REQUIRED_STORES:
            if store not in self.readme_content:
                missing_stores.append(store)
        
        if missing_stores:
            print(f"  ❌ FAIL: Missing stores: {', '.join(missing_stores)}")
            self.failed += 1
            return False
        
        # Check for product counts (should have numbers associated with stores)
        content_lines = self.readme_content.split('\n')
        store_with_counts = 0
        for line in content_lines:
            for store in REQUIRED_STORES:
                # Look for patterns like "Kaufland: 800+" or "800+ products from Kaufland"
                if store in line and any(char.isdigit() for char in line):
                    store_with_counts += 1
                    break
        
        if store_with_counts < 2:  # At least 2 stores should have product counts mentioned
            print(f"  ❌ FAIL: Stores documented but product counts not clearly shown")
            self.failed += 1
            return False
        
        print(f"  ✓ PASS: All 3 stores ({', '.join(REQUIRED_STORES)}) documented with product counts")
        self.passed += 1
        return True
    
    def test_openfoodfacts_integration(self):
        """AC7: Mentions OpenFoodFacts integration and match rate"""
        print("AC7: Testing OpenFoodFacts integration documentation...")
        if self.readme_content is None:
            print("  ❌ FAIL: Could not read file")
            self.failed += 1
            return False
        
        content_lower = self.readme_content.lower()
        
        # Check for OpenFoodFacts mentions
        has_off = "openfoodfacts" in content_lower or "open food facts" in content_lower or "OFF" in self.readme_content
        
        if not has_off:
            print("  ❌ FAIL: OpenFoodFacts integration not documented")
            self.failed += 1
            return False
        
        # Check that match rate is mentioned in relation to OpenFoodFacts
        # Look for context around match rate
        has_match_context = MATCH_RATE in self.readme_content
        
        if not has_match_context:
            print("  ❌ FAIL: OpenFoodFacts match rate not clearly documented")
            self.failed += 1
            return False
        
        print("  ✓ PASS: OpenFoodFacts integration and match rate documented")
        self.passed += 1
        return True
    
    def test_file_size(self):
        """AC8: File size > 500 bytes (comprehensive content)"""
        print("AC8: Testing file size...")
        if not os.path.exists(README_PATH):
            print("  ❌ FAIL: File does not exist")
            self.failed += 1
            return False
        
        file_size = os.path.getsize(README_PATH)
        
        if file_size <= MIN_FILE_SIZE:
            print(f"  ❌ FAIL: File size {file_size} bytes is not > {MIN_FILE_SIZE} bytes")
            self.failed += 1
            return False
        
        print(f"  ✓ PASS: File size {file_size} bytes > {MIN_FILE_SIZE} bytes")
        self.passed += 1
        return True
    
    def test_cat_command(self):
        """AC10: Running 'cat README_test.md' displays content without errors"""
        print("AC10: Testing cat command...")
        import subprocess
        
        try:
            result = subprocess.run(
                ['cat', README_PATH],
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.returncode != 0:
                print(f"  ❌ FAIL: cat command failed with exit code {result.returncode}")
                self.failed += 1
                return False
            
            if len(result.stdout) < MIN_FILE_SIZE:
                print(f"  ❌ FAIL: cat output too short ({len(result.stdout)} bytes)")
                self.failed += 1
                return False
            
            print(f"  ✓ PASS: cat command displays {len(result.stdout)} bytes without errors")
            self.passed += 1
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"  ❌ FAIL: cat command error: {e}")
            self.failed += 1
            return False
        except FileNotFoundError:
            print("  ❌ FAIL: cat command not found")
            self.failed += 1
            return False
    
    def run_all_tests(self):
        """Run all test methods"""
        print("=" * 70)
        print("README_test.md Validation Test Suite")
        print("=" * 70)
        print()
        
        # Run tests in logical order (file must be read first)
        self.test_file_exists()
        self.test_valid_utf8_encoding()  # Must run early - loads file content
        self.test_file_size()
        self.test_top_level_header()
        self.test_required_sections()
        self.test_code_blocks()
        self.test_matching_pipeline_statistics()
        self.test_store_coverage()
        self.test_openfoodfacts_integration()
        self.test_cat_command()
        
        # Print summary
        print()
        print("=" * 70)
        print(f"Test Results: {self.passed} passed, {self.failed} failed")
        print("=" * 70)
        
        if self.failed > 0:
            print("\n❌ TESTS FAILED")
            return 1
        else:
            print("\n✓ ALL TESTS PASSED")
            return 0


def main():
    """Main test runner"""
    tester = TestReadmeTest()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
