#!/usr/bin/env python3

"""
Job Description Analyzer
------------------------
This script analyzes a job description to extract key requirements,
skills, and keywords to help tailor your resume and cover letter.
"""

import sys
import os
import re
import argparse
from collections import Counter

# Common technical skills to look for
TECHNICAL_SKILLS = [
    "python", "javascript", "typescript", "react", "angular", "vue", "node", "express",
    "django", "flask", "fastapi", "ruby", "rails", "php", "laravel", "java", "spring",
    "c#", ".net", "c++", "go", "rust", "swift", "kotlin", "aws", "azure", "gcp",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions",
    "circleci", "travis", "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "kafka", "rabbitmq", "graphql", "rest", "api", "microservices", "git", "linux",
    "bash", "html", "css", "sass", "less", "webpack", "babel", "jest", "mocha",
    "cypress", "selenium", "machine learning", "ai", "data science", "tensorflow",
    "pytorch", "pandas", "numpy", "scikit-learn", "tableau", "power bi", "hadoop",
    "spark", "agile", "scrum", "kanban", "jira", "confluence", "devops", "ci/cd"
]

# Common soft skills to look for
SOFT_SKILLS = [
    "communication", "teamwork", "collaboration", "leadership", "problem solving",
    "critical thinking", "creativity", "time management", "organization", "adaptability",
    "flexibility", "interpersonal", "presentation", "negotiation", "conflict resolution",
    "decision making", "emotional intelligence", "customer service", "attention to detail",
    "multitasking", "prioritization", "self-motivated", "proactive", "initiative",
    "analytical", "strategic thinking", "innovation", "mentoring", "coaching"
]

def read_job_description(file_path):
    """Read job description from file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

def extract_technical_skills(text):
    """Extract technical skills from text"""
    found_skills = []
    for skill in TECHNICAL_SKILLS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text.lower()):
            found_skills.append(skill)
    return found_skills

def extract_soft_skills(text):
    """Extract soft skills from text"""
    found_skills = []
    for skill in SOFT_SKILLS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text.lower()):
            found_skills.append(skill)
    return found_skills

def extract_years_experience(text):
    """Extract years of experience requirements"""
    patterns = [
        r'(\d+)\+?\s*(?:to|-)\s*(\d+)\+?\s*years?(?:\s+of)?\s+experience',
        r'(\d+)\+?\s*years?(?:\s+of)?\s+experience',
        r'experience(?:\s+of)?\s+(\d+)\+?\s*years?'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            if isinstance(matches[0], tuple):
                return f"{matches[0][0]}-{matches[0][1]} years"
            else:
                return f"{matches[0]}+ years"
    
    return "Not specified"

def extract_education(text):
    """Extract education requirements"""
    education_patterns = [
        r"bachelor'?s\s+degree",
        r"master'?s\s+degree",
        r"ph\.?d",
        r"doctorate",
        r"mba",
        r"associate'?s\s+degree",
        r"high\s+school",
        r"ged"
    ]
    
    education = []
    for pattern in education_patterns:
        if re.search(pattern, text.lower()):
            education.append(pattern.replace(r'\.?', '.').replace('\\s+', ' '))
    
    return education if education else ["Not specified"]

def extract_keywords(text, top_n=20):
    """Extract potential keywords from the job description"""
    # Remove common words and punctuation
    words = re.findall(r'\b[a-zA-Z][a-zA-Z-]{2,}\b', text.lower())
    
    # Common words to exclude
    stop_words = {"the", "and", "to", "of", "in", "for", "with", "on", "at", "from", 
                  "by", "about", "as", "an", "will", "you", "your", "we", "our", 
                  "this", "that", "these", "those", "they", "them", "their", "it", 
                  "its", "is", "are", "was", "were", "be", "been", "being", "have", 
                  "has", "had", "do", "does", "did", "can", "could", "would", "should", 
                  "may", "might", "must", "shall"}
    
    filtered_words = [word for word in words if word not in stop_words]
    word_counts = Counter(filtered_words)
    
    # Return the most common words
    return word_counts.most_common(top_n)

def analyze_job_description(file_path, output_dir):
    """Analyze job description and create analysis files"""
    job_description = read_job_description(file_path)
    
    technical_skills = extract_technical_skills(job_description)
    soft_skills = extract_soft_skills(job_description)
    years_experience = extract_years_experience(job_description)
    education = extract_education(job_description)
    keywords = extract_keywords(job_description)
    
    # Create requirements analysis file
    req_analysis_path = os.path.join(output_dir, "requirements-analysis.md")
    with open(req_analysis_path, 'w', encoding='utf-8') as file:
        file.write("# Job Requirements Analysis\n\n")
        
        file.write("## Technical Skills\n")
        for skill in technical_skills:
            file.write(f"- {skill.capitalize()}: [Your level of proficiency, experience]\n")
        
        file.write("\n## Soft Skills\n")
        for skill in soft_skills:
            file.write(f"- {skill.capitalize()}: [Your level of proficiency, experience]\n")
        
        file.write("\n## Experience Requirements\n")
        file.write(f"- Years of Experience: {years_experience}\n")
        file.write("- [Other experience requirements]: [How you meet this requirement]\n")
        
        file.write("\n## Education Requirements\n")
        for edu in education:
            file.write(f"- {edu.capitalize()}: [How you meet this requirement]\n")
        
        file.write("\n## Key Responsibilities\n")
        file.write("- [Responsibility 1]: [Relevant experience]\n")
        file.write("- [Responsibility 2]: [Relevant experience]\n")
        file.write("- [Responsibility 3]: [Relevant experience]\n")
        
        file.write("\n## Company Values Alignment\n")
        file.write("- [Value 1]: [How you demonstrate this value]\n")
        file.write("- [Value 2]: [How you demonstrate this value]\n")
        file.write("- [Value 3]: [How you demonstrate this value]\n")
    
    # Create matching skills file
    matching_skills_path = os.path.join(output_dir, "matching-skills.md")
    with open(matching_skills_path, 'w', encoding='utf-8') as file:
        file.write("# Skills Matching Analysis\n\n")
        
        file.write("## Technical Skills Match\n")
        file.write("| Job Requirement | My Skill Level | Evidence/Example |\n")
        file.write("|----------------|---------------|------------------|\n")
        for skill in technical_skills[:5]:  # Limit to top 5 for readability
            file.write(f"| {skill.capitalize()} | [Your level] | [Specific example] |\n")
        
        file.write("\n## Soft Skills Match\n")
        file.write("| Job Requirement | My Skill Level | Evidence/Example |\n")
        file.write("|----------------|---------------|------------------|\n")
        for skill in soft_skills[:5]:  # Limit to top 5 for readability
            file.write(f"| {skill.capitalize()} | [Your level] | [Specific example] |\n")
        
        file.write("\n## Experience Match\n")
        file.write("| Job Requirement | My Experience | Gap Analysis |\n")
        file.write("|----------------|---------------|-------------|\n")
        file.write(f"| {years_experience} experience | [Your experience] | [Any gap and how to address] |\n")
        
        file.write("\n## Keywords for Resume/Cover Letter\n")
        for keyword, count in keywords:
            file.write(f"- {keyword} ({count})\n")
        
        file.write("\n## Overall Match Assessment\n")
        file.write("- **Technical Skills**: [Percentage match]\n")
        file.write("- **Soft Skills**: [Percentage match]\n")
        file.write("- **Experience**: [Percentage match]\n")
        file.write("- **Overall**: [Percentage match]\n")
        
        file.write("\n## Action Items\n")
        file.write("- [Action 1 to improve application]\n")
        file.write("- [Action 2 to improve application]\n")
        file.write("- [Action 3 to improve application]\n")
    
    print(f"Analysis complete!")
    print(f"Requirements analysis saved to: {req_analysis_path}")
    print(f"Skills matching analysis saved to: {matching_skills_path}")

def main():
    parser = argparse.ArgumentParser(description="Analyze job descriptions to extract key requirements and skills")
    parser.add_argument("company", help="Company name (folder name in applications/active/)")
    args = parser.parse_args()
    
    company_name = args.company
    job_desc_path = f"applications/active/{company_name}/job-details/job-description.md"
    output_dir = f"applications/active/{company_name}/job-details"
    
    if not os.path.exists(job_desc_path):
        print(f"Error: Job description file not found at {job_desc_path}")
        sys.exit(1)
    
    analyze_job_description(job_desc_path, output_dir)

if __name__ == "__main__":
    main() 