from fastapi import FastAPI, Query, HTTPException
from search_phone import PhoneOSINT

app = FastAPI(
    title="SearchPhone API",
    version="1.0"
)

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "SearchPhone API is running"
    }

@app.get("/search")
def search_phone(
    phone: str = Query(..., description="Phone number including country code"),
    region: str = Query("AE", description="Two-letter country code")
):
    try:
        osint = PhoneOSINT()

        phone_info = osint.validate_phone(phone, region)

        results = {
            "phone": phone,
            "region": region.upper(),
            "phone_info": phone_info,
            "numverify": osint.check_numverify(phone, region),
            "google": osint.search_google(phone),
            "github": osint.search_github(phone),
            "reddit": osint.search_reddit(phone),
            "duckduckgo": osint.search_duckduckgo(phone)
        }

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
