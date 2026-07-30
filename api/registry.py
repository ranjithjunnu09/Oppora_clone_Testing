"""
Feature registry — the single source of truth the UI is driven by.

Each of the 12 runnable features across the 9 standalone files is declared
here as a manifest: its inputs, its default model, and how its output should
be rendered. The React frontend reads /api/features and renders forms and
result panes generically from these manifests.

Adding a 10th file later means adding a manifest entry here and an adapter
function — zero frontend changes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FieldType = Literal["text", "textarea", "number", "boolean", "select", "json", "code"]


@dataclass
class Field_:
    name: str
    label: str
    type: FieldType = "text"
    default: Any = None
    placeholder: str = ""
    help: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)
    rows: int = 4
    min: int | None = None
    max: int | None = None


@dataclass
class Feature:
    id: str
    name: str
    category: str
    source_file: str
    source_of_truth: str
    summary: str
    use_case: str
    default_model: str
    result_type: str
    fields: list[Field_]
    call_count: str = "1"
    notes: str = ""
    is_reasoning_model: bool = False

    def to_dict(self) -> dict[str, Any]:
        from .scoring import SCORERS

        d = asdict(self)
        d["fields"] = [asdict(f) if not isinstance(f, dict) else f for f in self.fields]
        # Whether a deterministic rule rubric exists for this feature. Drives
        # the quality column in the UI so an unscored feature reads as "no
        # rubric yet" rather than as a zero.
        d["scoreable"] = self.id in SCORERS
        return d


CATEGORIES = [
    {
        "id": "classification",
        "name": "Classification",
        "description": "Small, high-frequency classifiers and extractors behind enrichment and reply triage.",
        "icon": "Tags",
    },
    {
        "id": "email_generation",
        "name": "Email Generation",
        "description": "Everything that writes email content, from full campaign sequences to a single merge-tag value.",
        "icon": "Mail",
    },
    {
        "id": "lead_scoring",
        "name": "Lead Scoring",
        "description": "Deciding which leads are worth pursuing, and how well each fits the filters.",
        "icon": "Target",
    },
]

# Claude first — these are the benchmark targets. The gpt-* entries are the
# models production actually runs on, kept so every Claude run can be compared
# against the real baseline rather than in isolation.
#
# Each feature's `default_model` below stays set to its PRODUCTION model on
# purpose: it documents what Oppora runs today. The UI's initial selection is
# a Claude model, set in the frontend store.
MODEL_PRESETS = [
    # Frontier — the incumbents being migrated away from.
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    # Production baseline. Keep this selectable: "quality stayed the same" is
    # meaningless without the thing it stayed the same AS. Needs OPENAI_API_KEY.
    "gpt-4.1-mini",
]

# Open-source candidates. These have no fixed endpoint — they run wherever you
# host them (vLLM, Ollama, TGI, Together, Groq, Fireworks...), so set the base
# URL in the UI header and the model name is passed straight through.
#
# Left as suggestions rather than presets because the exact served model string
# depends on your deployment, and a wrong name fails confusingly. Type the name
# your endpoint actually serves.
OPEN_MODEL_SUGGESTIONS = [
    "llama-3.3-70b-instruct",
    "qwen2.5-72b-instruct",
    "mistral-small-latest",
    "deepseek-v3",
    "gemma-2-27b-it",
]


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

_classify_company_industry = Feature(
    id="classify_company_industry",
    name="Company Industry & Size",
    category="classification",
    source_file="classification/classification_helpers.py",
    source_of_truth="sales/sales_open_ai.py :: get_companies_industry()",
    summary="Fills in industry and employee-size bucket for a batch of companies from raw scraped data.",
    use_case="Runs during company enrichment, after a domain or LinkedIn URL is discovered but before the company is usable for targeting.",
    default_model="claude-sonnet-5",
    result_type="company_industry",
    call_count="1",
    notes="Production types `industry` as a dynamically built Enum over the full LinkedIn taxonomy; simplified to a plain string here.",
    fields=[
        Field_(
            name="companies",
            label="Companies",
            type="json",
            rows=12,
            required=True,
            help="List of company dicts with whatever raw fields you have.",
            default=[
                {
                    "name": "Notion",
                    "domain": "notion.so",
                    "linkedin_url": "https://linkedin.com/company/notionhq",
                    "raw_text": "Notion is an all-in-one workspace for notes, docs, and project management. ~2,000 employees per LinkedIn.",
                }
            ],
        )
    ],
)

_extract_email_pattern = Feature(
    id="extract_email_pattern",
    name="Email Pattern Extraction",
    category="classification",
    source_file="classification/classification_helpers.py",
    source_of_truth="sales/sales_open_ai.py :: extract_email_pattern()",
    summary="Infers a company's email format from one known name/email pair.",
    use_case="Once one real address at a company is known, this pattern lets Oppora guess addresses for every other lead at that same company.",
    default_model="claude-sonnet-5",
    result_type="text_badge",
    fields=[
        Field_(name="lead_name", label="Lead name", required=True, default="Sarah Johnson"),
        Field_(
            name="lead_email",
            label="Known email",
            required=True,
            default="sarah.johnson@notion.so",
        ),
    ],
)

_predict_email_status = Feature(
    id="predict_email_status",
    name="Reply Status Prediction",
    category="classification",
    source_file="classification/classification_helpers.py",
    source_of_truth="sales/sales_open_ai.py :: email_status_predict()",
    summary="Classifies an inbound reply into one of 12 CRM statuses.",
    use_case="Fires on every inbound reply to move the lead to the right CRM stage automatically.",
    default_model="claude-sonnet-5",
    result_type="status_badge",
    is_reasoning_model=True,
    notes=(
        "The only feature in the repo on a reasoning model (o4-mini, reasoning_effort=high). "
        "IMPORTANT when benchmarking Claude here: `reasoning_effort` is not supported through "
        "Anthropic's OpenAI-compat layer, so it is stripped and the Claude run is NOT "
        "thinking-enabled. That makes this the one feature where Claude vs o4-mini is not "
        "apples-to-apples."
    ),
    fields=[
        Field_(
            name="email_content",
            label="Inbound reply",
            type="textarea",
            rows=8,
            required=True,
            default="Thanks for reaching out! Can we set up a call next Tuesday at 2pm?",
        )
    ],
)

_predict_delivery_failure = Feature(
    id="predict_delivery_failure",
    name="Bounce vs Reject Triage",
    category="classification",
    source_file="classification/classification_helpers.py",
    source_of_truth="sales/sales_open_ai.py :: delivery_failure_predict()",
    summary="Decides whether a delivery failure is a bad address (bounced) or a refused message (rejected).",
    use_case="Protects sender reputation: bounced addresses get purged from the list, rejected ones signal a deliverability problem to fix.",
    default_model="claude-sonnet-5",
    result_type="status_badge",
    fields=[
        Field_(
            name="subject",
            label="NDR subject",
            required=True,
            default="Undeliverable: Re: Quick question",
        ),
        Field_(
            name="body_content",
            label="NDR body (plain text)",
            type="textarea",
            rows=8,
            required=True,
            default="Your message wasn't delivered because the recipient's email address wasn't found. Please check the recipient's email address and try to resend. 550 5.1.1 The email account that you tried to reach does not exist.",
        ),
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL GENERATION
# ─────────────────────────────────────────────────────────────────────────────

_email_sequence = Feature(
    id="email_sequence",
    name="Campaign Email Sequence",
    category="email_generation",
    source_file="email_generation/email_generation.py",
    source_of_truth="sales/campaigns/utils.py :: build_personalized_email_prompt() + generate_personalized_emails_bulk()",
    summary="Generates a full cold-outreach sequence: one initial email plus N follow-ups.",
    use_case="The core campaign builder. Driven by a long style prompt covering word counts, spam-word blacklist, merge tags, CTA rules and follow-up cadence.",
    default_model="claude-sonnet-5",
    result_type="email_sequence",
    notes="The largest system prompt in the repo. Watch the cache-hit rate here.",
    fields=[
        Field_(
            name="template_prompt",
            label="What to pitch",
            type="textarea",
            rows=5,
            required=True,
            help="The brief. Overrides the ICP context for the offer and CTA.",
            default="We help B2B SaaS sales teams book more meetings with an AI SDR that researches each prospect and writes personalized outreach. Offer: 30% off the starter plan for the first year if they start a trial this month.",
        ),
        Field_(
            name="sequence_steps",
            label="Sequence steps",
            type="number",
            default=3,
            min=1,
            max=8,
            help="1 initial + (steps - 1) follow-ups.",
        ),
        Field_(
            name="include_spintax",
            label="Include spintax",
            type="boolean",
            default=False,
            help="Wraps greeting, CTA and sign-off in {random}a|b|c{endrandom}.",
        ),
        Field_(
            name="lead_data",
            label="Prospect",
            type="json",
            rows=6,
            default={
                "name": "Marcus Delgado",
                "job_title": "VP of Sales",
                "company_name": "Ledgerline",
            },
        ),
        Field_(
            name="icp_profile",
            label="ICP profile",
            type="json",
            rows=16,
            help="Leave empty to trigger the NO ICP CONFIGURED branch of the prompt.",
            default={
                "company_context": {
                    "description": "AI-powered sales prospecting and outreach platform for outbound teams",
                    "value_proposition": "Book more qualified meetings without adding headcount",
                    "key_differentiators": [
                        "Per-prospect research",
                        "Reply-rate optimized copy",
                        "CRM-native",
                    ],
                },
                "buyer_persona": {
                    "job_titles": ["VP Sales", "Head of Sales", "Director of Sales"],
                    "pain_points": [
                        "Reps spend hours on manual research",
                        "Low reply rates",
                        "Ramping SDRs is slow",
                    ],
                    "buying_triggers": [
                        "Recently raised funding",
                        "Hiring SDRs",
                        "Missed pipeline targets",
                    ],
                },
                "messaging": {
                    "preferred_tone": "consultative",
                    "elevator_pitch": "An AI SDR that researches every prospect and writes outreach that gets replies",
                    "call_to_action": "Start a free trial",
                },
                "target_company": {"industries": ["SaaS", "Fintech"]},
            },
        ),
        Field_(
            name="writing_style",
            label="Writing style",
            type="json",
            rows=8,
            default={
                "tone": "direct and warm",
                "avg_sentence_length": 16,
                "greeting_style": "Hi {first_name},",
                "sign_off_style": "Best, {from_first_name}",
                "forbidden_phrases": ["touching base", "circle back"],
            },
        ),
        Field_(
            name="research_brief",
            label="Research brief",
            type="textarea",
            rows=4,
            help="Optional web-research context about this specific prospect.",
        ),
    ],
)

_campaign_ai_variable = Feature(
    id="campaign_ai_variable",
    name="Campaign AI Variable",
    category="email_generation",
    source_file="email_generation/campaign_ai_variable.py",
    source_of_truth="sales/campaigns/utils.py :: _generate_ai_template_response()",
    summary="Fills a single merge-tag variable, such as {ai_icebreaker}, for one lead.",
    use_case="Highest per-item volume call in the entire platform: runs once per lead. A 500-lead AI-personalized campaign fires this 500 times.",
    default_model="claude-sonnet-5",
    result_type="text",
    notes="Output is post-processed to strip em/en dashes, because the prompt rule alone is not reliable.",
    fields=[
        Field_(
            name="prompt",
            label="Variable prompt",
            type="textarea",
            rows=5,
            required=True,
            help="The AiTemplate prompt. Placeholders below are substituted before the call.",
            default="Write one warm, specific opening line referencing {first_name}'s role as {lead_job_title} at {company}, hinting we help teams like theirs book more sales meetings with AI-driven outreach.",
        ),
        Field_(name="company", label="{company}", default="Notion"),
        Field_(name="first_name", label="{first_name}", default="Sarah"),
        Field_(name="last_name", label="{last_name}", default="Johnson"),
        Field_(name="lead_job_title", label="{lead_job_title}", default="VP of Sales"),
        Field_(name="job_location", label="{job_location}", default=""),
        Field_(name="job_opening_title", label="{job_opening_title}", default=""),
        Field_(name="position", label="{position}", default=""),
    ],
)

_reply_agent_chain = Feature(
    id="reply_agent_chain",
    name="Automatic Reply Agent",
    category="email_generation",
    source_file="email_generation/reply_agent_chain.py",
    source_of_truth="sales/agent/reply_agents.py :: classify_intent -> decide_attachments -> draft_reply -> guardrail_check -> extract_referred_contacts -> ai_send_decision",
    summary="The full pipeline that fires automatically on a real inbound reply, with no human involved.",
    use_case="Six chained nodes: classify intent, decide attachments, draft the reply, run a safety guardrail, extract referred contacts, then optionally decide send-vs-draft when autonomy is on.",
    default_model="claude-sonnet-5",
    result_type="chain",
    call_count="4-8",
    notes="Known production inconsistency, replicated not fixed: classify_intent's schema types intent as the CRM status enum, but its own prompt asks for a different, non-overlapping category set.",
    fields=[
        Field_(
            name="prospect_message",
            label="Inbound reply",
            type="textarea",
            rows=7,
            required=True,
            default="Thanks for reaching out! This actually looks interesting, can you send over a case study or two? Also loop in my colleague on this, Alex Kim (alex.kim@example.com), he's our technical lead and should see this too.",
        ),
        Field_(
            name="attachments",
            label="Available attachments",
            type="json",
            rows=10,
            default=[
                {
                    "id": 1,
                    "file_name": "case_study_saas.pdf",
                    "description": "Case study: SaaS company grew reply rate 3x",
                },
                {"id": 2, "file_name": "pricing_sheet.pdf", "description": "Current pricing tiers"},
                {
                    "id": 3,
                    "file_name": "company_overview.pdf",
                    "description": "General company one-pager",
                },
            ],
        ),
        Field_(
            name="autonomy",
            label="Autonomy (run send decision)",
            type="boolean",
            default=False,
            help="Adds the 6th node: the AI decides send vs. hold for human review.",
        ),
        Field_(name="current_attempt", label="Follow-up attempt", type="number", default=0, min=0, max=10),
        Field_(
            name="meeting_tool_url",
            label="Meeting link",
            default="https://cal.com/demo-rep/15min",
        ),
        Field_(name="tone", label="Tone", default="friendly-professional"),
    ],
)

_reply_generation = Feature(
    id="reply_generation",
    name="Manual AI Reply",
    category="email_generation",
    source_file="email_generation/reply_generation.py",
    source_of_truth="sales/campaigns/api/v1/views.py :: _generate_ai_reply()",
    summary="Drafts one reply from the conversation history plus a free-text instruction.",
    use_case="The 'AI reply' button a rep clicks in the campaign UI. Human-in-the-loop, distinct from the automatic agent chain.",
    default_model="claude-sonnet-5",
    result_type="text",
    fields=[
        Field_(
            name="context",
            label="Conversation",
            type="json",
            rows=16,
            required=True,
            default={
                "subject": "Quick question about your outbound process",
                "main_message": "Hi Marcus, I help SaaS sales teams book more meetings with an AI SDR that researches each prospect and writes the outreach. Worth a quick chat?",
                "follow_ups": [
                    {
                        "subject": None,
                        "message": "Just floating this back up, teams using us see ~20% higher reply rates.",
                    }
                ],
                "replies": [
                    {
                        "subject": "RE: Quick question",
                        "message": "Interesting. How is your data different from Apollo, and do you integrate with HubSpot? What's pricing like?",
                    }
                ],
            },
        ),
        Field_(
            name="user_instruction",
            label="Instruction",
            type="textarea",
            rows=3,
            default="Answer their questions about data, HubSpot integration, and pricing; offer a short call.",
        ),
        Field_(name="tone", label="Tone", default="friendly and consultative"),
    ],
)

_single_email_generation = Feature(
    id="single_email_generation",
    name="Single Templated Email",
    category="email_generation",
    source_file="email_generation/single_email_generation.py",
    source_of_truth="sales/sales_open_ai.py :: generate_ai_email()",
    summary="Generates one standalone HTML email with merge tags left as literal placeholders.",
    use_case="Template generation. Oppora substitutes the real values per recipient at send time, so the model never sees actual names.",
    default_model="claude-sonnet-5",
    result_type="email_single",
    fields=[
        Field_(
            name="first_name",
            label="First name",
            default="{first_name}",
            help="Leave as the literal merge tag to match production behaviour.",
        ),
        Field_(name="last_name", label="Last name", default="{last_name}"),
        Field_(name="company", label="Company", default="{company}"),
    ],
)

_lead_email_address_generation = Feature(
    id="lead_email_address_generation",
    name="Email Address Guessing",
    category="email_generation",
    source_file="email_generation/lead_email_address_generation.py",
    source_of_truth="sales/sales_open_ai.py :: generate_lead_email()",
    summary="Generates up to 5 candidate email addresses for a person from known colleague addresses.",
    use_case="Contact discovery, not content generation. Feeds verification: the candidates get tested and the deliverable one is kept.",
    default_model="claude-sonnet-5",
    result_type="email_list",
    fields=[
        Field_(name="name", label="Lead name", required=True, default="John Dev"),
        Field_(name="company", label="Company", required=True, default="Bluebix Inc"),
        Field_(
            name="other_leads",
            label="Known colleague emails",
            type="textarea",
            rows=5,
            required=True,
            default="Name: Charlotte Kris\nEmail: charlotte.kris@bluebixinc.com",
        ),
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# LEAD SCORING
# ─────────────────────────────────────────────────────────────────────────────

_lead_recommendation = Feature(
    id="lead_recommendation",
    name="Lead Recommendation (self-correcting)",
    category="lead_scoring",
    source_file="lead_scoring/lead_recommendation.py",
    source_of_truth="sales/sales_open_ai.py :: top_lead_generate_with_quality_check()",
    summary="Generate leads, audit them with an independent QA pass, then regenerate only if the audit fails.",
    use_case="Self-correcting loop. Two calls when QA passes (score >= 80 and acceptable), three when it fails and a fix is needed.",
    default_model="claude-sonnet-5",
    result_type="company_leads",
    call_count="2-3",
    notes="The QA system prompt is deliberately over 1,024 tokens and static, so OpenAI prompt caching activates. Request-specific data is sent last, in the user message.",
    fields=[
        Field_(
            name="prompt",
            label="Lead request",
            type="textarea",
            rows=7,
            required=True,
            default="Recommend up to 2 leads at each of these companies for an AI SDR sales tool: Stripe, Notion. Prioritize VP/Director of Sales or Revenue Operations. For each lead set ai_recommendation to a short sentence on why they're a good fit, and use id=1, 2, 3... sequentially across the whole result.",
        )
    ],
)

_lead_scoring_batch = Feature(
    id="lead_scoring_batch",
    name="Batch Lead Scoring",
    category="lead_scoring",
    source_file="lead_scoring/lead_scoring_batch.py",
    source_of_truth="planner/tools/planner_tools.py :: filter_company_leads_by_filters()",
    summary="Scores up to 200 leads at one company against filter criteria in a single call.",
    use_case="Highest per-call token count in the whole AI surface. Supports a priority-ladder fallback mode that tags each lead with the lowest tier it fits.",
    default_model="claude-sonnet-5",
    result_type="lead_table",
    notes="Ranking and slicing after scoring is pure Python, replicated exactly. The valid-id guard defends against cross-batch id hallucination.",
    fields=[
        Field_(name="company_name", label="Company", required=True, default="Notion"),
        Field_(
            name="filters",
            label="Filters",
            type="json",
            rows=8,
            required=True,
            default={
                "departments": ["Sales"],
                "management_level": ["VP", "Director"],
                "location": "New York",
                "title": ["VP of Sales", "Director of Sales"],
            },
        ),
        Field_(
            name="leads",
            label="Leads to score",
            type="json",
            rows=20,
            required=True,
            default=[
                {
                    "id": 101,
                    "name": "Sarah Johnson",
                    "title": "VP of Sales",
                    "location": "New York, NY",
                    "department": "Sales",
                    "management_level": "VP",
                    "experience_years": 12,
                    "headline": "VP of Sales @ Notion | Scaling B2B revenue teams",
                    "skills": ["SaaS sales", "team leadership", "pipeline management"],
                    "summary": "Leads a 40-person sales org, previously scaled ARR 3x at a prior startup.",
                },
                {
                    "id": 102,
                    "name": "Mike Chen",
                    "title": "Sales Development Rep",
                    "location": "New York, NY",
                    "department": "Sales",
                    "management_level": "Individual Contributor",
                    "experience_years": 1,
                    "headline": "SDR at Notion",
                    "skills": ["cold outreach", "SFDC"],
                    "summary": "Entry-level SDR, 6 months in role.",
                },
                {
                    "id": 103,
                    "name": "Priya Patel",
                    "title": "Director of Revenue Operations",
                    "location": "Austin, TX",
                    "department": "Sales",
                    "management_level": "Director",
                    "experience_years": 8,
                    "headline": "Director of RevOps | Notion",
                    "skills": ["revops", "forecasting", "CRM architecture"],
                    "summary": "Owns the full revenue operations function including forecasting and tooling.",
                },
                {
                    "id": 104,
                    "name": "Tom Wu",
                    "title": "Field Technician",
                    "location": "New York, NY",
                    "department": "Operations",
                    "management_level": "Individual Contributor",
                    "experience_years": 5,
                    "headline": "Field Technician",
                    "skills": ["hardware repair"],
                    "summary": "On-site hardware support technician.",
                },
                {
                    "id": 105,
                    "name": "Elena Ruiz",
                    "title": "Head of Sales",
                    "location": "London, UK",
                    "department": "Sales",
                    "management_level": "VP",
                    "experience_years": 10,
                    "headline": "Head of Sales, EMEA @ Notion",
                    "skills": ["EMEA GTM", "enterprise sales"],
                    "summary": "Runs EMEA sales; based in London, not the required geography for this search.",
                },
            ],
        ),
        Field_(
            name="main_objective",
            label="Main objective (tie-breaker)",
            type="textarea",
            rows=2,
            default="",
        ),
        Field_(
            name="fallback_sets",
            label="Priority ladder (fallback tiers)",
            type="json",
            rows=8,
            help="Leave empty for simple filter mode. Provide tiers to switch to the priority-ladder prompt.",
            default=[],
        ),
        Field_(
            name="total_required",
            label="Top N to select",
            type="number",
            default=2,
            min=1,
            max=200,
        ),
    ],
)


FEATURES: list[Feature] = [
    _classify_company_industry,
    _extract_email_pattern,
    _predict_email_status,
    _predict_delivery_failure,
    _email_sequence,
    _campaign_ai_variable,
    _reply_agent_chain,
    _reply_generation,
    _single_email_generation,
    _lead_email_address_generation,
    _lead_recommendation,
    _lead_scoring_batch,
]

FEATURES_BY_ID: dict[str, Feature] = {f.id: f for f in FEATURES}
