import os
import re
from pathlib import Path
from typing import Dict, List

from strands import Agent

from agent import model


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOGFOOD_ASSET_DIR = (
    PROJECT_ROOT / "campaign_assets" / "dogfood"
)

DOGFOOD_PUBLIC_BASE = (
    "/campaign-assets/dogfood"
)

DOGFOOD_CAMPAIGN_NICHE = (
    "automation freelancers and automation agencies"
)

DEFAULT_DEMO_VIDEO_URL = (
    "https://www.youtube.com/watch?v=fGaTBK5onhc"
)

DOGFOOD_ASSET_SPECS = [
    {
        "key": "form_screenshot",
        "filename": "dashboard.png",
        "cid": "scout-dogfood-dashboard",
        "alt": "Scout dashboard",
        "caption": "Scout dashboard",
    },
    {
        "key": "airtable_screenshot",
        "filename": "research-breakdown.png",
        "cid": "scout-dogfood-research",
        "alt": "Scout research breakdown",
        "caption": "Research breakdown",
    },
    {
        "key": "email_screenshot",
        "filename": "outreach-draft.png",
        "cid": "scout-dogfood-draft",
        "alt": "Scout outreach draft",
        "caption": "Personalized outreach draft",
    },
    {
        "key": "slack_screenshot",
        "filename": "sent-email.png",
        "cid": "scout-dogfood-sent-email",
        "alt": "Scout sent email proof",
        "caption": "Email sent through the workflow",
    },
    {
        "key": "video_thumbnail",
        "filename": "video-thumbnail.png",
        "cid": "scout-dogfood-video",
        "alt": "Scout three minute walkthrough",
        "caption": "3-minute Scout walkthrough",
    },
]


DOGFOOD_SYSTEM_PROMPT = """You are classifying the target of a founder-led
cold email for Scout.

Scout is a client-acquisition automation product for automation freelancers
and automation agencies.

Your ONLY job is to classify the target as exactly one of:

AGENCY
FREELANCER

Use only the supplied business name, contact information, and public research.

Choose AGENCY when the target is an automation agency, consultancy, studio,
firm, company, collective, or other multi-person/business operation.

Choose FREELANCER when the target is clearly an individual independent
automation freelancer, solo consultant, independent operator, or one-person
freelance business.

When the evidence is ambiguous, choose AGENCY.

Return ONLY one word:
AGENCY
or
FREELANCER
"""


dogfood_agent = Agent(
    model=model,
    tools=[],
    system_prompt=DOGFOOD_SYSTEM_PROMPT,
    callback_handler=None,
)


DOGFOOD_FIXED_OPENING = """Running an automation {target_label} means spending hours every week on manual client acquisition—prospecting SMBs, researching them, drafting personalized pitches, and building custom sample demos just to land a discovery call. I built Scout to automate that entire outbound loop for {target_label}s like yours."""


DOGFOOD_FIXED_PITCH = """Scout automates almost the entire client-acquisition process end to end. You just tell it the location, niche, and scale of businesses you want to target, and Scout finds the leads, researches them, drafts personalized outreach, builds a sample automation demo mockups tailored to each business, and brings everything back to you for a quick review before sending the outreach to the lead. What used to take hours of finding the right clients, researching them, writing outreach, and building a demo to send over now happens in one workflow."""


DOGFOOD_CTA = """If you'd like to try it out, just reply to this email and I'd be happy to set you up with a free run. I'd also personally onboard you to it, and it's pretty simple."""


def _clean_inline_name(value: str) -> str:
    name = " ".join(
        str(value or "").strip().split()
    )

    return name


def _classify_target_fallback(
    business_name: str,
    research_profile: str,
) -> str:
    text = " ".join(
        [
            str(business_name or ""),
            str(research_profile or ""),
        ]
    ).lower()

    agency_patterns = [
        r"\bautomation agency\b",
        r"\bautomation agencies\b",
        r"\bautomation consultancy\b",
        r"\bautomation consulting\b",
        r"\bconsulting firm\b",
        r"\bconsultancy\b",
        r"\bagency\b",
        r"\bstudio\b",
        r"\bcollective\b",
        r"\bfirm\b",
        r"\bcompany\b",
        r"\bltd\b",
        r"\bllc\b",
        r"\binc\b",
        r"\bcorporation\b",
        r"\bsolutions\b",
        r"\bdigital transformation\b",
    ]

    freelancer_patterns = [
        r"\bautomation freelancer\b",
        r"\bautomation freelancers\b",
        r"\bfreelance automation\b",
        r"\bfreelancer\b",
        r"\bfreelance\b",
        r"\bindependent consultant\b",
        r"\bindependent automation\b",
        r"\bsolo consultant\b",
        r"\bone-person\b",
        r"\bself-employed\b",
    ]

    for pattern in freelancer_patterns:
        if re.search(pattern, text):
            return "freelancer"

    for pattern in agency_patterns:
        if re.search(pattern, text):
            return "agency"

    name_parts = [
        part
        for part in re.split(
            r"\s+",
            _clean_inline_name(business_name),
        )
        if part
    ]

    if (
        2 <= len(name_parts) <= 4
        and all(
            re.match(
                r"^[A-Z][A-Za-z'.-]*$",
                part,
            )
            for part in name_parts
        )
    ):
        return "freelancer"

    return "agency"


async def _classify_target(
    business_name: str,
    research_profile: str,
    contact_name: str = "",
    contact_title: str = "",
) -> str:
    prompt = (
        f"Business name: {business_name}\n"
        f"Contact name: {contact_name or 'Unknown'}\n"
        f"Contact title: {contact_title or 'Unknown'}\n\n"
        f"Public research:\n{research_profile}"
    )

    try:
        response = await dogfood_agent.invoke_async(
            prompt
        )

        classification = (
            str(response)
            .strip()
            .upper()
        )

        if "FREELANCER" in classification:
            return "freelancer"

        if "AGENCY" in classification:
            return "agency"

    except Exception:
        pass

    return _classify_target_fallback(
        business_name,
        research_profile,
    )


def _subject_for_target(
    target_type: str,
) -> str:
    if target_type == "freelancer":
        audience = "automation freelancers"
    else:
        audience = "automation agencies"

    return (
        "Built an autonomous client acquisition agent "
        f"for {audience}"
    )


def _greeting_name(
    business_name: str,
    contact_name: str = "",
) -> str:
    contact = _clean_inline_name(
        contact_name
    )

    if contact:
        return contact

    return (
        _clean_inline_name(
            business_name
        )
        or "there"
    )


def dogfood_asset_paths() -> Dict[str, str]:
    return {
        spec["key"]: str(
            DOGFOOD_ASSET_DIR / spec["filename"]
        )
        for spec in DOGFOOD_ASSET_SPECS
    }


def dogfood_public_paths() -> Dict[str, str]:
    return {
        spec["key"]: (
            f"{DOGFOOD_PUBLIC_BASE}/"
            f"{spec['filename']}"
        )
        for spec in DOGFOOD_ASSET_SPECS
    }


def missing_dogfood_assets() -> List[str]:
    paths = dogfood_asset_paths()

    return [
        key
        for key, path in paths.items()
        if not os.path.exists(path)
    ]


def dogfood_inline_specs(
    video_url: str = "",
) -> List[dict]:
    paths = dogfood_asset_paths()

    specs: List[dict] = []

    actual_video_url = (
        video_url.strip()
        if video_url
        else DEFAULT_DEMO_VIDEO_URL
    )

    for spec in DOGFOOD_ASSET_SPECS:
        item = {
            "path": paths[spec["key"]],
            "cid": spec["cid"],
            "alt": spec["alt"],
            "caption": spec["caption"],
        }

        if (
            spec["key"] == "video_thumbnail"
            and actual_video_url
        ):
            item["link_url"] = actual_video_url

        specs.append(item)

    return specs


def dogfood_demo_result() -> dict:
    public_paths = dogfood_public_paths()

    return {
        "lead_name": None,
        "lead_email": None,
        "inquiry": None,
        "form_screenshot": public_paths[
            "form_screenshot"
        ],
        "airtable_screenshot": public_paths[
            "airtable_screenshot"
        ],
        "email_screenshot": public_paths[
            "email_screenshot"
        ],
        "slack_screenshot": public_paths[
            "slack_screenshot"
        ],
        "video_thumbnail": public_paths[
            "video_thumbnail"
        ],
    }


async def draft_dogfood_pitch(
    business_name: str,
    research_profile: str,
    contact_name: str = "",
    contact_title: str = "",
) -> tuple[str, str]:
    target_type = await _classify_target(
        business_name=business_name,
        research_profile=research_profile,
        contact_name=contact_name,
        contact_title=contact_title,
    )

    target_label = (
        "automation freelancer"
        if target_type == "freelancer"
        else "automation agency"
    )

    subject = _subject_for_target(
        target_type
    )

    greeting_name = _greeting_name(
        business_name=business_name,
        contact_name=contact_name,
    )

    opening = DOGFOOD_FIXED_OPENING.format(
        target_label=target_label
    )

    body = (
        f"Hi {greeting_name},\n\n"
        f"{opening}\n\n"
        f"{DOGFOOD_FIXED_PITCH}\n\n"
        f"{DOGFOOD_CTA}\n\n"
        "I also put together a 3-minute video of Scout below.\n"
        f"{os.getenv('SCOUT_DEMO_VIDEO_URL', DEFAULT_DEMO_VIDEO_URL)}\n\n"
        "Best regards,\n"
        "Chalitha Widusahan\n"
        "Founder & CEO, Scout"
    )

    return subject, body