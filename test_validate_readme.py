#!/usr/bin/env python3
"""
Tests for README_test.md validation script.

Validates US-003 acceptance criteria:
  1. Validation script exists (scripts/validate_readme_test.py)
  2. Script checks for required sections
  3. Script validates markdown syntax
  4. Script verifies UTF-8 encoding
  5. Script checks heading hierarchy
  6. Running 'python3 scripts/validate_readme_test.py' exits with code 0
  7. Tests for validation script pass
"""

import unittest
import sys
import subprocess
from pathlib import Path


class TestReadmeValidation(unittest.TestCase):
    """Test suite for README_test.md validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent
        self.validation_script = self.project_root / "scripts" / "validate_readme_test.py"
        self.readme_path = self.project_root / "README_test.md"
    
    def test_ac1_validation_script_exists(self):
        """AC1: Validation script exists (scripts/validate_readme_test.py)."""
        self.assertTrue(
            self.validation_script.exists(),
            f"Validation script not found: {self.validation_script}"
        )
        print("✓ AC1: Validation script exists")
    
    def test_ac2_script_checks_required_sections(self):
        """AC2: Script checks for required sections."""
        # Read the validation script and verify it checks for required sections
        with open(self.validation_script, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Verify REQUIRED_SECTIONS constant exists
        self.assertIn("REQUIRED_SECTIONS", script_content,
                      "Script missing REQUIRED_SECTIONS constant")
        
        # Verify it checks for title, description, features, stack, architecture
        required_checks = [
            "Promo Products BG",  # Title
            "Overview",  # Description
            "Features",
            "Tech Stack",
            "Architecture"
        ]
        
        for section in required_checks:
            self.assertIn(section, script_content,
                          f"Script doesn't check for '{section}' section")
        
        print(f"✓ AC2: Script checks for {len(required_checks)} required sections")
    
    def test_ac3_script_validates_markdown_syntax(self):
        """AC3: Script validates markdown syntax."""
        with open(self.validation_script, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Verify markdown validation methods exist
        self.assertIn("_validate_markdown_syntax", script_content,
                      "Script missing markdown syntax validation")
        
        # Verify it checks for common issues
        markdown_checks = [
            "link",  # Link validation
            "backtick",  # Code formatting
        ]
        
        for check in markdown_checks:
            self.assertIn(check.lower(), script_content.lower(),
                          f"Script missing {check} validation")
        
        print("✓ AC3: Script validates markdown syntax")
    
    def test_ac4_script_verifies_utf8_encoding(self):
        """AC4: Script verifies UTF-8 encoding."""
        with open(self.validation_script, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Verify encoding validation exists
        self.assertIn("encoding='utf-8'", script_content,
                      "Script doesn't explicitly check UTF-8 encoding")
        self.assertIn("_validate_encoding", script_content,
                      "Script missing encoding validation method")
        
        print("✓ AC4: Script verifies UTF-8 encoding")
    
    def test_ac5_script_checks_heading_hierarchy(self):
        """AC5: Script checks heading hierarchy."""
        with open(self.validation_script, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Verify heading hierarchy validation exists
        self.assertIn("_validate_heading_hierarchy", script_content,
                      "Script missing heading hierarchy validation")
        
        # Verify it checks for skipped levels
        self.assertIn("level", script_content.lower(),
                      "Script doesn't check heading levels")
        
        print("✓ AC5: Script checks heading hierarchy")
    
    def test_ac6_validation_script_exits_zero(self):
        """AC6: Running 'python3 scripts/validate_readme_test.py' exits with code 0."""
        # Run the validation script
        result = subprocess.run(
            [sys.executable, str(self.validation_script)],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        
        # Print output for debugging
        if result.stdout:
            print(f"\nValidation output:\n{result.stdout}")
        if result.stderr:
            print(f"\nValidation errors:\n{result.stderr}")
        
        # Check exit code
        self.assertEqual(result.returncode, 0,
                        f"Validation script exited with code {result.returncode}\n"
                        f"stdout: {result.stdout}\nstderr: {result.stderr}")
        
        print("✓ AC6: Validation script exits with code 0")
    
    def test_ac7_validation_detects_missing_sections(self):
        """AC7: Validation script can detect issues (negative test)."""
        # Create a temporary invalid README to test detection
        import tempfile
        
        invalid_content = """# Test README
        
This is missing required sections.

## Some Section

Content here.
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(invalid_content)
            temp_path = f.name
        
        try:
            # Run validation on invalid file
            result = subprocess.run(
                [sys.executable, str(self.validation_script), temp_path],
                capture_output=True,
                text=True
            )
            
            # Should exit with non-zero code
            self.assertNotEqual(result.returncode, 0,
                               "Validation should fail for incomplete README")
            
            # Should report missing sections
            self.assertIn("Missing required sections", result.stdout,
                          "Validation should report missing sections")
            
            print("✓ AC7: Validation script correctly detects issues")
        
        finally:
            # Clean up temp file
            import os
            os.unlink(temp_path)


def main():
    """Run tests and print results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestReadmeValidation)
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY - US-003: Validate README_test.md")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ All acceptance criteria validated successfully!")
    else:
        print("\n❌ Some tests failed")
    
    print("="*70 + "\n")
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
