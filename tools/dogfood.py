import os
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOGFOOD_ASSET_DIR = PROJECT_ROOT / "campaign_assets" / "dogfood"
DOGFOOD_PUBLIC_BASE = "/campaign-assets/dogfood"

DOGFOOD_CAMPAIGN_NICHE = (
    "automation freelancers and automation agencies"
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


DOGFOOD_SYSTEM_PROMPT = """You are writing one small personalized hook and one subject line
for a founder-led cold email introducing Scout to an automation freelancer or
automation agency.

The fixed Scout pitch is written separately by the founder and MUST NOT be
rewritten, summarized, expanded, or contradicted by you.

Your only jobs are:
1. Write a natural 1-2 sentence personalized hook based only on the supplied
   public research and contact information.
2. Write a personalized subject line.

SUBJECT RULES:
- Maximum 8 words.
- No exclamation marks.
- No fake urgency.
- Do not use words like "opportunity", "revolutionize", "unlock", "game-changing",
  "amazing", "guaranteed", "skyrocket", or "boost".
- Make it specific to the recipient's business or client-acquisition context.
- Avoid generic subjects such as "Try Scout", "AI for your business", or
  "A quick opportunity".

HOOK RULES:
- 1-2 sentences, ideally 25-45 words total.
- Mention one real, concrete detail from the supplied research when possible.
- Tie that detail to the reality of finding clients, researching prospects,
  personalizing outreach, or building demos.
- Do not invent clients, revenue, staff, tools, workflows, or pain points that
  the research does not support.
- Keep the tone human, warm, and founder-to-founder.
- Do not mention that you are an AI or that you are generating the copy.
- No markdown formatting.

OUTPUT EXACTLY:

SUBJECT: <subject line>
HOOK: <personalized hook>
"""


DOGFOOD_FIXED_PITCH = """Scout automates almost the entire client-acquisition process end to end. You just tell it the location, niche, and scale of businesses you want to target, and Scout finds the leads, researches them, drafts personalized outreach, builds a sample automation demo tailored to each business, and brings everything back to you for a quick review before sending the outreach to the lead. What used to take hours of finding the right clients, researching them, writing outreach, and building a demo to send over now happens in one workflow."""


DOGFOOD_CTA = """If you'd like to try it out, just reply to this email and I'd be happy to set you up with a free run. I'd also personally onboard you to it, and it's pretty simple."""


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
            f"{DOGFOOD_PUBLIC_BASE}/{spec['filename']}"
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

    for spec in DOGFOOD_ASSET_SPECS:
        item = {
            "path": paths[spec["key"]],
            "cid": spec["cid"],
            "alt": spec["alt"],
            "caption": spec["caption"],
        }

        if (
            spec["key"] == "video_thumbnail"
            and video_url
        ):
            item["link_url"] = video_url

        specs.append(item)

    return specs


def dogfood_demo_result() -> dict:
    public_paths = dogfood_public_paths()

    return {
        "lead_name": None,
        "lead_email": None,
        "inquiry": None,
        "form_screenshot": public_paths["form_screenshot"],
        "airtable_screenshot": public_paths["airtable_screenshot"],
        "email_screenshot": public_paths["email_screenshot"],
        "slack_screenshot": public_paths["slack_screenshot"],
        "video_thumbnail": public_paths["video_thumbnail"],
    }
