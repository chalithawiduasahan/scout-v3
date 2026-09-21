import os
import re
import requests
from typing import Any, Dict, Optional
from urllib.parse import urlparse


HUNTER_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"


# These roles are given an additional ranking boost after Hunter returns
# actual personal contacts. We deliberately do NOT use these as API filters,
# because filtering too aggressively at the Hunter level can produce zero
# results even when useful personal contacts exist for the domain.
HIGH_LEVEL_ROLE_KEYWORDS = [
    "founder",
    "co-founder",
    "owner",
    "chief executive",
    "ceo",
    "managing director",
    "executive director",
    "director",
    "partner",
    "principal",
    "general manager",
    "head of",
    "operations manager",
    "marketing manager",
    "sales manager",
    "business development",
]


SENIORITY_SCORE = {
    "executive": 300,
    "senior": 200,
    "junior": 50,
}


def _normalize_domain(value: Optional[str]) -> str:
    """
    Normalize a website/domain into a bare domain.

    Examples:
        example.com
        www.example.com
        https://www.example.com/about
        -> example.com
    """
    if not value:
        return ""

    value = value.strip().lower()
    value = value.strip(" <>\"'")

    if value.lower() == "not found":
        return ""

    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urlparse(value)
        domain = parsed.netloc or parsed.path.split("/")[0]
    except Exception:
        domain = value

    domain = domain.split("@")[-1]
    domain = domain.split(":")[0]
    domain = domain.removeprefix("www.")

    return domain.strip().rstrip("/")


def _valid_email(value: Optional[str]) -> bool:
    if not value:
        return False

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            value.strip(),
        )
    )


def _position_score(position: Optional[str]) -> int:
    """
    Rank roles that are generally more useful for automation outreach.

    This is deliberately a local ranking step rather than a Hunter API filter.
    """
    if not position:
        return 0

    position_lower = position.lower()

    for keyword in HIGH_LEVEL_ROLE_KEYWORDS:
        if keyword in position_lower:
            return 150

    return 0


def _candidate_score(candidate: Dict[str, Any]) -> int:
    """
    Rank a personal Hunter contact.

    We use every useful signal Hunter gives us:
      - decision maker
      - seniority
      - position
      - verification
      - confidence
      - presence of an actual name
    """
    score = 0

    # Strongest signal.
    if candidate.get("decision_maker") is True:
        score += 1000

    # Hunter's seniority taxonomy.
    seniority = str(
        candidate.get("seniority") or ""
    ).lower()

    score += SENIORITY_SCORE.get(
        seniority,
        0,
    )

    # Role/title relevance.
    score += _position_score(
        candidate.get("position")
        or candidate.get("position_raw")
    )

    # Verification.
    verification = (
        candidate.get("verification")
        or {}
    )

    verification_status = str(
        verification.get("status") or ""
    ).lower()

    if verification_status == "valid":
        score += 100

    elif verification_status == "accept_all":
        score += 40

    # Hunter's confidence score.
    confidence = candidate.get("confidence")

    try:
        score += int(
            confidence or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        pass

    # Prefer contacts where Hunter knows the person's identity.
    first_name = candidate.get("first_name")
    last_name = candidate.get("last_name")
    full_name = candidate.get("full_name")

    if (
        first_name
        or last_name
        or full_name
    ):
        score += 20

    # Prefer a real title.
    if (
        candidate.get("position")
        or candidate.get("position_raw")
    ):
        score += 20

    return score


def find_best_contact(
    business_name: str,
    domain: str,
    automation_opportunity: str = "",
) -> Dict[str, Any]:
    """
    Find the best personal contact for a business using Hunter Domain Search.

    IMPORTANT FALLBACK RULE:
    This function NEVER returns a generic Hunter email.

    If Hunter finds no suitable personal contact, this function returns {}.
    The caller then falls back to the exact website email discovered by
    Linkup.

    Hunter is intentionally queried broadly for personal contacts and Scout
    performs the seniority/decision-maker ranking locally. This prevents the
    overly restrictive combination of type=personal + decision_maker=true
    from returning zero results unnecessarily.
    """

    api_key = os.getenv(
        "HUNTER_API_KEY"
    )

    if not api_key:
        print(
            "Hunter enrichment skipped: "
            "HUNTER_API_KEY is not configured."
        )
        return {}

    normalized_domain = _normalize_domain(
        domain
    )

    if not normalized_domain:
        print(
            f"Hunter enrichment skipped for "
            f"'{business_name}': no usable domain was found."
        )
        return {}

    # -----------------------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT use decision_maker=true here.
    #
    # Hunter can have personal emails for a domain whose decision-maker
    # classification is missing or false. We want those people returned so
    # Scout can inspect their position/seniority/decision-maker fields itself.
    #
    # Hunter's current free-plan behavior also means a query with zero
    # results does not consume a search credit. That is expected.
    # -----------------------------------------------------------------------
    params = {
        "domain": normalized_domain,
        "type": "personal",
        "limit": 10,
        "api_key": api_key,
    }

    headers = {
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            HUNTER_DOMAIN_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=15,
        )

    except requests.RequestException as exc:
        print(
            f"Hunter API request failed for "
            f"'{business_name}' ({normalized_domain}): {exc}"
        )
        return {}

    # -----------------------------------------------------------------------
    # Explicitly report Hunter API errors so Render logs tell us exactly what
    # went wrong instead of silently looking like a normal fallback.
    # -----------------------------------------------------------------------
    if response.status_code != 200:
        print(
            f"Hunter API returned HTTP "
            f"{response.status_code} for "
            f"'{business_name}' ({normalized_domain})."
        )

        print(
            f"Hunter response: "
            f"{response.text[:1000]}"
        )

        return {}

    try:
        payload = response.json()

    except ValueError:
        print(
            f"Hunter API returned invalid JSON for "
            f"'{business_name}' ({normalized_domain})."
        )

        print(
            f"Hunter raw response: "
            f"{response.text[:1000]}"
        )

        return {}

    # -----------------------------------------------------------------------
    # Hunter success response
    # -----------------------------------------------------------------------
    data = (
        payload.get("data")
        or {}
    )

    meta = (
        payload.get("meta")
        or {}
    )

    emails = (
        data.get("emails")
        or []
    )

    print(
        f"Hunter Domain Search completed for "
        f"'{business_name}' ({normalized_domain}). "
        f"Hunter returned {len(emails)} personal email record(s). "
        f"meta.results={meta.get('results')}"
    )

    if not isinstance(
        emails,
        list,
    ):
        print(
            "Hunter returned an unexpected "
            "emails payload."
        )
        return {}

    # -----------------------------------------------------------------------
    # Local candidate filtering
    # -----------------------------------------------------------------------
    candidates = []

    for email_record in emails:

        if not isinstance(
            email_record,
            dict,
        ):
            continue

        email_value = str(
            email_record.get("value")
            or ""
        ).strip()

        if not _valid_email(
            email_value
        ):
            continue

        # We asked Hunter for personal emails, but keep this defensive check
        # so Scout never accidentally chooses a generic address.
        email_type = str(
            email_record.get("type")
            or ""
        ).lower()

        if email_type != "personal":
            continue

        verification = (
            email_record.get("verification")
            or {}
        )

        verification_status = str(
            verification.get("status")
            or ""
        ).lower()

        # Never select an explicitly invalid Hunter email.
        if verification_status == "invalid":
            continue

        candidate = dict(
            email_record
        )

        candidate["_score"] = (
            _candidate_score(
                candidate
            )
        )

        candidates.append(
            candidate
        )

    if not candidates:
        print(
            f"Hunter returned no usable personal "
            f"contact for '{business_name}' "
            f"({normalized_domain}). "
            f"Scout will use the Linkup website email "
            f"as the fallback, if one exists."
        )
        return {}

    # Highest score wins.
    best = max(
        candidates,
        key=lambda item: item["_score"],
    )

    # -----------------------------------------------------------------------
    # Contact name
    # -----------------------------------------------------------------------
    first_name = str(
        best.get("first_name")
        or ""
    ).strip()

    last_name = str(
        best.get("last_name")
        or ""
    ).strip()

    contact_name = str(
        best.get("full_name")
        or ""
    ).strip()

    if not contact_name:
        contact_name = " ".join(
            part
            for part in [
                first_name,
                last_name,
            ]
            if part
        ).strip()

    # -----------------------------------------------------------------------
    # Contact title
    # -----------------------------------------------------------------------
    contact_title = str(
        best.get("position")
        or best.get("position_raw")
        or ""
    ).strip()

    # -----------------------------------------------------------------------
    # Verification metadata
    # -----------------------------------------------------------------------
    verification = (
        best.get("verification")
        or {}
    )

    verification_status = (
        str(
            verification.get("status")
            or ""
        ).strip()
        or None
    )

    selected_email = str(
        best.get("value")
        or ""
    ).strip()

    print(
        f"Hunter selected personal contact for "
        f"'{business_name}': "
        f"{contact_name or 'Unknown person'} "
        f"<{selected_email}> "
        f"| title={contact_title or 'Unknown'} "
        f"| seniority={best.get('seniority') or 'Unknown'} "
        f"| decision_maker={best.get('decision_maker')} "
        f"| confidence={best.get('confidence')}"
    )

    return {
        "contact_email": selected_email,
        "contact_name": (
            contact_name
            or None
        ),
        "contact_title": (
            contact_title
            or None
        ),
        "contact_seniority": (
            str(
                best.get("seniority")
            ).strip()
            if best.get(
                "seniority"
            ) is not None
            else None
        ),
        "contact_department": (
            str(
                best.get("department")
            ).strip()
            if best.get(
                "department"
            ) is not None
            else None
        ),
        "contact_confidence": (
            best.get(
                "confidence"
            )
        ),
        "contact_verification_status": verification_status,
        "contact_source": "Hunter",
    }