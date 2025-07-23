#!/usr/bin/env python3
"""
JSON Resume Manager
Utility script for managing JSON-based resumes with job-specific customizations
"""

import json
import os
import shutil
import sys
import secrets
import string
from pathlib import Path
from typing import Dict, List, Any

class JSONResumeManager:
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.templates_path = self.base_path / "templates" / "resumes"
        self.base_resume_path = self.templates_path / "base-resume.json"
    
    def generate_cuid2(self) -> str:
        """Generate a CUID2-like ID (24 characters, lowercase + digits)"""
        chars = string.ascii_lowercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(24))
        
    def load_base_resume(self) -> Dict[str, Any]:
        """Load the base resume JSON file"""
        try:
            with open(self.base_resume_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: Base resume not found at {self.base_resume_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in base resume: {e}")
            sys.exit(1)
    
    def save_resume(self, resume_data: Dict[str, Any], output_path: str):
        """Save resume data to JSON file"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(resume_data, f, indent=2)
        print(f"Resume saved to: {output_path}")
    
    def create_job_specific_resume(self, company: str, role_focus: str = None) -> Dict[str, Any]:
        """Create a job-specific resume based on role focus"""
        resume = self.load_base_resume()
        
        # Role-specific customizations
        if role_focus:
            resume = self.apply_role_focus(resume, role_focus)
        
        # Add company-specific notes
        resume["metadata"]["notes"] = f"Customized for {company}"
        
        return resume
    
    def apply_role_focus(self, resume: Dict[str, Any], role_focus: str) -> Dict[str, Any]:
        """Apply role-specific customizations"""
        
        if role_focus.lower() in ["frontend", "front-end", "ui", "react", "vue"]:
            return self.customize_for_frontend(resume)
        elif role_focus.lower() in ["backend", "back-end", "api", "server", "python"]:
            return self.customize_for_backend(resume)
        elif role_focus.lower() in ["fullstack", "full-stack", "full stack"]:
            return self.customize_for_fullstack(resume)
        elif role_focus.lower() in ["devops", "cloud", "infrastructure"]:
            return self.customize_for_devops(resume)
        elif role_focus.lower() in ["data", "analytics", "ml", "ai"]:
            return self.customize_for_data(resume)
        
        return resume
    
    def customize_for_frontend(self, resume: Dict[str, Any]) -> Dict[str, Any]:
        """Customize resume for frontend roles"""
        # Reorder skills to prioritize frontend
        skills = resume["sections"]["skills"]["items"]
        for skill in skills:
            if "Frontend" in skill["name"] or "React" in skill.get("keywords", []):
                skill["level"] = 5
        
        # Update layout to show skills first
        resume["metadata"]["layout"] = [
            [
                ["profiles", "summary", "experience", "projects"],
                ["skills", "education", "certifications", "languages"]
            ]
        ]
        
        # Update summary for frontend focus
        resume["sections"]["summary"]["content"] = resume["sections"]["summary"]["content"].replace(
            "full-stack development",
            "frontend development with expertise in modern JavaScript frameworks"
        )
        
        return resume
    
    def customize_for_backend(self, resume: Dict[str, Any]) -> Dict[str, Any]:
        """Customize resume for backend roles"""
        # Prioritize backend skills
        skills = resume["sections"]["skills"]["items"]
        for skill in skills:
            if "Database" in skill["name"] or "Python" in skill.get("keywords", []):
                skill["level"] = 5
        
        # Update summary for backend focus
        resume["sections"]["summary"]["content"] = resume["sections"]["summary"]["content"].replace(
            "modern web technologies",
            "backend systems and database design"
        )
        
        return resume
    
    def customize_for_fullstack(self, resume: Dict[str, Any]) -> Dict[str, Any]:
        """Customize resume for fullstack roles"""
        # Keep all skills visible and balanced
        return resume
    
    def customize_for_devops(self, resume: Dict[str, Any]) -> Dict[str, Any]:
        """Customize resume for DevOps roles"""
        # Prioritize DevOps skills
        skills = resume["sections"]["skills"]["items"]
        for skill in skills:
            if "DevOps" in skill["name"] or "Docker" in skill.get("keywords", []):
                skill["level"] = 5
        
        return resume
    
    def customize_for_data(self, resume: Dict[str, Any]) -> Dict[str, Any]:
        """Customize resume for data roles"""
        # Hide non-relevant sections
        resume["sections"]["interests"]["visible"] = False
        
        return resume
    
    def hide_section(self, resume: Dict[str, Any], section_name: str) -> Dict[str, Any]:
        """Hide a specific section"""
        if section_name in resume["sections"]:
            resume["sections"][section_name]["visible"] = False
        return resume
    
    def show_section(self, resume: Dict[str, Any], section_name: str) -> Dict[str, Any]:
        """Show a specific section"""
        if section_name in resume["sections"]:
            resume["sections"][section_name]["visible"] = True
        return resume
    
    def update_keywords(self, resume: Dict[str, Any], job_keywords: List[str]) -> Dict[str, Any]:
        """Update skill keywords based on job requirements"""
        skills = resume["sections"]["skills"]["items"]
        
        for skill in skills:
            # Add relevant keywords to existing skills
            existing_keywords = skill.get("keywords", [])
            for keyword in job_keywords:
                if keyword.lower() in skill["description"].lower():
                    if keyword not in existing_keywords:
                        existing_keywords.append(keyword)
            skill["keywords"] = existing_keywords
        
        return resume
    
    def validate_json(self, file_path: str) -> bool:
        """Validate JSON file syntax"""
        try:
            with open(file_path, 'r') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            print(f"JSON validation error: {e}")
            return False
    
    def list_sections(self) -> List[str]:
        """List all available sections in base resume"""
        resume = self.load_base_resume()
        return list(resume["sections"].keys())

def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="JSON Resume Manager")
    parser.add_argument("--company", help="Company name")
    parser.add_argument("--role", help="Role focus (frontend, backend, fullstack, devops, data)")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--hide", nargs="*", help="Sections to hide")
    parser.add_argument("--show", nargs="*", help="Sections to show")
    parser.add_argument("--keywords", nargs="*", help="Job keywords to emphasize")
    parser.add_argument("--validate", help="Validate JSON file")
    parser.add_argument("--list-sections", action="store_true", help="List all sections")
    
    args = parser.parse_args()
    
    manager = JSONResumeManager()
    
    if args.validate:
        is_valid = manager.validate_json(args.validate)
        print(f"JSON validation: {'PASSED' if is_valid else 'FAILED'}")
        return
    
    if args.list_sections:
        sections = manager.list_sections()
        print("Available sections:")
        for section in sections:
            print(f"  - {section}")
        return
    
    # Require company for resume generation
    if not args.company:
        parser.error("--company is required for resume generation")
    
    # Create job-specific resume
    resume = manager.create_job_specific_resume(args.company, args.role)
    
    # Apply customizations
    if args.hide:
        for section in args.hide:
            resume = manager.hide_section(resume, section)
    
    if args.show:
        for section in args.show:
            resume = manager.show_section(resume, section)
    
    if args.keywords:
        resume = manager.update_keywords(resume, args.keywords)
    
    # Save resume
    if args.output:
        output_path = args.output
    else:
        output_path = f"applications/active/{args.company}/documents/resume.json"
    
    manager.save_resume(resume, output_path)

if __name__ == "__main__":
    main() 