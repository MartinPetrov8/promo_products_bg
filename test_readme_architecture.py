#!/usr/bin/env python3
"""
Test suite for README_test.md architecture documentation completeness.
Tests acceptance criteria for US-002.
"""

import re
from pathlib import Path


class TestReadmeArchitecture:
    """Tests for README_test.md architecture section."""
    
    def __init__(self):
        self.readme_path = Path(__file__).parent / "README_test.md"
        self.readme_content = self.readme_path.read_text(encoding='utf-8')
        self.failures = []
        self.passed = 0
    
    def test_architecture_section_exists(self):
        """AC1: README_test.md contains 'Architecture' or 'System Design' section"""
        if "## Architecture" in self.readme_content or "## System Design" in self.readme_content:
            self.passed += 1
            print("✓ AC1: Architecture section exists")
            return True
        else:
            self.failures.append("AC1: No 'Architecture' or 'System Design' section found")
            print("✗ AC1: No 'Architecture' or 'System Design' section found")
            return False
    
    def test_database_structure_documented(self):
        """AC2: Database structure is documented (promobg.db and off_bulgaria.db mentioned)"""
        has_promobg = "promobg.db" in self.readme_content
        has_off_bulgaria = "off_bulgaria.db" in self.readme_content
        
        if has_promobg and has_off_bulgaria:
            self.passed += 1
            print("✓ AC2: Both databases (promobg.db and off_bulgaria.db) are documented")
            return True
        else:
            missing = []
            if not has_promobg:
                missing.append("promobg.db")
            if not has_off_bulgaria:
                missing.append("off_bulgaria.db")
            msg = f"AC2: Missing database documentation: {', '.join(missing)}"
            self.failures.append(msg)
            print(f"✗ {msg}")
            return False
    
    def test_matching_pipeline_described(self):
        """AC3: Matching pipeline is described with match types"""
        required_match_types = ["token", "barcode", "embedding"]
        found_types = []
        
        for match_type in required_match_types:
            # Check for match type mentions (case-insensitive)
            pattern = re.compile(rf'\b{match_type}\b', re.IGNORECASE)
            if pattern.search(self.readme_content):
                found_types.append(match_type)
        
        if len(found_types) == len(required_match_types):
            self.passed += 1
            print(f"✓ AC3: Matching pipeline described with all match types: {', '.join(required_match_types)}")
            return True
        else:
            missing = set(required_match_types) - set(found_types)
            msg = f"AC3: Missing match type documentation: {', '.join(missing)}"
            self.failures.append(msg)
            print(f"✗ {msg}")
            return False
    
    def test_project_structure_included(self):
        """AC4: Project directory structure is included"""
        required_dirs = ["scrapers/", "scripts/", "apps/", "data/"]
        found_dirs = []
        
        for directory in required_dirs:
            if directory in self.readme_content:
                found_dirs.append(directory)
        
        if len(found_dirs) == len(required_dirs):
            self.passed += 1
            print(f"✓ AC4: Project structure includes key directories: {', '.join(required_dirs)}")
            return True
        else:
            missing = set(required_dirs) - set(found_dirs)
            msg = f"AC4: Missing directories in project structure: {', '.join(missing)}"
            self.failures.append(msg)
            print(f"✗ {msg}")
            return False
    
    def test_performance_metrics_documented(self):
        """AC5: Performance metrics are documented (match rate, product count)"""
        # Check for 63.3% match rate
        has_match_rate = "63.3%" in self.readme_content
        # Check for 5,113 products (may be formatted as 5,113 or 5113)
        has_product_count = ("5,113" in self.readme_content or "5113" in self.readme_content)
        
        if has_match_rate and has_product_count:
            self.passed += 1
            print("✓ AC5: Performance metrics documented (63.3% match rate, 5,113 products)")
            return True
        else:
            missing = []
            if not has_match_rate:
                missing.append("63.3% match rate")
            if not has_product_count:
                missing.append("5,113 product count")
            msg = f"AC5: Missing performance metrics: {', '.join(missing)}"
            self.failures.append(msg)
            print(f"✗ {msg}")
            return False
    
    def test_related_docs_referenced(self):
        """AC6: References to related docs are included"""
        required_docs = ["DAILY_SCAN_ARCHITECTURE.md", "MATCHING_PIPELINE.md"]
        found_docs = []
        
        for doc in required_docs:
            if doc in self.readme_content:
                found_docs.append(doc)
        
        if len(found_docs) == len(required_docs):
            self.passed += 1
            print(f"✓ AC6: Related documentation referenced: {', '.join(required_docs)}")
            return True
        else:
            missing = set(required_docs) - set(found_docs)
            msg = f"AC6: Missing documentation references: {', '.join(missing)}"
            self.failures.append(msg)
            print(f"✗ {msg}")
            return False
    
    def run_all_tests(self):
        """Run all tests and report results."""
        print("=" * 70)
        print("Testing README_test.md Architecture Documentation (US-002)")
        print("=" * 70)
        print()
        
        self.test_architecture_section_exists()
        self.test_database_structure_documented()
        self.test_matching_pipeline_described()
        self.test_project_structure_included()
        self.test_performance_metrics_documented()
        self.test_related_docs_referenced()
        
        print()
        print("=" * 70)
        total_tests = self.passed + len(self.failures)
        print(f"Results: {self.passed}/{total_tests} tests passed")
        
        if self.failures:
            print()
            print("FAILURES:")
            for failure in self.failures:
                print(f"  - {failure}")
            print("=" * 70)
            return False
        else:
            print("=" * 70)
            print("✓ All acceptance criteria met!")
            return True


def main():
    """Main test runner."""
    tester = TestReadmeArchitecture()
    success = tester.run_all_tests()
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
