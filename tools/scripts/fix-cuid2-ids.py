#!/usr/bin/env python3
"""
Fix CUID2 IDs in JSON Resume
Updates all ID fields to use proper CUID2 format for Reactive Resume compatibility
"""

import argparse
import json
import secrets
import string
from pathlib import Path

def generate_cuid2():
    """Generate a CUID2-like ID (24 characters, lowercase + digits)"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(24))

def fix_cuid2_ids(data, path=[]):
    """Recursively fix item 'id' fields in the JSON structure, but preserve section IDs"""
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = path + [key]
            
            # Only fix IDs that are NOT section IDs
            if key == 'id' and isinstance(value, str):
                # Check if this is a section ID (should be literal string)
                if len(current_path) >= 3 and current_path[-3] == 'sections':
                    # This is a section ID, should be literal string like "summary", "experience", etc.
                    section_name = current_path[-2]  # Get the section name
                    data[key] = section_name
                else:
                    # This is an item ID, should be CUID2
                    data[key] = generate_cuid2()
            else:
                fix_cuid2_ids(value, current_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            fix_cuid2_ids(item, path + [i])

def main():
    parser = argparse.ArgumentParser(description="Fix CUID2 IDs in JSON resumes.")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return
    
    # Load the resume
    with open(input_path, 'r') as f:
        resume_data = json.load(f)
    
    # Fix all CUID2 IDs
    fix_cuid2_ids(resume_data)
    
    # Save the updated resume
    with open(output_path, 'w') as f:
        json.dump(resume_data, f, indent=2)
    
    print(f"✅ Fixed CUID2 IDs in {output_path}")
    print("Section IDs are now literal strings, item IDs use CUID2 format")

if __name__ == "__main__":
    main()