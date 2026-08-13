from fastapi import FastAPI, Query, HTTPException
from search_phone import PhoneOSINT
import re

app = FastAPI(
    title="SearchPhone API",
    version="2.0"
)

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "SearchPhone API v2 is running"
    }


def phone_variants(phone: str):
    clean = re.sub(r"[^\d+]", "", phone)

    digits = re.sub(r"\D", "", phone)

    variants = {
        phone,
        clean,
        digits
    }

    # UAE number conversions
    if digits.startswith("971") and len(digits) >= 11:
        local = "0" + digits[3:]
        variants.add(local)
        variants.add("+" + digits)

        # Spaced formats
        if len(local) == 10:
            variants.add(
                f"{local[:3]} {local[3:6]} {local[6:]}"
            )

        if len(digits) == 12:
            variants.add(
                f"+971 {digits[3:5]} {digits[5:8]} {digits[8:]}"
            )

    return list(variants)


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

        results = {
            "phone": phone,
            "region": region.upper(),
            "searched_variants": variants,
            "phone_info": osint.validate_phone(phone, region),
            "numverify": osint.check_numverify(phone, region),
            "searches": []
        }

        for variant in variants:
            item = {
                "variant": variant,
                "google": osint.search_google(variant),
                "github": osint.search_github(variant),
                "reddit": osint.search_reddit(variant),
                "duckduckgo": osint.search_duckduckgo(variant)
            }

            # Hudson Rock support, if available in this version
            try:
                item["hudson_rock"] = osint.check_hudson_rock(variant)
            except Exception:
                item["hudson_rock"] = None

            results["searches"].append(item)

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
