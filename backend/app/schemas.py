"""Pydantic models for everything the agents read and write.

The LLM is asked to answer in exactly these shapes (Gemini "structured output"),
so every agent gets clean, validated data instead of free text.
"""

from pydantic import BaseModel, Field


# ---------- CV ----------
class Experience(BaseModel):
    title: str
    company: str
    location: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: str
    institution: str
    year: str = ""


class Project(BaseModel):
    name: str
    description: str


class CVData(BaseModel):
    name: str
    headline: str = Field(description="Current job title or one-line professional headline")
    contact: str = Field(default="", description="Location, email, links on one line")
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


# ---------- Job ----------
class JobData(BaseModel):
    title: str
    company: str = ""
    seniority: str = Field(description="e.g. Junior, Mid-level, Senior, Lead")
    summary: str = Field(description="One or two sentences on what the role is about")
    required_skills: list[str]
    nice_to_have: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(description="Important words a recruiter or ATS would scan for")
    responsibilities: list[str] = Field(default_factory=list)


# ---------- Fit ----------
class SkillGap(BaseModel):
    skill: str
    importance: str = Field(description="'required' or 'nice-to-have'")
    why_it_matters: str = Field(description="One short sentence")


class FitScore(BaseModel):
    score: int = Field(description="Overall fit from 0 to 100")
    summary: str = Field(description="Two sentences explaining the score in plain English")
    matched_skills: list[str]
    missing_skills: list[SkillGap]
    quick_wins: list[str] = Field(description="Small, honest changes that would improve the CV")


# ---------- Writing ----------
class TailoredCV(CVData):
    skills: list[str] = Field(
        default_factory=list,
        description="Individual skill names, most relevant first. No category labels like 'Data:'.",
    )
    changes_made: list[str] = Field(
        default_factory=list, description="Short list of what was changed and why"
    )


class CoverLetter(BaseModel):
    greeting: str
    paragraphs: list[str]
    sign_off: str


class CriticReport(BaseModel):
    score: int = Field(description="Overall quality from 0 to 100")
    truthfulness: int = Field(description="0-100: does everything match the original CV and confirmed facts?")
    keyword_match: int = Field(description="0-100: are the job's key words naturally covered?")
    tone: int = Field(description="0-100: professional, confident, specific, not generic")
    length: int = Field(description="0-100: CV concise, letter under ~350 words")
    issues: list[str] = Field(description="Specific problems found, empty if none")
    feedback: str = Field(description="Clear instructions for the writer on what to fix")
