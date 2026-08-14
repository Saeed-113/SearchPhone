from fastapi import FastAPI, Query, HTTPException
from search_phone import PhoneOSINT
import os
import re
import requests
import concurrent.futures

app = FastAPI(
    title="SearchPhone API",
    version="3.0"
)

IPQS_KEY = os.getenv("IPQS_KEY", "")


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "SearchPhone API v3 is running"
    }


def phone_variants(phone: str):
    digits = re.sub(r"\D", "", phone)

    variants = []

    def add(value):
        if value and value not in variants:
            variants.append(value)

    add(phone)
    add("+" + digits)
    add(digits)

    # UAE conversion
    if digits.startswith("971") and len(digits) == 12:
        local = "0" + digits[3:]

        add(local)

        # 055 323 2334
        if len(local) == 10:
            add(f"{local[:3]} {local[3:6]} {local[6:]}")

        # +971 55 323 2334
        add(f"+971 {digits[3:5]} {digits[5:8]} {digits[8:]}")

    return variants


def check_ipqs(phone: str, region: str = "AE"):
    if not IPQS_KEY:
        return {
            "success": False,
            "message": "IPQS_KEY is not configured"
        }

    try:
        url = "https://ipqualityscore.com/api/json/phone"

        headers = {
            "IPQS-KEY": IPQS_KEY
        }

        params = {
            "phone": phone,
            "strictness": 1
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        data = response.json()

        if response.status_code != 200:
            return {
                "success": False,
                "status_code": response.status_code,
                "message": data
            }

        return data

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


def simplify_ipqs(data):
    if not isinstance(data, dict):
        return {}

    name = data.get("name")

    if name in ["N/A", "", None]:
        name = None

    associated_emails = []

    email_data = data.get("associated_email_addresses")

    if isinstance(email_data, dict):
        emails = email_data.get("emails", [])

        if isinstance(emails, list):
            associated_emails = emails

    return {
        "name": name,
        "associated_emails": associated_emails,
        "valid": data.get("valid"),
        "active": data.get("active"),
        "formatted": data.get("formatted"),
        "local_format": data.get("local_format"),
        "carrier": data.get("carrier"),
        "line_type": data.get("line_type"),
        "country": data.get("country"),
        "region": data.get("region"),
        "city": data.get("city"),
        "timezone": data.get("timezone"),
        "fraud_score": data.get("fraud_score"),
        "risky": data.get("risky"),
        "spammer": data.get("spammer"),
        "leaked": data.get("leaked"),
        "VOIP": data.get("VOIP"),
        "prepaid": data.get("prepaid"),
        "user_activity": data.get("user_activity")
    }


@app.get("/search")
def search_phone(
    phone: str = Query(
        ...,
        description="Phone number including international country code"
    ),
    region: str = Query(
        "AE",
        description="Two-letter country code"
    )
):
    try:
        osint = PhoneOSINT()

        variants = phone_variants(phone)

        # Prefer international number
        main_number = variants[1] if len(variants) > 1 else phone

        local_variant = None

        for variant in variants:
            if variant.startswith("0") and " " not in variant:
                local_variant = variant
                break

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:

            jobs = {
                "ipqs": executor.submit(
                    check_ipqs,
                    main_number,
                    region
                ),

                "numverify": executor.submit(
                    osint.check_numverify,
                    main_number,
                    region
                ),

                "hudson_rock": executor.submit(
                    osint.check_hudsonrock,
                    main_number
                ),

                "google": executor.submit(
                    osint.search_google,
                    main_number
                ),

                "github_international": executor.submit(
                    osint.search_github,
                    main_number
                ),

                "reddit_international": executor.submit(
                    osint.search_reddit,
                    main_number
                ),

                "duckduckgo": executor.submit(
                    osint.search_duckduckgo,
                    main_number
                )
            }

            # Also search UAE local format when available
            if local_variant:
                jobs["github_local"] = executor.submit(
                    osint.search_github,
                    local_variant
                )

                jobs["reddit_local"] = executor.submit(
                    osint.search_reddit,
                    local_variant
                )

            results = {}

            for name, future in jobs.items():
                try:
                    results[name] = future.result(timeout=25)
                except Exception as e:
                    results[name] = {
                        "error": str(e)
                    }

        ipqs_raw = results.get("ipqs", {})

        identity = simplify_ipqs(ipqs_raw)

        return {
            "phone": phone,
            "region": region.upper(),

            "searched_variants": variants,

            "identity": identity,

            "ipqs": ipqs_raw,

            "phone_info": osint.validate_phone(
                main_number,
                region
            ),

            "numverify": results.get("numverify"),

            "hudson_rock": results.get("hudson_rock"),

            "google": results.get("google", []),

            "github": {
                "international": results.get(
                    "github_international",
                    []
                ),
                "local": results.get(
                    "github_local",
                    []
                )
            },

            "reddit": {
                "international": results.get(
                    "reddit_international",
                    []
                ),
                "local": results.get(
                    "reddit_local",
                    []
                )
            },

            "duckduckgo": results.get(
                "duckduckgo",
                []
            )
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
