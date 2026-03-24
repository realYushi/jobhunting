# Quality & Truthfulness Validation

## Phase 1: Truthfulness (MUST PASS)

Verify every claim against `base-resume.json` and `LinkedIn-CV-Profile.md`:

- [ ] **Experience**: Company names, positions, dates, responsibilities all match source
- [ ] **Metrics**: All percentages/numbers match actual accomplishments (no inflation)
- [ ] **Skills**: Every technology mentioned exists in candidate's verified skill set
- [ ] **Education**: GPA, institution, dates match official records
- [ ] **Projects**: All referenced projects exist in GitHub/portfolio

**If any false claim found: STOP and restart with verified info only.**

### Acceptable vs Unacceptable
- OK: Connecting transferable skills, highlighting relevant aspects, expressing learning interest
- NOT OK: Inventing projects/metrics, claiming unverified skills, exaggerating scope/impact

## Phase 2: Professional Quality (MUST PASS)

- [ ] **ATS**: Keywords from job description naturally integrated (no stuffing)
- [ ] **Grammar**: Error-free, professional tone
- [ ] **Structure**: Resume imports to Reactive Resume; cover letter 200-400 words, 3 paragraphs
- [ ] **Company-specific**: Research insights authentic and recent
- [ ] **No placeholders**: Zero bracket text or TODO items remaining
- [ ] **Consistent**: Messaging aligned across resume and cover letter

### Avoid
- Corporate buzzwords ("synergy", "leverage", "paradigm")
- Overused intensifiers ("meticulously", "crucial", "essential")
- Generic phrases ("dynamic environment", "cutting-edge technology")
- Vague descriptors ("robust", "seamless", "comprehensive")

## Final Gate

Both phases must pass. If either fails, fix and re-validate before submission.
