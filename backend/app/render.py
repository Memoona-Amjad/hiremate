"""Turn structured CV / letter data into plain Markdown text (for copy, display and PDF)."""

from app.schemas import CoverLetter, CVData


def cv_to_markdown(cv: CVData) -> str:
    lines: list[str] = [f"# {cv.name}", "", f"**{cv.headline}**"]
    if cv.contact:
        lines += ["", cv.contact]  # blank lines keep these as separate paragraphs
    if cv.summary:
        lines += ["", "## Summary", cv.summary]
    if cv.skills:
        lines += ["", "## Skills", ", ".join(cv.skills)]
    if cv.experience:
        lines += ["", "## Experience"]
        for job in cv.experience:
            dates = " – ".join(d for d in (job.start, job.end) if d)
            where = ", ".join(p for p in (job.company, job.location) if p)
            lines.append(f"### {job.title} — {where}" + (f" ({dates})" if dates else ""))
            lines += [f"- {b}" for b in job.bullets]
    if cv.projects:
        lines += ["", "## Projects"]
        lines += [f"- **{p.name}**: {p.description}" for p in cv.projects]
    if cv.education:
        lines += ["", "## Education"]
        for ed in cv.education:
            lines.append(f"- {ed.degree}, {ed.institution}" + (f" ({ed.year})" if ed.year else ""))
    if cv.certifications:
        lines += ["", "## Certifications"]
        lines += [f"- {c}" for c in cv.certifications]
    return "\n".join(lines).strip()


def letter_to_text(letter: CoverLetter) -> str:
    return "\n\n".join([letter.greeting, *letter.paragraphs, letter.sign_off]).strip()


def word_count(text: str) -> int:
    return len(text.split())
