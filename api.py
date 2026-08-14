from fastapi import FastAPI, Query, HTTPException
from search_phone import PhoneOSINT

import concurrent.futures
import os
import re
import requests

from typing import Any, Dict, List, Optional


app = FastAPI(
    title="SearchPhone API",
    version="3.0.0"
)


# =========================================================
# ENVIRONMENT KEYS
# =========================================================

IPQS_KEY = os.getenv("IPQS_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


# =========================================================
# HOME / HEALTH CHECK
# =========================================================

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "SearchPhone API v3 is running"
    }


# =========================================================
# PHONE NUMBER FORMATS
# =========================================================

def unique_add(items: List[str], value: Optional[str]) -> None:
    if value and value not in items:
        items.append(value)


def phone_variants(phone: str, region: str = "AE") -> List[str]:

    digits = re.sub(r"\D", "", phone)

    variants: List[str] = []

    unique_add(variants, phone.strip())

    if digits:
        unique_add(variants, digits)
        unique_add(variants, f"+{digits}")

    # UAE formats
    if region.upper() == "AE":

        # Example:
        # +971551234567 -> 0551234567
        if digits.startswith("971") and len(digits) >= 11:

            national_digits = digits[3:]

            local = "0" + national_digits

            unique_add(
                variants,
                local
            )

            # Example:
            # 055 123 4567
            if len(local) == 10:

                unique_add(
                    variants,
                    f"{local[:3]} {local[3:6]} {local[6:]}"
                )

            # Example:
            # +971 55 123 4567
            if len(national_digits) == 9:

                unique_add(
                    variants,
                    f"+971 {national_digits[:2]} "
                    f"{national_digits[2:5]} "
                    f"{national_digits[5:]}"
                )

        # Convert local UAE number to international
        elif digits.startswith("0") and len(digits) == 10:

            international_digits = "971" + digits[1:]

            unique_add(
                variants,
                f"+{international_digits}"
            )

            unique_add(
                variants,
                international_digits
            )

            unique_add(
                variants,
                f"+971 {digits[1:3]} "
                f"{digits[3:6]} "
                f"{digits[6:]}"
            )

    return variants


def choose_e164_like(
    variants: List[str],
    original: str
) -> str:

    for item in variants:

        if item.startswith("+") and " " not in item:

            return item

    return original


def choose_local_plain(
    variants: List[str]
) -> Optional[str]:

    for item in variants:

        if (
            item.startswith("0")
            and " " not in item
            and item.isdigit()
        ):

            return item

    return None


# =========================================================
# IPQUALITYSCORE
# =========================================================

def check_ipqs(
    phone: str,
    region: str
) -> Dict[str, Any]:

    if not IPQS_KEY:

        return {
            "success": False,
            "message": "IPQS_KEY is not configured"
        }

    try:

        clean_phone = re.sub(
            r"[^\d+]",
            "",
            phone
        )

        response = requests.get(

            "https://ipqualityscore.com/api/json/phone",

            headers={
                "IPQS-KEY": IPQS_KEY
            },

            params={
                "phone": clean_phone,
                "strictness": 1,
                "country[]": region.upper()
            },

            timeout=20
        )

        try:

            data = response.json()

        except Exception:

            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:500]
            }

        if response.status_code != 200:

            return {
                "success": False,
                "status_code": response.status_code,
                "response": data
            }

        return data

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# =========================================================
# SIMPLIFY IPQS IDENTITY DATA
# =========================================================

def simplify_ipqs(
    data: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(data, dict):

        return {}

    name = data.get("name")

    if name in (
        None,
        "",
        "N/A"
    ):

        name = None

    emails: List[Any] = []

    email_data = data.get(
        "associated_email_addresses"
    )

    if isinstance(email_data, dict):

        possible_emails = email_data.get(
            "emails",
            []
        )

        if isinstance(
            possible_emails,
            list
        ):

            emails = possible_emails

    return {

        # Identity
        "name": name,

        "associated_emails": emails,

        # Higher IPQS plans may return this
        "identity_data": data.get(
            "identity_data"
        ),

        # Phone information
        "valid": data.get("valid"),

        "active": data.get("active"),

        "active_status": data.get(
            "active_status"
        ),

        "formatted": data.get(
            "formatted"
        ),

        "local_format": data.get(
            "local_format"
        ),

        "carrier": data.get(
            "carrier"
        ),

        "line_type": data.get(
            "line_type"
        ),

        "country": data.get(
            "country"
        ),

        "region": data.get(
            "region"
        ),

        "city": data.get(
            "city"
        ),

        "timezone": data.get(
            "timezone"
        ),

        # Risk information
        "fraud_score": data.get(
            "fraud_score"
        ),

        "recent_abuse": data.get(
            "recent_abuse"
        ),

        "risky": data.get(
            "risky"
        ),

        "spammer": data.get(
            "spammer"
        ),

        "leaked": data.get(
            "leaked"
        ),

        "VOIP": data.get(
            "VOIP"
        ),

        "prepaid": data.get(
            "prepaid"
        ),

        "user_activity": data.get(
            "user_activity"
        )
    }


# =========================================================
# SERPAPI BASE REQUEST
# =========================================================

def serpapi_request(
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not SERPAPI_KEY:

        return {
            "success": False,
            "message": "SERPAPI_KEY is not configured"
        }

    full_params = dict(params)

    full_params["api_key"] = SERPAPI_KEY

    try:

        response = requests.get(

            "https://serpapi.com/search",

            params=full_params,

            timeout=25
        )

        try:

            data = response.json()

        except Exception:

            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:500]
            }

        if response.status_code != 200:

            return {
                "success": False,
                "status_code": response.status_code,
                "response": data
            }

        return data

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# =========================================================
# STRONGER GOOGLE SEARCH
# =========================================================

def search_google_enriched(
    e164: str,
    local: Optional[str],
    region: str
) -> List[Dict[str, Any]]:

    numbers = [
        f'"{e164}"'
    ]

    if local:

        numbers.append(
            f'"{local}"'
        )

    number_query = " OR ".join(
        numbers
    )

    # Look for public contact/profile/business pages
    query = (

        f"({number_query}) "

        f"(contact OR caller OR phone OR mobile "
        f"OR WhatsApp OR business "

        f"OR site:facebook.com "
        f"OR site:instagram.com "
        f"OR site:linkedin.com "
        f"OR site:x.com "
        f"OR site:tiktok.com)"
    )

    data = serpapi_request({

        "engine": "google",

        "q": query,

        "hl": "en",

        "gl": region.lower(),

        "num": 20
    })

    results: List[Dict[str, Any]] = []

    if not isinstance(data, dict):

        return results

    for item in data.get(
        "organic_results",
        []
    ):

        results.append({

            "title": item.get(
                "title",
                ""
            ),

            "link": item.get(
                "link",
                ""
            ),

            "snippet": item.get(
                "snippet",
                ""
            ),

            "source": item.get(
                "source",
                ""
            )
        })

    return results


# =========================================================
# GOOGLE MAPS / BUSINESS LOOKUP
# =========================================================

def search_google_maps(
    e164: str,
    local: Optional[str]
) -> List[Dict[str, Any]]:

    query = local or e164

    data = serpapi_request({

        "engine": "google_maps",

        "type": "search",

        "q": query,

        "hl": "en"
    })

    results: List[Dict[str, Any]] = []

    if not isinstance(data, dict):

        return results

    for item in data.get(
        "local_results",
        []
    ):

        results.append({

            "title": item.get(
                "title",
                ""
            ),

            "type": item.get(
                "type",
                ""
            ),

            "address": item.get(
                "address",
                ""
            ),

            "phone": item.get(
                "phone",
                ""
            ),

            "website": item.get(
                "website",
                ""
            ),

            "description": item.get(
                "description",
                ""
            ),

            "rating": item.get(
                "rating"
            ),

            "reviews": item.get(
                "reviews"
            ),

            "gps_coordinates": item.get(
                "gps_coordinates"
            ),

            "data_id": item.get(
                "data_id"
            )
        })

    return results


# =========================================================
# SAFE FUNCTION CALL
# =========================================================

def safe_call(
    function,
    *args
):

    try:

        return function(
            *args
        )

    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
# MAIN SEARCH ENDPOINT
# =========================================================

@app.get("/search")
def search_phone(

    phone: str = Query(
        ...,
        description=(
            "Phone number, preferably with "
            "international country code"
        )
    ),

    region: str = Query(
        "AE",
        description=(
            "Two-letter country code, "
            "for example AE"
        )
    )
):

    try:

        region = region.upper()

        osint = PhoneOSINT()

        variants = phone_variants(
            phone,
            region
        )

        main_number = choose_e164_like(
            variants,
            phone
        )

        local_number = choose_local_plain(
            variants
        )


        # =================================================
        # RUN SOURCES TOGETHER
        # =================================================

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=10
        ) as executor:

            futures = {

                # IPQualityScore
                "ipqs": executor.submit(
                    check_ipqs,
                    main_number,
                    region
                ),

                # Numverify
                "numverify": executor.submit(
                    safe_call,
                    osint.check_numverify,
                    main_number,
                    region
                ),

                # Hudson Rock
                "hudson_rock": executor.submit(
                    safe_call,
                    osint.check_hudsonrock,
                    main_number
                ),

                # Original SearchPhone Google
                "google_exact": executor.submit(
                    safe_call,
                    osint.search_google,
                    main_number
                ),

                # Stronger Google search
                "google_enriched": executor.submit(
                    search_google_enriched,
                    main_number,
                    local_number,
                    region
                ),

                # Google Maps businesses
                "google_maps": executor.submit(
                    search_google_maps,
                    main_number,
                    local_number
                ),

                # GitHub
                "github_international": executor.submit(
                    safe_call,
                    osint.search_github,
                    main_number
                ),

                # Reddit
                "reddit_international": executor.submit(
                    safe_call,
                    osint.search_reddit,
                    main_number
                ),

                # DuckDuckGo
                "duckduckgo_international": executor.submit(
                    safe_call,
                    osint.search_duckduckgo,
                    main_number
                )
            }


            # =================================================
            # ALSO SEARCH UAE LOCAL FORMAT
            # =================================================

            if local_number:

                futures[
                    "github_local"
                ] = executor.submit(
                    safe_call,
                    osint.search_github,
                    local_number
                )

                futures[
                    "reddit_local"
                ] = executor.submit(
                    safe_call,
                    osint.search_reddit,
                    local_number
                )

                futures[
                    "duckduckgo_local"
                ] = executor.submit(
                    safe_call,
                    osint.search_duckduckgo,
                    local_number
                )


            collected: Dict[str, Any] = {}


            for name, future in futures.items():

                try:

                    collected[name] = (
                        future.result(
                            timeout=35
                        )
                    )

                except Exception as e:

                    collected[name] = {
                        "error": str(e)
                    }


        # =================================================
        # IPQS IDENTITY
        # =================================================

        ipqs_raw = collected.get(
            "ipqs",
            {}
        )

        identity = simplify_ipqs(

            ipqs_raw

            if isinstance(
                ipqs_raw,
                dict
            )

            else {}
        )


        # =================================================
        # BASIC PHONE INFO
        # =================================================

        phone_info = safe_call(

            osint.validate_phone,

            main_number,

            region
        )


        # =================================================
        # FINAL RESULT
        # =================================================

        return {

            "phone": phone,

            "region": region,

            "searched_variants": variants,


            # ---------------------------------------------
            # IMPORTANT IDENTITY SECTION
            # ---------------------------------------------

            "identity": identity,


            # ---------------------------------------------
            # PHONE DATABASES
            # ---------------------------------------------

            "phone_info": phone_info,

            "ipqs": ipqs_raw,

            "numverify": collected.get(
                "numverify"
            ),

            "hudson_rock": collected.get(
                "hudson_rock"
            ),


            # ---------------------------------------------
            # GOOGLE
            # ---------------------------------------------

            "google": {

                "exact": collected.get(
                    "google_exact",
                    []
                ),

                "enriched": collected.get(
                    "google_enriched",
                    []
                ),

                "maps_businesses": collected.get(
                    "google_maps",
                    []
                )
            },


            # ---------------------------------------------
            # GITHUB
            # ---------------------------------------------

            "github": {

                "international": collected.get(
                    "github_international",
                    []
                ),

                "local": collected.get(
                    "github_local",
                    []
                )
            },


            # ---------------------------------------------
            # REDDIT
            # ---------------------------------------------

            "reddit": {

                "international": collected.get(
                    "reddit_international",
                    []
                ),

                "local": collected.get(
                    "reddit_local",
                    []
                )
            },


            # ---------------------------------------------
            # DUCKDUCKGO
            # ---------------------------------------------

            "duckduckgo": {

                "international": collected.get(
                    "duckduckgo_international",
                    []
                ),

                "local": collected.get(
                    "duckduckgo_local",
                    []
                )
            },


            # ---------------------------------------------
            # API STATUS
            # ---------------------------------------------

            "source_status": {

                "ipqs_configured": bool(
                    IPQS_KEY
                ),

                "serpapi_configured": bool(
                    SERPAPI_KEY
                )
            }
        }


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
