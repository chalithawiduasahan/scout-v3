import os
import random
import uuid
import traceback

from fastapi import (
    FastAPI,
    HTTPException,
    Header,
    Depends,
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from typing import List, Optional

from supabase import create_client, Client

from agent import (
    find_businesses,
    research_business,
    build_real_demo,
    draft_outreach_pitch,
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

app.mount(
    "/screenshots",
    StaticFiles(directory="screenshots"),
    name="screenshots"
)


# Initialize Supabase Client securely on the backend
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Optional[Client] = (
    create_client(
        supabase_url,
        supabase_key
    )
    if supabase_url and supabase_key
    else None
)


SCREENSHOTS_BUCKET = "screenshots"


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
def get_verified_user_id(
    authorization: Optional[str] = Header(None)
) -> str:
    """FastAPI dependency: verifies the bearer token and returns the
    authenticated user's id, or raises HTTPException(401)."""

    if not supabase:
        raise HTTPException(
            status_code=500,
            detail="Supabase isn't configured on the server."
        )

    if (
        not authorization
        or not authorization.lower().startswith("bearer ")
    ):
        raise HTTPException(
            status_code=401,
            detail="Not signed in. Please log in and try again."
        )

    token = authorization.split(" ", 1)[1].strip()

    try:
        user_res = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please log in again."
        )

    if not user_res or not user_res.user:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please log in again."
        )

    return user_res.user.id


# ---------------------------------------------------------------------------
# MAILBOX SENDING
# ---------------------------------------------------------------------------
USER_SETTINGS_TABLE = "user_settings"


def get_mailbox_credentials(
    user_id: str
) -> tuple[str, str]:
    """Looks up a user's connected Gmail address + App Password."""

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
        .select(
            "gmail_address, gmail_app_password"
        )
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
    local_path: Optional[str]
) -> Optional[str]:
    """Uploads a local screenshot file to Supabase Storage."""

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

        storage_path = (
            f"{uuid.uuid4().hex}{file_ext}"
        )

        with open(local_path, "rb") as f:
            supabase.storage.from_(SCREENSHOTS_BUCKET).upload(
                path=storage_path,
                file=f,
                file_options={
                    "content-type": "image/png"
                }
            )

        public_url = (
            supabase
            .storage
            .from_(SCREENSHOTS_BUCKET)
            .get_public_url(storage_path)
        )

        return public_url

    except Exception:
        print(
            f"WARNING: Failed to upload {local_path} "
            "to Supabase Storage:"
        )
        traceback.print_exc()

        return local_path


# ---------------------------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    niche: str
    location: str
    scale: str = "small"
    count: int = 1


class RegenerateRequest(BaseModel):
    business_name: str
    research_profile: str


class SaveMailboxSettingsRequest(BaseModel):
    gmail_address: str
    gmail_app_password: str


class SendOutreachRequest(BaseModel):
    niche: str
    location: str
    scale: str
    recipient_email: str
    subject: str
    body: str
    business_name: str
    form_screenshot: str
    airtable_screenshot: str
    email_screenshot: str
    slack_screenshot: Optional[str] = None


@app.get("/")
async def root():
    return {
        "message": "Scout API is running!"
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
        print(
            f"\n--- API Request Received: "
            f"User='{user_id}', "
            f"Niche='{request.niche}', "
            f"Location='{request.location}', "
            f"Scale='{request.scale}', "
            f"Count={request.count} ---"
        )

        excluded_businesses = []

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

                print(
                    f"Excluding previously contacted businesses "
                    f"for {user_id}: {excluded_businesses}"
                )

        # ---------------------------------------------------------------
        # Stage 1: business discovery
        # ---------------------------------------------------------------
        print("Finding targeted businesses...")

        businesses = await find_businesses(
            request.niche,
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
            request.count,
            len(businesses)
        )

        batch_results = []
        available_pool = list(businesses)

        # ---------------------------------------------------------------
        # Stage 2 + 3 + 4
        # ---------------------------------------------------------------
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
                f"Target business selected (Random): "
                f"{target_business}"
            )

            print(
                f"Researching business profile for "
                f"{target_business}..."
            )

            research_result = await research_business(
                target_business,
                request.location,
            )

            # Preserve the existing plain-text research profile for all
            # downstream code that already expects it.
            profile = research_result["research_profile"]

            print(
                f"Resolved recipient for {target_business}: "
                f"{research_result.get('recipient_email') or 'Not found'}"
            )

            if research_result.get("contact_email"):
                print(
                    f"Hunter personal contact found: "
                    f"{research_result.get('contact_name') or 'Unnamed'} "
                    f"<{research_result.get('contact_email')}>"
                )
            elif research_result.get("website_email"):
                print(
                    f"Hunter did not find a suitable personal contact. "
                    f"Using Linkup website email: "
                    f"{research_result.get('website_email')}"
                )
            else:
                print(
                    "No recipient email was found by Linkup or Hunter."
                )

            print(
                f"Building live demo & capturing screenshots "
                f"for {target_business}..."
            )

            demo_result = await build_real_demo(
                target_business,
                profile,
            )

            print(
                f"Drafting high-converting outreach pitch "
                f"for {target_business}..."
            )

            subject, body = await draft_outreach_pitch(
                target_business,
                profile,
            )

            batch_results.append({
                "business_name": target_business,

                # Existing field retained for compatibility with the
                # dashboard, demo builder, and outreach generator.
                "research_profile": profile,

                # Structured business research.
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

                # Linkup website email and Hunter enrichment are kept
                # separate so the UI can show exactly where the final
                # recipient came from.
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

                # THIS is what the frontend should use for "Send to".
                # Hunter personal email wins; Linkup website email is
                # the direct fallback.
                "recipient_email": research_result.get(
                    "recipient_email"
                ),

                "demo_result": demo_result,
                "draft_subject": subject,
                "draft_body": body,
            })

        print(
            "--- Pipeline Batch Finished Successfully! ---"
        )

        return {
            "status": "success",
            "data": batch_results
        }

    except HTTPException:
        raise

    except Exception as e:
        print("ERROR IN PIPELINE:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
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
            detail="Supabase isn't configured on the server."
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
    user_id: str = Depends(get_verified_user_id)
):
    if not supabase:
        return {
            "status": "success",
            "connected": False
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
            "connected": False
        }

    return {
        "status": "success",
        "connected": True,
        "gmail_address": res.data[0]["gmail_address"]
    }


# ---------------------------------------------------------------------------
# OUTREACH REGENERATION
# ---------------------------------------------------------------------------
@app.post("/api/regenerate-outreach")
async def regenerate_outreach(
    request: RegenerateRequest
):
    try:
        print(
            f"Regenerating pitch for: "
            f"{request.business_name}..."
        )

        subject, body = await draft_outreach_pitch(
            request.business_name,
            request.research_profile,
        )

        return {
            "status": "success",
            "draft_subject": subject,
            "draft_body": body
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ---------------------------------------------------------------------------
# SEND OUTREACH
# ---------------------------------------------------------------------------
@app.post("/api/send-outreach")
async def send_outreach(
    request: SendOutreachRequest,
    user_id: str = Depends(get_verified_user_id),
):
    try:
        sender_email, app_password = get_mailbox_credentials(
            user_id
        )

        print(
            f"Sending outreach for "
            f"'{request.business_name}' to "
            f"'{request.recipient_email}' via "
            f"{sender_email}'s mailbox."
        )

        attachments = [
            request.form_screenshot,
            request.airtable_screenshot,
            request.email_screenshot,
        ]

        if request.slack_screenshot:
            attachments.append(
                request.slack_screenshot
            )

        status = send_email_smtp(
            to_email=request.recipient_email,
            subject=request.subject,
            body=request.body,
            sender_email=sender_email,
            app_password=app_password,
            attachment_paths=attachments,
        )

        if supabase:
            form_url = upload_screenshot_to_storage(
                request.form_screenshot
            )

            airtable_url = upload_screenshot_to_storage(
                request.airtable_screenshot
            )

            email_url = upload_screenshot_to_storage(
                request.email_screenshot
            )

            slack_url = (
                upload_screenshot_to_storage(
                    request.slack_screenshot
                )
                if request.slack_screenshot
                else None
            )

            supabase.table(
                "outreach_history"
            ).insert(
                {
                    "user_name": user_id,
                    "business_name": request.business_name,
                    "niche": request.niche,
                    "location": request.location,
                    "scale": request.scale,
                    "recipient_email": request.recipient_email,
                    "subject": request.subject,
                    "body": request.body,
                    "form_screenshot": form_url,
                    "airtable_screenshot": airtable_url,
                    "email_screenshot": email_url,
                    "slack_screenshot": slack_url,
                }
            ).execute()

        return {
            "status": "success",
            "message": status,
        }

    except Exception as e:
        print("ERROR SENDING OUTREACH:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------
@app.get("/api/history")
async def get_history(
    user_id: str = Depends(get_verified_user_id)
):
    try:
        if not supabase:
            return {
                "status": "success",
                "data": []
            }

        query = (
            supabase
            .table("outreach_history")
            .select("*")
            .eq("user_name", user_id)
            .order("created_at", desc=True)
        )

        response = query.execute()

        return {
            "status": "success",
            "data": response.data
        }

    except Exception as e:
        print("ERROR FETCHING HISTORY:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ---------------------------------------------------------------------------
# STATIC FRONTEND
# ---------------------------------------------------------------------------
if os.path.exists("static"):
    app.mount(
        "/assets",
        StaticFiles(directory="static/assets"),
        name="assets"
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if (
            full_path.startswith("api/")
            or full_path.startswith("screenshots/")
        ):
            raise HTTPException(
                status_code=404,
                detail="Not found"
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
        reload=True
    )