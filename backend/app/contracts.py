import re
from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator, field_validator
from .templates import TemplateId

Text = Annotated[str, Field(min_length=1, max_length=5000)]
Platform = Literal['instagram', 'facebook', 'linkedin']
Stage = Literal['validate', 'text_generation', 'artwork_generation', 'poster_rendering', 'quality_checks', 'persistence']
JobStatus = Literal['queued', 'running', 'partial', 'succeeded', 'failed', 'interrupted', 'cancelled']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Source(Contract):
    id: Text
    url: HttpUrl
    title: Text
    publisher: Text
    published_at: date | None = None
    retrieved_at: AwareDatetime


class Evidence(Contract):
    source_id: Text
    excerpt: Text
    locator: str | None = None
    relation: Literal['supports', 'contradicts']


class Claim(Contract):
    id: Text
    text: Text
    verification_status: Literal['unverified', 'supported', 'contradicted', 'mixed']
    verification_method: Text
    evidence: list[Evidence] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_support(self) -> Self:
        relations = {item.relation for item in self.evidence}
        required = {'supported': {'supports'}, 'contradicted': {'contradicts'}, 'mixed': {'supports', 'contradicts'}}
        if not required.get(self.verification_status, set()).issubset(relations):
            raise ValueError('Verification status requires corresponding evidence')
        return self


class ResearchReport(Contract):
    schema_version: Literal['1'] = '1'
    id: UUID
    origin: Literal['demo', 'live', 'provided']
    topic: Text
    summary: Text
    sources: list[Source] = Field(max_length=100)
    claims: list[Claim] = Field(max_length=100)
    content_opportunities: list[Text] = Field(default_factory=list)
    warnings: list[Text] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)
    prepared_at: AwareDatetime
    researched_at: AwareDatetime | None = None

    @model_validator(mode='after')
    def check_references(self) -> Self:
        if self.origin != 'provided' and (not self.sources or not self.claims):
            raise ValueError('Researched reports require sources and claims')
        if self.origin == 'provided' and (self.sources or self.claims or self.researched_at):
            raise ValueError('Provided facts must not imply independent research or citations')
        source_ids = {source.id for source in self.sources}
        if len(source_ids) != len(self.sources) or len({c.id for c in self.claims}) != len(self.claims):
            raise ValueError('Source and claim IDs must be unique within the report')
        if any(e.source_id not in source_ids for c in self.claims for e in c.evidence):
            raise ValueError('Evidence references an unknown source')
        if self.origin == 'live' and self.researched_at is None:
            raise ValueError('Live research requires a research timestamp')
        if self.origin == 'demo' and self.researched_at is not None:
            raise ValueError('Demo research must not imply a live research run')
        return self


class CampaignInput(Contract):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: str = Field(default='', max_length=5000)
    objective: str = Field(default='', max_length=1000)
    audience: str = Field(default='', max_length=500)
    platforms: list[Platform] = Field(default_factory=lambda: ['instagram'], min_length=1, max_length=3)
    event_details: str = Field(default='', max_length=5000)
    start_date: date | None = None
    end_date: date | None = None
    registration_url: HttpUrl | None = None
    approved_facts: list[Text] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def check_options(self) -> Self:
        if len(self.platforms) != len(set(self.platforms)):
            raise ValueError('Platforms must be unique')
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('End date must be on or after start date')
        return self






class ContentTrashState(Contract):
    id: UUID
    trashed_at: AwareDatetime | None






class GenerationRequest(Contract):
    creative_mode: Literal['shared', 'distinct_platforms'] = 'shared'
    export_mode: Literal['per_platform', 'shared_square'] = 'per_platform'
    background_theme: Literal['light', 'dark', 'colorful'] = 'dark'
    hashtag_count: int = Field(default=3, ge=0, le=10)
    caption_length: Literal['concise', 'balanced', 'detailed'] = 'balanced'
    template_id: TemplateId = 'editorial-v1'
    topic: Text
    report_id: UUID
    campaign_id: UUID | None = None
    content_type: Literal['educational', 'promotional', 'informational', 'announcement'] = 'educational'
    audience: Text = 'Beginners'
    tone: Text = 'Clear and professional'
    platforms: list[Platform] = Field(default_factory=lambda: ['instagram'], min_length=1, max_length=3)
    visual_style: Text = 'Clean editorial'
    background_subject: str = Field(default='', max_length=500)
    brand_profile_id: UUID | None = None
    concept_count: int = Field(default=1, ge=1, le=3)
    slide_count: int = Field(default=1, ge=1, le=5)
    customization_mode: Literal['automatic', 'custom'] = 'automatic'
    approved_user_facts: list[Text] = Field(default_factory=list, max_length=50)
    artwork_mode: Literal['pollinations', 'application_gradient'] = 'pollinations'
    brand_name: Annotated[str, Field(min_length=1, max_length=60)] = 'Content Studio'
    brand_color: Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')] = '#2563eb'

    @model_validator(mode='after')
    def unique_platforms(self) -> Self:
        if self.creative_mode == 'distinct_platforms' and self.export_mode != 'per_platform':
            raise ValueError('Distinct platform creatives require per-platform exports')
        if len(self.platforms) != len(set(self.platforms)):
            raise ValueError('Platforms must be unique')
        return self


def clean_claim_markers(value: str) -> str:
    return re.sub(r'\s*[\(\[]c\d+(?:\s*[,;]\s*c\d+)*[\)\]]', '', value, flags=re.IGNORECASE).strip()


class SlideText(Contract):
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    body: str = Field(max_length=1000)
    cta: str = Field(default='', max_length=160)
    layout: Literal['educational', 'promotional', 'announcement']
    claim_ids: list[Text] = Field(default_factory=list)


    @field_validator('headline', 'body', 'cta')
    @classmethod
    def clean_display_text(cls, value):
        cleaned = clean_claim_markers(value)
        if value and not cleaned:
            raise ValueError('Visible text cannot consist only of claim markers')
        return cleaned


class Caption(Contract):
    platform: Platform
    text: Text
    claim_ids: list[Text] = Field(default_factory=list)
    hashtags: list[Annotated[str, Field(pattern=r'^#[A-Za-z0-9_]{1,50}$')]] = Field(default_factory=list, max_length=10)

    @field_validator('hashtags', mode='before')
    @classmethod
    def normalize_hashtags(cls, value):
        if not isinstance(value, list):
            raise ValueError('Hashtags must be a list')
        normalized = []
        for tag in value:
            if not isinstance(tag, str):
                raise ValueError('Each hashtag must be text')
            tag = tag.strip()
            normalized.append(tag if tag.startswith('#') else '#' + tag)
        if len({tag.casefold() for tag in normalized}) != len(normalized):
            raise ValueError('Hashtags must be unique, ignoring case')
        return normalized


    @field_validator('text')
    @classmethod
    def clean_caption(cls, value):
        cleaned = clean_claim_markers(value)
        if not cleaned:
            raise ValueError('Caption cannot consist only of claim markers')
        return cleaned


class PlatformCreative(Contract):
    slides: list[SlideText] = Field(min_length=1, max_length=5)
    background_design: Text


class GeneratedConcept(Contract):
    platform_variants: dict[Platform, PlatformCreative] = Field(default_factory=dict)
    title: Text
    captions: list[Caption] = Field(min_length=1, max_length=3)
    slides: list[SlideText] = Field(min_length=1, max_length=5)
    background_design: Text
    warnings: list[Text] = Field(default_factory=list)








class GeneratedBatch(Contract):
    concepts: list[GeneratedConcept] = Field(min_length=1, max_length=3)


class RetryRequest(Contract):
    artwork_mode: Literal['pollinations', 'application_gradient'] | None = None


class JobView(Contract):
    id: UUID
    topic: str
    campaign_id: UUID | None
    parent_job_id: UUID | None
    can_retry: bool
    status: JobStatus
    current_stage: str
    stages: list[dict]
    results: list[dict]
    error: str | None
    created_at: str


class JobSummary(Contract):
    id: UUID
    topic: str
    campaign_id: UUID | None
    campaign_name: str | None
    parent_job_id: UUID | None
    status: JobStatus
    current_stage: str
    created_at: str
    can_retry: bool


class JobPage(Contract):
    items: list[JobSummary]
    total: int
    page: int
    limit: int


class RevisionRequest(Contract):
    base_version_id: UUID
    concept: GeneratedConcept
    template_id: TemplateId | None = None


class TemplateView(Contract):
    id: TemplateId
    name: str
    description: str


class PlatformPreset(Contract):
    platform: Platform
    preset_id: str
    name: str
    width: int
    height: int


class PlatformExport(PlatformPreset):
    template_id: TemplateId
    background_asset_id: UUID
    renders: list[UUID] = Field(min_length=1, max_length=5)
