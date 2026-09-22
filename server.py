import html
import os
import random
import re
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import Client, create_client
from strands import Agent

from agent import (
    draft_outreach_pitch,
    find_businesses,
    model,
    research_business,
    build_real_demo,
)

from tools.dogfood import (
    DOGFOOD_CAMPAIGN_NICHE,
    DOGFOOD_CTA,
    DOGFOOD_FIXED_PITCH,
    DOGFOOD_SYSTEM_PROMPT,
    DOGFOOD_ASSET_DIR,
    dogfood_asset_paths,
    dogfood_demo_result,
    dogfood_inline_specs,
    dogfood_public_paths,
    missing_dogfood_assets,
)

from tools.mailbox import (
    send_email_smtp,
    verify_mailbox_credentials,
)


app = FastAPI(title="Agents for Humans API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


os.makedirs("screenshots", exist_ok=True)
os.makedirs(DOGFOOD_ASSET_DIR, exist_ok=True)

app.mount(
    "/screenshots",
    StaticFiles(directory="screenshots"),
    name="screenshots",
)

app.mount(
    "/campaign-assets",
    StaticFiles(directory="campaign_assets"),
    name="campaign-assets",
)


supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Optional[Client] = (
    create_client(
        supabase_url,
        supabase_key,
    )
    if supabase_url and supabase_key
    else None
)


SCREENSHOTS_BUCKET = "screenshots"
USER_SETTINGS_TABLE = "user_settings"

CAMPAIGN_NORMAL = "normal"
CAMPAIGN_DOGFOOD = "dogfood"

# ---------------------------------------------------------------------------
# EMAIL SEND RATE LIMITING
# ---------------------------------------------------------------------------
# Every send goes out through the user's own Gmail mailbox, so these limits
# exist to keep that mailbox from getting flagged/suspended for spam-like
# sending behaviour. Applied to every campaign type, including "dogfood",
# since the founder's Gmail account needs the same protection.
DAILY_EMAIL_LIMIT = 10
MIN_EMAIL_GAP_SECONDS = 180  # 3 minutes
MAX_EMAIL_GAP_SECONDS = 420  # 7 minutes


def _utc_day_start() -> datetime:
    """Start of the current UTC calendar day (the daily limit resets here)."""
    now = datetime.now(timezone.utc)
    return now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def enforce_daily_email_limit(user_id: str) -> None:
    """Raises 429 if this user has already sent DAILY_EMAIL_LIMIT emails
    today (UTC). Counts actual sends recorded in outreach_history, not how
    many times Scout has been run — so skipped/unsent runs don't count
    against the limit.
    """
    if not supabase:
        return

    res = (
        supabase
        .table("outreach_history")
        .select("id", count="exact")
        .eq("user_name", user_id)
        .gte("created_at", _utc_day_start().isoformat())
        .execute()
    )

    sent_today = res.count or 0

    if sent_today >= DAILY_EMAIL_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily email limit reached ({DAILY_EMAIL_LIMIT}/"
                f"{DAILY_EMAIL_LIMIT} sent today). Try again after "
                "midnight UTC."
            ),
        )


def enforce_send_gap(user_id: str) -> None:
    """Raises 429 if it's too soon after this user's last send. The actual
    minimum gap for each send is randomised (3-7 min) and stored by
    schedule_next_send_window() right after a successful send.
    """
    if not supabase:
        return

    res = (
        supabase
        .table(USER_SETTINGS_TABLE)
        .select("next_send_allowed_at")
        .eq("user_name", user_id)
        .limit(1)
        .execute()
    )

    if not res.data or not res.data[0].get("next_send_allowed_at"):
        return

    next_allowed = datetime.fromisoformat(
        res.data[0]["next_send_allowed_at"]
    )
    now = datetime.now(timezone.utc)

    if now < next_allowed:
        wait_seconds = int(
            (next_allowed - now).total_seconds()
        )
        minutes, seconds = divmod(
            max(wait_seconds, 1),
            60,
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Please wait {minutes}m {seconds}s before sending "
                "your next email. Scout spaces sends out so your "
                "mailbox doesn't look like it's spamming."
            ),
        )


def schedule_next_send_window(user_id: str) -> None:
    """Called right after a successful send. Picks a fresh random 3-7 min
    gap and stores when the *next* send is allowed for this user.

    Uses a plain UPDATE, never an insert. By the time this runs,
    get_mailbox_credentials() has already read this user's row, so it's
    guaranteed to exist — there is nothing to insert. A blind upsert()
    risks Postgres treating it as a fresh INSERT (if the conflict target
    isn't matched for any reason) and tripping the NOT NULL constraints
    on gmail_address / gmail_app_password, which is what caused sends to
    fail after a successful SMTP send.
    """
    if not supabase:
        return

    next_allowed = datetime.now(timezone.utc) + timedelta(
        seconds=random.randint(
            MIN_EMAIL_GAP_SECONDS,
            MAX_EMAIL_GAP_SECONDS,
        )
    )

    supabase.table(USER_SETTINGS_TABLE).update(
        {"next_send_allowed_at": next_allowed.isoformat()}
    ).eq("user_name", user_id).execute()

FOUNDER_USER_ID = os.getenv(
    "SCOUT_FOUNDER_USER_ID",
    ""
).strip()

SCOUT_DEMO_VIDEO_URL = os.getenv(
    "SCOUT_DEMO_VIDEO_URL",
    ""
).strip()


dogfood_agent = Agent(
    model=model,
    tools=[],
    system_prompt=DOGFOOD_SYSTEM_PROMPT,
    callback_handler=None,
)


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
def get_verified_user_id(
    authorization: Optional[str] = Header(None),
) -> str:
    if not supabase:
        raise HTTPException(
            status_code=500,
            detail="Supabase isn't configured on the server.",
        )

    if (
        not authorization
        or not authorization.lower().startswith("bearer ")
    ):
        raise HTTPException(
            status_code=401,
            detail="Not signed in. Please log in and try again.",
        )

    token = authorization.split(" ", 1)[1].strip()

    try:
        user_res = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please log in again.",
        )

    if not user_res or not user_res.user:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please log in again.",
        )

    return user_res.user.id


def require_founder(user_id: str) -> None:
    if not FOUNDER_USER_ID:
        raise HTTPException(
            status_code=403,
            detail=(
                "Founder campaign access is not configured yet. "
                "Set SCOUT_FOUNDER_USER_ID on the backend."
            ),
        )

    if user_id != FOUNDER_USER_ID:
        raise HTTPException(
            status_code=403,
            detail="This campaign is restricted to the Scout founder.",
        )


# ---------------------------------------------------------------------------
# MAILBOX
# ---------------------------------------------------------------------------
def get_mailbox_credentials(
    user_id: str,
) -> tuple[str, str]:
    if not supabase:
        raise HTTPException(
            status_code=500,
            detail=(
                "Supabase isn't configured on the server, "
                "so mailbox settings can't be read."
            ),
        )

    res = (
        supabase
        .table(USER_SETTINGS_TABLE)
        .select("gmail_address, gmail_app_password")
        .eq("user_name", user_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        raise HTTPException(
            status_code=400,
            detail=(
                "No mailbox connected yet. Add your Gmail address "
                "and App Password in Settings before sending."
            ),
        )

    row = res.data[0]

    return (
        row["gmail_address"],
        row["gmail_app_password"],
    )


def upload_screenshot_to_storage(
    local_path: Optional[str],
) -> Optional[str]:
    if (
        not supabase
        or not local_path
        or not os.path.exists(local_path)
    ):
        return local_path

    try:
        file_ext = (
            os.path.splitext(local_path)[1]
            or ".png"
        )

        storage_path = f"{uuid.uuid4().hex}{file_ext}"

        content_type = "image/png"

        lowered = file_ext.lower()

        if lowered in [".jpg", ".jpeg"]:
            content_type = "image/jpeg"
        elif lowered == ".gif":
            content_type = "image/gif"
        elif lowered == ".webp":
            content_type = "image/webp"

        with open(local_path, "rb") as file:
            supabase.storage.from_(SCREENSHOTS_BUCKET).upload(
                path=storage_path,
                file=file,
                file_options={
                    "content-type": content_type,
                },
            )

        return (
            supabase
            .storage
            .from_(SCREENSHOTS_BUCKET)
            .get_public_url(storage_path)
        )

    except Exception:
        print(
            f"WARNING: Failed to upload {local_path} "
            "to Supabase Storage:"
        )
        traceback.print_exc()
        return local_path


# ---------------------------------------------------------------------------
# EMAIL COPY HELPERS
# ---------------------------------------------------------------------------
def normalise_normal_inline_copy(
    body: str,
) -> str:
    replacements = [
        (
            r"(?i)\bi attached 4 quick screenshots\b",
            "I included 4 quick screenshots below",
        ),
        (
            r"(?i)\bi attached the 4 screenshots\b",
            "I included the 4 screenshots below",
        ),
        (
            r"(?i)\b4 attached screenshots\b",
            "4 screenshots below",
        ),
        (
            r"(?i)\bthe attached screenshots\b",
            "the screenshots below",
        ),
        (
            r"(?i)\battached screenshots\b",
            "screenshots below",
        ),
        (
            r"(?i)\battached screenshots showing\b",
            "screenshots below showing",
        ),
        (
            r"(?i)\bthe four attached screenshots\b",
            "the four screenshots below",
        ),
    ]

    result = body

    for pattern, replacement in replacements:
        result = re.sub(
            pattern,
            replacement,
            result,
        )

    return result


def _safe_subject(
    subject: str,
    business_name: str,
) -> str:
    subject = " ".join(
        subject.replace("!", "").split()
    ).strip()

    if not subject:
        return f"A quick look at {business_name}"

    if len(subject.split()) > 8:
        subject = " ".join(
            subject.split()[:8]
        ).rstrip(" ,.-")

    return subject


async def draft_dogfood_pitch(
    business_name: str,
    research_profile: str,
    contact_name: str = "",
    contact_title: str = "",
) -> tuple[str, str]:
    prompt = (
        f"Business name: {business_name}\n"
        f"Contact name: {contact_name or 'Unknown'}\n"
        f"Contact title: {contact_title or 'Unknown'}\n\n"
        f"Public research:\n{research_profile}"
    )

    response = await dogfood_agent.invoke_async(prompt)

    response_text = str(response).strip()

    subject = f"A simpler way to find clients for {business_name}"
    hook = (
        f"I came across {business_name} and noticed you work in the "
        "automation space, so I thought Scout might be relevant to how "
        "you find and pitch new clients."
    )

    if "SUBJECT:" in response_text and "HOOK:" in response_text:
        try:
            subject_part, hook_part = response_text.split(
                "HOOK:",
                1,
            )

            subject_part = subject_part.replace(
                "SUBJECT:",
                "",
            ).strip()

            hook_part = hook_part.strip()

            if subject_part:
                subject = subject_part

            if hook_part:
                hook = hook_part
        except Exception:
            pass

    subject = _safe_subject(
        subject,
        business_name,
    )

    fixed_body = (
        f"Hi {contact_name.strip() if contact_name.strip() else 'there'},\n\n"
        f"{hook.strip()}\n\n"
        f"{DOGFOOD_FIXED_PITCH}\n\n"
        f"{DOGFOOD_CTA}"
    )

    if SCOUT_DEMO_VIDEO_URL:
        fixed_body += (
            "\n\n"
            "I also put together a 3-minute video of Scout below."
            f"\n{SCOUT_DEMO_VIDEO_URL}"
        )

    return subject, fixed_body


# ---------------------------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    niche: str
    location: str
    scale: str = "small"
    count: int = 1
    campaign_type: Literal["normal", "dogfood"] = "normal"


class RegenerateRequest(BaseModel):
    business_name: str
    research_profile: str
    campaign_type: Literal["normal", "dogfood"] = "normal"
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None


class SaveMailboxSettingsRequest(BaseModel):
    gmail_address: str
    gmail_app_password: str


class SendOutreachRequest(BaseModel):
    niche: str
    location: str
    scale: str
    campaign_type: Literal["normal", "dogfood"] = "normal"
    recipient_email: str
    subject: str
    body: str
    business_name: str
    form_screenshot: Optional[str] = None
    airtable_screenshot: Optional[str] = None
    email_screenshot: Optional[str] = None
    slack_screenshot: Optional[str] = None


# ---------------------------------------------------------------------------
# DOGFOOD ASSETS
# ---------------------------------------------------------------------------
def validate_dogfood_assets() -> None:
    missing = missing_dogfood_assets()

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Dogfood assets are missing. Add these files under "
                "campaign_assets/dogfood/: "
                + ", ".join(missing)
            ),
        )


def get_dogfood_result() -> dict:
    validate_dogfood_assets()
    return dogfood_demo_result()


# ---------------------------------------------------------------------------
# ROOT / ACCESS
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "Scout API is running!",
    }


@app.get("/api/founder-access")
async def founder_access(
    user_id: str = Depends(get_verified_user_id),
):
    return {
        "status": "success",
        "allowed": bool(
            FOUNDER_USER_ID
            and user_id == FOUNDER_USER_ID
        ),
    }


# ---------------------------------------------------------------------------
# MAIN SCOUT PIPELINE
# ---------------------------------------------------------------------------
@app.post("/api/start-agent")
async def start_agent_pipeline(
    request: ResearchRequest,
    user_id: str = Depends(get_verified_user_id),
):
    try:
        enforce_daily_email_limit(user_id)

        if request.campaign_type == CAMPAIGN_DOGFOOD:
            require_founder(user_id)
            validate_dogfood_assets()

        campaign_type = request.campaign_type

        effective_niche = (
            DOGFOOD_CAMPAIGN_NICHE
            if campaign_type == CAMPAIGN_DOGFOOD
            else request.niche.strip()
        )

        if not effective_niche:
            raise HTTPException(
                status_code=400,
                detail="Enter a niche before running Scout.",
            )

        if not request.location.strip():
            raise HTTPException(
                status_code=400,
                detail="Enter a location before running Scout.",
            )

        print(
            f"\n--- API Request Received: "
            f"User='{user_id}', "
            f"Campaign='{campaign_type}', "
            f"Niche='{effective_niche}', "
            f"Location='{request.location}', "
            f"Scale='{request.scale}', "
            f"Count={request.count} ---"
        )

        excluded_businesses: List[str] = []

        if supabase:
            history_res = (
                supabase
                .table("outreach_history")
                .select("business_name")
                .eq("user_name", user_id)
                .execute()
            )

            if history_res.data:
                excluded_businesses = [
                    item["business_name"]
                    for item in history_res.data
                ]

        businesses = await find_businesses(
            effective_niche,
            request.location,
            request.scale,
            excluded_businesses,
        )

        if not businesses:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No new businesses found matching these criteria "
                    "(all potential matches were previously contacted by you)."
                ),
            )

        run_count = min(
            max(request.count, 1),
            len(businesses),
        )

        batch_results: List[dict] = []
        available_pool = list(businesses)

        for i in range(run_count):
            if not available_pool:
                break

            target_business = random.choice(
                available_pool
            )

            available_pool.remove(
                target_business
            )

            print(
                f"[{i + 1}/{run_count}] "
                f"Target business selected: "
                f"{target_business}"
            )

            research_result = await research_business(
                target_business,
                request.location,
            )

            profile = research_result["research_profile"]

            if campaign_type == CAMPAIGN_DOGFOOD:
                demo_result = get_dogfood_result()

                subject, body = await draft_dogfood_pitch(
                    target_business,
                    profile,
                    research_result.get(
                        "contact_name"
                    ) or "",
                    research_result.get(
                        "contact_title"
                    ) or "",
                )

                print(
                    f"Drafting Dogfood Scout pitch "
                    f"for {target_business}..."
                )

            else:
                demo_result = await build_real_demo(
                    target_business,
                    profile,
                )

                subject, body = await draft_outreach_pitch(
                    target_business,
                    profile,
                )

                body = normalise_normal_inline_copy(
                    body
                )

            batch_results.append({
                "business_name": target_business,
                "campaign_type": campaign_type,
                "research_profile": profile,
                "business_type": research_result.get(
                    "business_type"
                ),
                "business_facts": research_result.get(
                    "business_facts"
                ),
                "estimated_scale": research_result.get(
                    "estimated_scale"
                ),
                "website": research_result.get(
                    "website"
                ),
                "domain": research_result.get(
                    "domain"
                ),
                "automation_opportunity": research_result.get(
                    "automation_opportunity"
                ),
                "website_email": research_result.get(
                    "website_email"
                ),
                "contact_name": research_result.get(
                    "contact_name"
                ),
                "contact_title": research_result.get(
                    "contact_title"
                ),
                "contact_email": research_result.get(
                    "contact_email"
                ),
                "contact_seniority": research_result.get(
                    "contact_seniority"
                ),
                "contact_department": research_result.get(
                    "contact_department"
                ),
                "contact_confidence": research_result.get(
                    "contact_confidence"
                ),
                "contact_verification_status": research_result.get(
                    "contact_verification_status"
                ),
                "contact_source": research_result.get(
                    "contact_source"
                ),
                "recipient_email": research_result.get(
                    "recipient_email"
                ),
                "demo_result": demo_result,
                "draft_subject": subject,
                "draft_body": body,
            })

        return {
            "status": "success",
            "data": batch_results,
        }

    except HTTPException:
        raise

    except Exception as exc:
        print("ERROR IN PIPELINE:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# MAILBOX SETTINGS
# ---------------------------------------------------------------------------
@app.post("/api/settings/mailbox")
async def save_mailbox_settings(
    request: SaveMailboxSettingsRequest,
    user_id: str = Depends(get_verified_user_id),
):
    try:
        verify_mailbox_credentials(
            request.gmail_address,
            request.gmail_app_password,
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=(
                "Couldn't sign in with that Gmail address + App Password. "
                "Double-check the App Password (not your regular Gmail password) "
                "and that 2-Step Verification is on."
            ),
        )

    if not supabase:
        raise HTTPException(
            status_code=500,
            detail="Supabase isn't configured on the server.",
        )

    supabase.table(
        USER_SETTINGS_TABLE
    ).upsert(
        {
            "user_name": user_id,
            "gmail_address": request.gmail_address,
            "gmail_app_password": request.gmail_app_password,
        },
        on_conflict="user_name",
    ).execute()

    return {
        "status": "success",
        "message": (
            f"Mailbox {request.gmail_address} connected."
        ),
    }


@app.get("/api/settings/mailbox")
async def get_mailbox_settings(
    user_id: str = Depends(get_verified_user_id),
):
    if not supabase:
        return {
            "status": "success",
            "connected": False,
        }

    res = (
        supabase
        .table(USER_SETTINGS_TABLE)
        .select("gmail_address")
        .eq("user_name", user_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return {
            "status": "success",
            "connected": False,
        }

    return {
        "status": "success",
        "connected": True,
        "gmail_address": res.data[0]["gmail_address"],
    }


# ---------------------------------------------------------------------------
# OUTREACH REGENERATION
# ---------------------------------------------------------------------------
@app.post("/api/regenerate-outreach")
async def regenerate_outreach(
    request: RegenerateRequest,
    authorization: Optional[str] = Header(None),
):
    try:
        if request.campaign_type == CAMPAIGN_DOGFOOD:
            user_id = get_verified_user_id(authorization)
            require_founder(user_id)

            validate_dogfood_assets()

            subject, body = await draft_dogfood_pitch(
                request.business_name,
                request.research_profile,
                request.contact_name or "",
                request.contact_title or "",
            )

        else:
            subject, body = await draft_outreach_pitch(
                request.business_name,
                request.research_profile,
            )

            body = normalise_normal_inline_copy(
                body
            )

        return {
            "status": "success",
            "draft_subject": subject,
            "draft_body": body,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# SEND OUTREACH
# ---------------------------------------------------------------------------
def build_normal_inline_specs(
    request: SendOutreachRequest,
) -> List[Dict[str, Any]]:
    specs = [
        {
            "path": request.form_screenshot,
            "cid": "scout-normal-form",
            "alt": "Tally contact form demo",
            "caption": "1. Customer intake form",
        },
        {
            "path": request.airtable_screenshot,
            "cid": "scout-normal-airtable",
            "alt": "Airtable CRM demo",
            "caption": "2. Lead logged into the CRM",
        },
        {
            "path": request.email_screenshot,
            "cid": "scout-normal-email",
            "alt": "Automatic email reply demo",
            "caption": "3. Automatic customer reply",
        },
    ]

    if request.slack_screenshot:
        specs.append(
            {
                "path": request.slack_screenshot,
                "cid": "scout-normal-slack",
                "alt": "Slack lead notification demo",
                "caption": "4. Team notification",
            }
        )

    return specs


def build_history_payload(
    user_id: str,
    request: SendOutreachRequest,
    screenshot_urls: Dict[str, Optional[str]],
) -> dict:
    return {
        "user_name": user_id,
        "business_name": request.business_name,
        "niche": (
            DOGFOOD_CAMPAIGN_NICHE
            if request.campaign_type == CAMPAIGN_DOGFOOD
            else request.niche
        ),
        "location": request.location,
        "scale": request.scale,
        "campaign_type": request.campaign_type,
        "recipient_email": request.recipient_email,
        "subject": request.subject,
        "body": request.body,
        "form_screenshot": screenshot_urls.get(
            "form_screenshot"
        ),
        "airtable_screenshot": screenshot_urls.get(
            "airtable_screenshot"
        ),
        "email_screenshot": screenshot_urls.get(
            "email_screenshot"
        ),
        "slack_screenshot": screenshot_urls.get(
            "slack_screenshot"
        ),
    }


@app.post("/api/send-outreach")
async def send_outreach(
    request: SendOutreachRequest,
    user_id: str = Depends(get_verified_user_id),
):
    try:
        enforce_daily_email_limit(user_id)
        enforce_send_gap(user_id)

        if request.campaign_type == CAMPAIGN_DOGFOOD:
            require_founder(user_id)
            validate_dogfood_assets()

            dogfood_paths = dogfood_asset_paths()

            inline_specs = dogfood_inline_specs(
                SCOUT_DEMO_VIDEO_URL
            )

            attachment_history_paths = {
                "form_screenshot": dogfood_paths[
                    "form_screenshot"
                ],
                "airtable_screenshot": dogfood_paths[
                    "airtable_screenshot"
                ],
                "email_screenshot": dogfood_paths[
                    "email_screenshot"
                ],
                "slack_screenshot": dogfood_paths[
                    "slack_screenshot"
                ],
            }

        else:
            inline_specs = build_normal_inline_specs(
                request
            )

            for spec in inline_specs:
                if not spec["path"]:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Normal outreach is missing one of its "
                            "generated proof screenshots."
                        ),
                    )

            attachment_history_paths = {
                "form_screenshot": request.form_screenshot,
                "airtable_screenshot": request.airtable_screenshot,
                "email_screenshot": request.email_screenshot,
                "slack_screenshot": request.slack_screenshot,
            }

        sender_email, app_password = get_mailbox_credentials(
            user_id
        )

        print(
            f"Sending {request.campaign_type} outreach for "
            f"'{request.business_name}' to "
            f"'{request.recipient_email}' via "
            f"{sender_email}'s mailbox."
        )

        status = send_email_smtp(
            to_email=request.recipient_email,
            subject=request.subject,
            body=request.body,
            sender_email=sender_email,
            app_password=app_password,
            inline_images=inline_specs,
        )

        try:
            schedule_next_send_window(user_id)
        except Exception as schedule_exc:
            # The email has already been sent successfully at this point.
            # A failure here is just cooldown bookkeeping — never let it
            # surface as a "send failed" error to the user.
            print(
                "WARNING: Could not update next_send_allowed_at "
                f"for user {user_id}."
            )
            print(schedule_exc)

        if supabase:
            uploaded = {
                key: upload_screenshot_to_storage(path)
                for key, path in attachment_history_paths.items()
            }

            history_payload = build_history_payload(
                user_id,
                request,
                uploaded,
            )

            # New schema includes campaign_type. For a safe deployment,
            # retry once without that new column if the migration hasn't
            # been applied yet. The email has already been sent, so history
            # failure should never turn a successful send into a false error.
            try:
                supabase.table(
                    "outreach_history"
                ).insert(
                    history_payload
                ).execute()

            except Exception as history_exc:
                print(
                    "WARNING: Could not save campaign_type to "
                    "outreach_history. Retrying legacy history insert."
                )
                print(history_exc)

                legacy_payload = dict(
                    history_payload
                )
                legacy_payload.pop(
                    "campaign_type",
                    None
                )

                try:
                    supabase.table(
                        "outreach_history"
                    ).insert(
                        legacy_payload
                    ).execute()

                except Exception:
                    print(
                        "WARNING: Legacy history insert also failed."
                    )
                    traceback.print_exc()

        return {
            "status": "success",
            "message": status,
        }

    except HTTPException:
        raise

    except Exception as exc:
        print("ERROR SENDING OUTREACH:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------
@app.get("/api/history")
async def get_history(
    user_id: str = Depends(get_verified_user_id),
):
    try:
        if not supabase:
            return {
                "status": "success",
                "data": [],
            }

        response = (
            supabase
            .table("outreach_history")
            .select("*")
            .eq("user_name", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        return {
            "status": "success",
            "data": response.data,
        }

    except Exception as exc:
        print("ERROR FETCHING HISTORY:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# STATIC FRONTEND
# ---------------------------------------------------------------------------
if os.path.exists("static"):
    app.mount(
        "/assets",
        StaticFiles(directory="static/assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if (
            full_path.startswith("api/")
            or full_path.startswith("screenshots/")
            or full_path.startswith("campaign-assets/")
        ):
            raise HTTPException(
                status_code=404,
                detail="Not found",
            )

        return FileResponse(
            "static/index.html"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )