---
intent: Preserve uploaded DOCX comments and tracked revisions while adding AI comments, yellow highlights, and Beijing-time comment timestamps.
success_criteria: Generated annotated DOCX retains original comments/revisions, adds AI comments without ID collisions, highlights AI-anchored text in yellow, and writes comment dates with +08:00 timezone.
risk_level: medium
auto_approve: true
worktree: false
dirty_worktree: allow
---

## Steps

- [x] **Step 1: Replace cleaned-output base with original DOCX base**
action: Update `tools/document/reporting/docx_report.py` so annotated DOCX generation copies `contract_path` directly to `output_path` and no longer uses `clean_docx()` for the output document.
loop: false
verify: rg -n "clean_docx|shutil.copy2" tools/document/reporting/docx_report.py

- [x] **Step 2: Add paragraph text views and run-range anchors**
action: Add minimal dataclasses and helper functions in `tools/document/reporting/docx_report.py` to build paragraph-level review text views using accepted-revision semantics and map matched quoted text back to original DOCX runs.
loop: until tests pass
max_iterations: 3
verify: python -m py_compile tools/document/reporting/docx_report.py

- [x] **Step 3: Add yellow highlight and append-only AI comments**
action: Update comment insertion in `tools/document/reporting/docx_report.py` to use run ranges, add yellow highlight to AI-matched text, preserve existing comments, and allocate new comment IDs after existing IDs.
loop: until tests pass
max_iterations: 3
verify: python -m py_compile tools/document/reporting/docx_report.py

- [x] **Step 4: Write Beijing-time comment dates**
action: Update AI comment date generation in `tools/document/reporting/docx_report.py` to emit explicit `+08:00` timestamps instead of local naive time plus `Z`.
loop: false
verify: python -m py_compile tools/document/reporting/docx_report.py

- [x] **Step 5: Verify with focused DOCX fixtures**
action: Run lightweight local scripts that generate DOCX samples with existing comments/revisions, invoke `DocxReportGenerator.generate_annotated_docx`, and inspect resulting DOCX XML for preserved original markup, AI comment IDs, yellow highlight, and `+08:00` dates.
loop: until tests pass
max_iterations: 3
verify: python -m py_compile tools/document/reporting/docx_report.py
