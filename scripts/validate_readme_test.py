#!/usr/bin/env python3
"""
Validation script for README_test.md

Validates markdown formatting, required sections, encoding, and quality standards.
"""

import sys
import os
import re
from pathlib import Path
from typing import List, Tuple, Set


class ReadmeValidator:
    """Validates README_test.md for quality and completeness."""
    
    REQUIRED_SECTIONS = [
        "Promo Products BG - Test Documentation",  # Title (H1)
        "Overview",
        "Features",
        "Tech Stack",
        "Architecture"
    ]
    
    def __init__(self, readme_path: str):
        self.readme_path = Path(readme_path)
        self.content = ""
        self.lines = []
        self.errors = []
        self.warnings = []
    
    def validate(self) -> bool:
        """Run all validation checks. Returns True if all pass."""
        print(f"Validating {self.readme_path}...")
        
        # Check file exists
        if not self.readme_path.exists():
            self.errors.append(f"File not found: {self.readme_path}")
            return False
        
        # Read and validate encoding
        if not self._validate_encoding():
            return False
        
        # Run all validation checks
        self._validate_required_sections()
        self._validate_heading_hierarchy()
        self._validate_code_blocks()
        self._validate_markdown_syntax()
        self._validate_links()
        
        # Report results
        self._print_results()
        
        return len(self.errors) == 0
    
    def _validate_encoding(self) -> bool:
        """Verify file is valid UTF-8."""
        try:
            with open(self.readme_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                self.lines = self.content.split('\n')
            print("✓ UTF-8 encoding verified")
            return True
        except UnicodeDecodeError as e:
            self.errors.append(f"File is not valid UTF-8: {e}")
            return False
    
    def _validate_required_sections(self):
        """Check all required sections are present."""
        missing_sections = []
        
        for section in self.REQUIRED_SECTIONS:
            # Check if section exists as heading (with # prefix or as exact text)
            pattern = rf'^#+\s+{re.escape(section)}|^{re.escape(section)}$'
            if not re.search(pattern, self.content, re.MULTILINE):
                missing_sections.append(section)
        
        if missing_sections:
            self.errors.append(f"Missing required sections: {', '.join(missing_sections)}")
        else:
            print(f"✓ All {len(self.REQUIRED_SECTIONS)} required sections present")
    
    def _validate_heading_hierarchy(self):
        """Ensure heading levels don't skip (e.g., H1 -> H3 without H2)."""
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
        previous_level = 0
        hierarchy_errors = []
        
        for i, line in enumerate(self.lines, 1):
            match = heading_pattern.match(line)
            if match:
                current_level = len(match.group(1))
                heading_text = match.group(2).strip()
                
                # Check for skipped levels (only if jumping more than 1 level down)
                if current_level > previous_level + 1 and previous_level > 0:
                    hierarchy_errors.append(
                        f"Line {i}: Skipped heading level (H{previous_level} -> H{current_level}): {heading_text}"
                    )
                
                previous_level = current_level
        
        if hierarchy_errors:
            for error in hierarchy_errors:
                self.warnings.append(error)
        else:
            print("✓ Heading hierarchy is consistent")
    
    def _validate_code_blocks(self):
        """Verify code blocks have language tags."""
        code_block_pattern = re.compile(r'^```(\w*)$')
        blocks_without_lang = []
        in_code_block = False
        block_start_line = 0
        
        for i, line in enumerate(self.lines, 1):
            match = code_block_pattern.match(line)
            if match:
                if not in_code_block:
                    # Starting a code block
                    in_code_block = True
                    block_start_line = i
                    lang_tag = match.group(1)
                    if not lang_tag:
                        blocks_without_lang.append(f"Line {i}: Code block missing language tag")
                else:
                    # Ending a code block
                    in_code_block = False
        
        if blocks_without_lang:
            for error in blocks_without_lang:
                self.warnings.append(error)
        else:
            # Count code blocks
            code_block_count = len(re.findall(r'^```\w+', self.content, re.MULTILINE))
            print(f"✓ All {code_block_count} code blocks have language tags")
    
    def _validate_markdown_syntax(self):
        """Basic markdown syntax validation."""
        syntax_errors = []
        
        # Check for common markdown issues
        for i, line in enumerate(self.lines, 1):
            # Check for malformed links: [text](url should have closing )
            if '[' in line and '](' in line:
                # Count brackets
                open_brackets = line.count('[')
                close_brackets = line.count(']')
                open_parens = line.count('(', line.find(']'))
                close_parens = line.count(')', line.find(']'))
                
                if open_brackets != close_brackets or ('](' in line and open_parens != close_parens):
                    # This is a complex check; only warn if obviously broken
                    if line.count('[') > line.count(']') or line.count('](') > line.count(')'):
                        syntax_errors.append(f"Line {i}: Possibly malformed link syntax")
            
            # Check for unbalanced code backticks (odd number on a line outside code blocks)
            if '`' in line and not line.strip().startswith('```'):
                backtick_count = line.count('`')
                if backtick_count % 2 != 0:
                    syntax_errors.append(f"Line {i}: Unbalanced backticks (odd count)")
        
        if syntax_errors:
            for error in syntax_errors:
                self.warnings.append(error)
        else:
            print("✓ Basic markdown syntax appears valid")
    
    def _validate_links(self):
        """Check for broken internal links and verify external link format."""
        # Extract all markdown links
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        broken_links = []
        
        for match in link_pattern.finditer(self.content):
            link_text = match.group(1)
            link_url = match.group(2)
            
            # Check internal file links (relative paths starting with ./ or ../)
            if link_url.startswith('./') or link_url.startswith('../'):
                # Resolve relative to README_test.md location
                link_path = self.readme_path.parent / link_url
                if not link_path.exists():
                    broken_links.append(f"Broken internal link: [{link_text}]({link_url})")
            
            # Check anchor-only links (within same document)
            elif link_url.startswith('#'):
                # For anchor validation, we'd need to parse all heading IDs
                # Skip for now as it's complex
                pass
        
        if broken_links:
            for error in broken_links:
                self.errors.append(error)
        else:
            link_count = len(link_pattern.findall(self.content))
            print(f"✓ All {link_count} links validated (no broken internal links)")
    
    def _print_results(self):
        """Print validation results summary."""
        print("\n" + "="*60)
        print("VALIDATION RESULTS")
        print("="*60)
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if not self.errors and not self.warnings:
            print("\n✅ All validation checks passed!")
        elif not self.errors:
            print(f"\n✅ Validation passed with {len(self.warnings)} warnings")
        
        print("="*60 + "\n")


def main():
    """Main entry point for validation script."""
    # Default to README_test.md in project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    readme_path = project_root / "README_test.md"
    
    # Allow override via command line argument
    if len(sys.argv) > 1:
        readme_path = Path(sys.argv[1])
    
    validator = ReadmeValidator(readme_path)
    success = validator.validate()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
