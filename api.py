from fastapi import FastAPI, Query, HTTPException
from search_phone import PhoneOSINT

import concurrent.futures
import os
import re
import requests
from urllib.parse import urlparse


app = FastAPI(
    title="SearchPhone API",
    version="4.0.0"
)


# =========================================================
# API KEYS
# =========================================================

IPQS_KEY = os.getenv("IPQS_KEY", "")
PDL_API_KEY = os.getenv("PDL_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "SearchPhone API v4 is running"
    }


# =========================================================
# HELPERS
# =========================================================

def safe_call(function, *args):
    try:
        return function(*args)
    except Exception as e:
        return {"error": str(e)}


def safe_string(value):
    return value if isinstance(value, str) and value.strip() else None


def phone_variants(phone: str, region: str = "AE"):
    digits = re.sub(r"\D", "", phone)

    variants = []

    def add(value):
        if value and value not in variants:
            variants.append(value)

    add(phone.strip())

    if digits:
        add(digits)
        add("+" + digits)

    # UAE local/international conversions
    if region.upper() == "AE":

        if digits.startswith("971") and len(digits) == 12:
            national = digits[3:]
            local = "0" + national

            add(local)
            add(f"{local[:3]} {local[3:6]} {local[6:]}")
            add(f"+971 {national[:2]} {national[2:5]} {national[5:]}")

        elif digits.startswith("0") and len(digits) == 10:
            international = "971" + digits[1:]

            add("+" + international)
            add(international)
            add(
                f"+971 {digits[1:3]} "
                f"{digits[3:6]} "
                f"{digits[6:]}"
            )

    return variants


def choose_e164(variants, original):
    for value in variants:
        if value.startswith("+") and " " not in value:
            return value

    return original


def choose_local(variants):
    for value in variants:
        if value.startswith("0") and value.isdigit():
            return value

    return None


# =========================================================
# IPQUALITYSCORE
# =========================================================

def check_ipqs(phone, region="AE"):
    if not IPQS_KEY:
        return {
            "success": False,
            "message": "IPQS_KEY is not configured"
        }

    try:
        response = requests.get(
            "https://ipqualityscore.com/api/json/phone",
            headers={
                "IPQS-KEY": IPQS_KEY
            },
            params={
                "phone": phone,
                "strictness": 1,
                "country[]": region.upper()
            },
            timeout=20
        )

        try:
            return response.json()
        except Exception:
            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:500]
            }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


def simplify_ipqs(data):
    if not isinstance(data, dict):
        return {}

    name = data.get("name")

    if name in ("N/A", "", None):
        name = None

    email_data = data.get("associated_email_addresses", {})

    emails = []

    if isinstance(email_data, dict):
        possible = email_data.get("emails", [])

        if isinstance(possible, list):
            emails = [
                x for x in possible
                if isinstance(x, str)
            ]

    return {
        "name": name,
        "associated_emails": emails,
        "valid": data.get("valid"),
        "active": data.get("active"),
        "carrier": data.get("carrier"),
        "line_type": data.get("line_type"),
        "country": data.get("country"),
        "region": data.get("region"),
        "city": data.get("city"),
        "timezone": data.get("timezone"),
        "fraud_score": data.get("fraud_score"),
        "recent_abuse": data.get("recent_abuse"),
        "risky": data.get("risky"),
        "spammer": data.get("spammer"),
        "leaked": data.get("leaked"),
        "VOIP": data.get("VOIP"),
        "prepaid": data.get("prepaid")
    }


# =========================================================
# PEOPLE DATA LABS
# =========================================================

def check_pdl(phone, region="AE"):
    if not PDL_API_KEY:
        return {
            "matched": False,
            "message": "PDL_API_KEY is not configured"
        }

    params = {
        "phone": phone,
        "min_likelihood": 6
    }

    # Extra country hint for UAE numbers
    if region.upper() == "AE":
        params["country"] = "United Arab Emirates"

    try:
        response = requests.get(
            "https://api.peopledatalabs.com/v5/person/enrich",
            headers={
                "X-Api-Key": PDL_API_KEY
            },
            params=params,
            timeout=25
        )

        if response.status_code == 404:
            return {
                "matched": False,
                "status_code": 404,
                "message": "No PDL profile matched this phone number"
            }

        try:
            data = response.json()
        except Exception:
            return {
                "matched": False,
                "status_code": response.status_code,
                "message": response.text[:500]
            }

        if response.status_code != 200:
            return {
                "matched": False,
                "status_code": response.status_code,
                "response": data
            }

        return {
            "matched": True,
            "status_code": 200,
            "likelihood": data.get("likelihood"),
            "data": data.get("data", {})
        }

    except Exception as e:
        return {
            "matched": False,
            "message": str(e)
        }


def simplify_pdl(result):
    if not isinstance(result, dict):
        return {
            "matched": False
        }

    if not result.get("matched"):
        return {
            "matched": False,
            "likelihood": None
        }

    data = result.get("data", {})

    if not isinstance(data, dict):
        data = {}

    # Free PDL accounts may return True/False instead of
    # contact values. Only expose actual strings.
    work_email = safe_string(data.get("work_email"))

    return {
        "matched": True,
        "likelihood": result.get("likelihood"),

        "full_name": safe_string(
            data.get("full_name")
        ),

        "first_name": safe_string(
            data.get("first_name")
        ),

        "last_name": safe_string(
            data.get("last_name")
        ),

        "work_email": work_email,

        "work_email_available": (
            bool(data.get("work_email"))
            if isinstance(data.get("work_email"), bool)
            else bool(work_email)
        ),

        "job_title": safe_string(
            data.get("job_title")
        ),

        "job_company_name": safe_string(
            data.get("job_company_name")
        ),

        "job_company_website": safe_string(
            data.get("job_company_website")
        ),

        "industry": safe_string(
            data.get("industry")
        ),

        "linkedin_url": safe_string(
            data.get("linkedin_url")
        ),

        "facebook_url": safe_string(
            data.get("facebook_url")
        ),

        "twitter_url": safe_string(
            data.get("twitter_url")
        ),

        "github_url": safe_string(
            data.get("github_url")
        ),

        "location_name": safe_string(
            data.get("location_name")
        )
    }


# =========================================================
# SERPAPI
# =========================================================

def serpapi_request(params):
    if not SERPAPI_KEY:
        return {
            "success": False,
            "message": "SERPAPI_KEY is not configured"
        }

    request_params = dict(params)
    request_params["api_key"] = SERPAPI_KEY

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params=request_params,
            timeout=25
        )

        try:
            return response.json()
        except Exception:
            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:500]
            }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


# =========================================================
# FILTER JUNK GOOGLE RESULTS
# =========================================================

def looks_like_junk_result(title, snippet, link):
    text = f"{title} {snippet}".lower()

    # Many unrelated phone-number-like strings
    number_count = len(
        re.findall(r"\b0\d{8,10}\b", text)
    )

    hostname = ""

    try:
        hostname = urlparse(link).hostname or ""
    except Exception:
        pass

    if (
        title.lower().strip() == "untitled"
        and number_count >= 5
    ):
        return True

    if (
        number_count >= 8
        and (
            "cloudfront.net" in hostname
            or "web.core.windows.net" in hostname
        )
    ):
        return True

    return False


# =========================================================
# GOOGLE ENRICHED SEARCH
# =========================================================

def search_google_enriched(e164, local=None, region="AE"):
    exact_numbers = [f'"{e164}"']

    if local:
        exact_numbers.append(f'"{local}"')

    number_query = " OR ".join(exact_numbers)

    query = (
        f"({number_query}) "
        f"(name OR contact OR mobile OR phone OR whatsapp "
        f"OR company OR business "
        f"OR site:linkedin.com "
        f"OR site:facebook.com "
        f"OR site:instagram.com "
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

    results = []

    if not isinstance(data, dict):
        return results

    for item in data.get("organic_results", []):
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")

        if looks_like_junk_result(
            title,
            snippet,
            link
        ):
            continue

        results.append({
            "title": title,
            "link": link,
            "snippet": snippet,
            "source": item.get("source", "")
        })

    return results


# =========================================================
# GOOGLE MAPS / BUSINESS SEARCH
# =========================================================

def search_google_maps(e164, local=None):
    query = local or e164

    data = serpapi_request({
        "engine": "google_maps",
        "type": "search",
        "q": query,
        "hl": "en"
    })

    results = []

    if not isinstance(data, dict):
        return results

    for item in data.get("local_results", []):
        results.append({
            "title": item.get("title"),
            "type": item.get("type"),
            "address": item.get("address"),
            "phone": item.get("phone"),
            "website": item.get("website"),
            "description": item.get("description"),
            "rating": item.get("rating"),
            "reviews": item.get("reviews")
        })

    return results


# =========================================================
# BUILD BEST IDENTITY
# =========================================================

def normalize_name(name):
    if not isinstance(name, str):
        return None

    return re.sub(
        r"[^a-z0-9]",
        "",
        name.lower()
    )


def build_best_identity(ipqs, pdl):
    ipqs_name = ipqs.get("name")
    pdl_name = pdl.get("full_name")
    likelihood = pdl.get("likelihood")

    # Both databases agree
    if (
        ipqs_name
        and pdl_name
        and normalize_name(ipqs_name)
        == normalize_name(pdl_name)
    ):
        return {
            "name": pdl_name,
            "confidence": "high",
            "sources": [
                "IPQualityScore",
                "People Data Labs"
            ]
        }

    # Strong PDL match
    if pdl_name:
        confidence = "medium"

        if isinstance(likelihood, (int, float)):
            if likelihood >= 8:
                confidence = "high"
            elif likelihood >= 6:
                confidence = "medium"
            else:
                confidence = "low"

        return {
            "name": pdl_name,
            "confidence": confidence,
            "sources": [
                "People Data Labs"
            ],
            "pdl_likelihood": likelihood
        }

    # IPQS only
    if ipqs_name:
        return {
            "name": ipqs_name,
            "confidence": "medium",
            "sources": [
                "IPQualityScore"
            ]
        }

    return {
        "name": None,
        "confidence": "none",
        "sources": []
    }


# =========================================================
# MAIN SEARCH
# =========================================================

@app.get("/search")
def search_phone(
    phone: str = Query(
        ...,
        description="Phone number, preferably international format"
    ),
    region: str = Query(
        "AE",
        description="Two-letter country code"
    )
):
    try:
        region = region.upper()

        osint = PhoneOSINT()

        variants = phone_variants(
            phone,
            region
        )

        main_number = choose_e164(
            variants,
            phone
        )

        local_number = choose_local(
            variants
        )

        # Run services together
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=12
        ) as executor:

            jobs = {
                "ipqs": executor.submit(
                    check_ipqs,
                    main_number,
                    region
                ),

                "pdl": executor.submit(
                    check_pdl,
                    main_number,
                    region
                ),

                "numverify": executor.submit(
                    safe_call,
                    osint.check_numverify,
                    main_number,
                    region
                ),

                "hudson_rock": executor.submit(
                    safe_call,
                    osint.check_hudsonrock,
                    main_number
                ),

                "google_exact": executor.submit(
                    safe_call,
                    osint.search_google,
                    main_number
                ),

                "google_enriched": executor.submit(
                    search_google_enriched,
                    main_number,
                    local_number,
                    region
                ),

                "google_maps": executor.submit(
                    search_google_maps,
                    main_number,
                    local_number
                ),

                "github_international": executor.submit(
                    safe_call,
                    osint.search_github,
                    main_number
                ),

                "reddit_international": executor.submit(
                    safe_call,
                    osint.search_reddit,
                    main_number
                ),

                "duckduckgo_international": executor.submit(
                    safe_call,
                    osint.search_duckduckgo,
                    main_number
                )
            }

            if local_number:
                jobs["github_local"] = executor.submit(
                    safe_call,
                    osint.search_github,
                    local_number
                )

                jobs["reddit_local"] = executor.submit(
                    safe_call,
                    osint.search_reddit,
                    local_number
                )

                jobs["duckduckgo_local"] = executor.submit(
                    safe_call,
                    osint.search_duckduckgo,
                    local_number
                )

            collected = {}

            for name, future in jobs.items():
                try:
                    collected[name] = future.result(
                        timeout=40
                    )
                except Exception as e:
                    collected[name] = {
                        "error": str(e)
                    }

        # Simplified identity sources
        ipqs_identity = simplify_ipqs(
            collected.get("ipqs", {})
        )

        pdl_identity = simplify_pdl(
            collected.get("pdl", {})
        )

        best_identity = build_best_identity(
            ipqs_identity,
            pdl_identity
        )

        phone_info = safe_call(
            osint.validate_phone,
            main_number,
            region
        )

        return {
            "phone": phone,
            "region": region,

            "searched_variants": variants,

            # MAIN RESULT
            "best_identity": best_identity,

            # IDENTITY DATABASES
            "identity": {
                "ipqs": ipqs_identity,
                "pdl": pdl_identity
            },

            # RAW STATUS / DATABASE RESULTS
            "ipqs": collected.get("ipqs"),
            "pdl": collected.get("pdl"),

            "phone_info": phone_info,

            "numverify": collected.get(
                "numverify"
            ),

            "hudson_rock": collected.get(
                "hudson_rock"
            ),

            # WEB SEARCH
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

            "source_status": {
                "ipqs_configured": bool(
                    IPQS_KEY
                ),

                "pdl_configured": bool(
                    PDL_API_KEY
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
