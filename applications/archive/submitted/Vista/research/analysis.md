# Job Analysis: Vista - Graduate Software Engineer

## 1. Role Overview

- **Position Level**: Graduate / entry-level software engineer
- **Department**: Engineering
- **Location**: Auckland, New Zealand; hybrid working noted in benefits
- **Company Context**: Vista Group builds software across the film industry: cinema websites, mobile apps, loyalty, digital signage, POS, kiosks, ticket scanning, scheduling, vouchers, refunds, payments, and staff workflows.

## 2. Requirements

### Must-Have Technical Skills

| Skill | Experience Level | Context/Usage |
| --- | --- | --- |
| C# / .NET 6 | Graduate exposure | Product areas use C# and .NET 6 across engineering. |
| SQL Server | Graduate exposure | Data layer for cinema and operational software. |
| TypeScript + React / Angular | Graduate exposure | Front-end product areas differ across Angular, TypeScript, and React. |
| Cloud software | Graduate exposure | Vista says its behind-the-scenes software targets cloud-based workflows. |
| Docker / Kubernetes / Octopus | Graduate exposure | Deployment stack used for product delivery. |
| Microsoft Azure and/or AWS | Graduate exposure | Cloud platforms used across product areas. |

### Soft Skills

- **Collaboration**: “One Crew” values connecting, helping, and collaborating across teams and functions.
- **Communication**: “Shine a Light” values explaining the why, asking when unclear, and avoiding information gaps.
- **Delivery**: “Make it Happen” values practical delivery as individuals and teams.
- **Growth Mindset**: “Chase Great” values continuous improvement.

---

## 3. Skills Matching

### Executive Summary

- **Deterministic Match Score**: 47% from `tools/match_score.py` literal keyword matching.
- **Adjusted Readiness**: Reasonable for a graduate role. The low score is mainly from literal misses around Angular, Kubernetes, AWS, and Vista-specific cinema domain keywords; the profile shows adjacent or partial matches across .NET, SQL Server, React/TypeScript, Docker, Azure, Vue, and production-facing web apps.
- **Competitive Advantage**: Product-minded full-stack experience, proven front-end delivery in Vue/TypeScript, a React/.NET/SQL Server/Azure project, and evidence of working from ambiguous requirements to production-facing software.

### Strong Matches

| Requirement | Candidate Evidence |
| --- | --- |
| TypeScript + front-end engineering | HALO Systems internship used Vue.js, TypeScript, SCSS, Mapbox, GeoJSON, and reusable SVG components for a production HMI dashboard. |
| React / TypeScript | Full-Stack Todo List project uses React and TypeScript frontend. Mini AI App Builder uses React + TypeScript. |
| C# / .NET / SQL Server | Full-Stack Todo List project uses .NET Core backend, SQL Server, and Azure deployment. Verified skills include C#, .NET Core, and SQL Server. |
| Azure / cloud deployment | Full-Stack Todo List deployed to Azure with GitHub Actions CI/CD. Certification: Microsoft Azure AI Fundamentals. |
| Docker | My Recipe Book project containerized with Docker; Docker is a verified DevOps skill. |
| Graduate-level learning and mentoring fit | AUT BCIS student graduating July 2026 with GPA 7.75/9.0; role offers strong mentoring and career development. |

### Partial Matches / Gaps

| Requirement | Current Evidence | Positioning |
| --- | --- | --- |
| Angular | Resume includes Angular as a seeded skill, but strongest verified framework experience is React and Vue.js. | Position as transferable TypeScript component-framework experience, not as deep Angular production experience. |
| Kubernetes / AWS | Seeded keywords in resume from JD; profile’s strongest verified DevOps evidence is Docker, GitHub Actions, Azure. | Mention interest/exposure only if asked; avoid claiming production Kubernetes/AWS depth. |
| Octopus Deploy | No verified evidence. | Do not claim experience. Frame as a deployment tool to learn alongside existing CI/CD experience. |
| Cinema domain | No direct film/cinema software experience. | Use product/domain interest and adjacent operational software: dashboards, client-facing web apps, booking/workflow-type systems. |

---

## 4. Application Strategy

### Strategic Keywords

- **High-Priority**: C#, .NET 6, SQL Server, TypeScript, React, Angular, Docker, Kubernetes, Azure, AWS, cloud, cinema software
- **Context Phrases**: “platform that connects the industry”, “powers the moviegoer experience”, “One Crew”, “Shine a Light”, “Make it Happen”, “Chase Great”

### Cover Letter Focus

1. **Opening Hook**: Vista is a New Zealand company with a global footprint building software that connects the film industry and powers the moviegoer experience.
2. **Key Selling Points**:
   - React/TypeScript + .NET Core + SQL Server + Azure project maps directly to Vista’s stack.
   - Vue/TypeScript internship delivering a production HMI dashboard shows front-end delivery in a real operational context.
   - Product-minded full-stack work at GrowLab maps to Vista’s practical delivery and collaboration values.
3. **Address Concerns**: Do not overclaim Angular/Kubernetes/AWS/Octopus. Emphasize TypeScript framework transferability, Docker/Azure/CI/CD foundation, and readiness to learn in a mentored graduate environment.

### Resume Optimization

- Prioritize Full-Stack Todo List and HALO Systems because they map directly to .NET/SQL Server/Azure and TypeScript UI work.
- Keep AI work present but secondary; Vista’s JD is broader product/platform engineering, not AI-specific.
- Ensure no unsupported claims around cinema-specific software or deep Kubernetes/AWS experience.

---

## 5. Red Flags & Concerns

- Literal match score is low (47%), but it underrates adjacent framework and cloud experience.
- Angular, Kubernetes, AWS, and Octopus are not strong verified areas; avoid claiming depth.
- Role is graduate-level, which reduces concern around missing full production ownership in every part of the stack.

---

## Match Score Output

```text
MATCH SCORE REPORT
========================================
Required (6/10):
  [OK  ] C#
  [MISS] .NET 6
  [OK  ] SQL Server
  [MISS] Angular
  [OK  ] TypeScript
  [OK  ] React
  [OK  ] Docker
  [MISS] Kubernetes
  [OK  ] Microsoft Azure
  [MISS] AWS
Preferred (1/6):
  [MISS] cinema websites
  [MISS] mobile app
  [MISS] POS systems
  [MISS] ticket scanning
  [OK  ] cloud
  [MISS] hybrid working
----------------------------------------
Required: 60% (x0.7)  Preferred: 17% (x0.3)
Overall:  47%
Verdict:  SKIP — unless dream role

NOTE: matching is literal keyword search. Before trusting the verdict,
scan MISS items for adjacent tech in the candidate profile (e.g., NestJS
for FastAPI, Azure for AWS) — those are partial matches the score ignores.

RED FLAGS: none detected
```
