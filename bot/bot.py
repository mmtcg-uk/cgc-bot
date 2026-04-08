import discord
import requests
import asyncio
import json
import os
import re

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

EBAY_CLIENT_ID = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]

SEEN_FILE = "seen_items.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/extra whitespace for fuzzy title comparison."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title

def load_seen_items():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                data = json.load(f)
                # Support both old format (list of IDs) and new format (dict with ids + titles)
                if isinstance(data, dict):
                    return set(data.get("ids", [])), set(data.get("titles", []))
                else:
                    return set(data), set()
        except:
            return set(), set()
    return set(), set()

def save_seen_items(seen_ids, seen_titles):
    with open(SEEN_FILE, "w") as f:
        json.dump({"ids": list(seen_ids), "titles": list(seen_titles)}, f)

seen_ids, seen_titles = load_seen_items()

def get_ebay_token():
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["access_token"]

def get_ebay_listings(token):
    queries = ["CGC 9.5", "CGC Blue Label"]
    batch_ids = set()  # deduplicate within this fetch batch only
    all_items = []
    for query in queries:
        response = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "limit": 20},
            timeout=30
        )
        response.raise_for_status()
        for item in response.json().get("itemSummaries", []):
            item_id = item.get("itemId")
            if item_id and item_id not in batch_ids:
                batch_ids.add(item_id)
                all_items.append(item)
    return all_items

COUNTRY_FLAGS = {
    "united states": "🇺🇸",
    "united kingdom": "🇬🇧",
    "japan": "🇯🇵",
    "germany": "🇩🇪",
    "france": "🇫🇷",
    "canada": "🇨🇦",
    "australia": "🇦🇺",
    "italy": "🇮🇹",
    "spain": "🇪🇸",
    "netherlands": "🇳🇱",
    "china": "🇨🇳",
    "south korea": "🇰🇷",
    "hong kong": "🇭🇰",
    "singapore": "🇸🇬",
    "taiwan": "🇹🇼",
    "brazil": "🇧🇷",
    "mexico": "🇲🇽",
    "sweden": "🇸🇪",
    "norway": "🇳🇴",
    "denmark": "🇩🇰",
    "finland": "🇫🇮",
    "switzerland": "🇨🇭",
    "austria": "🇦🇹",
    "belgium": "🇧🇪",
    "poland": "🇵🇱",
    "portugal": "🇵🇹",
    "new zealand": "🇳🇿",
    "ireland": "🇮🇪",
    "israel": "🇮🇱",
    "india": "🇮🇳",
    "russia": "🇷🇺",
    "ukraine": "🇺🇦",
    "greece": "🇬🇷",
    "czech republic": "🇨🇿",
    "hungary": "🇭🇺",
    "romania": "🇷🇴",
    "thailand": "🇹🇭",
    "malaysia": "🇲🇾",
    "indonesia": "🇮🇩",
    "philippines": "🇵🇭",
    "south africa": "🇿🇦",
    "argentina": "🇦🇷",
    "chile": "🇨🇱",
    "colombia": "🇨🇴",
}

def get_country_flag(location: str) -> str:
    """Return a flag emoji for the given location string, or 🌍 if unknown."""
    if not location:
        return "🌍"
    normalised = location.lower().strip()
    # Try longest match first so "United Kingdom" beats "United"
    for country, flag in sorted(COUNTRY_FLAGS.items(), key=lambda x: len(x[0]), reverse=True):
        if country in normalised:
            return flag
    return "🌍"

def is_target_item(item):
    title = item.get("title", "").lower()
    return "cgc 9.5" in title or "cgc blue label" in title

async def check_ebay():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return
    while not client.is_closed():
        print("Checking eBay...")
        try:
            token = get_ebay_token()
            items = get_ebay_listings(token)
            for item in items:
                item_id = item.get("itemId")
                if not item_id or not is_target_item(item):
                    continue
                # Primary dedup: by itemId
                if item_id in seen_ids:
                    continue
                # Secondary dedup: by normalized title (catches same product with different IDs)
                title = item.get("title", "No title")
                norm_title = normalize_title(title)
                if norm_title in seen_titles:
                    continue
                seen_ids.add(item_id)
                seen_titles.add(norm_title)
                save_seen_items(seen_ids, seen_titles)
                price_data = item.get("price", {})
                price = price_data.get("value", "N/A")
                currency = price_data.get("currency", "")
                url = item.get("itemWebUrl", "")
                location_data = item.get("itemLocation", {})
                location = location_data.get("country", "") or location_data.get("postalCode", "")
                location_name = (
                    location_data.get("city", "")
                    or location_data.get("stateOrProvince", "")
                    or location_data.get("country", "")
                    or "Unknown"
                )
                flag = get_country_flag(location_data.get("country", ""))
                image_url = (
                    (item.get("image") or {}).get("imageUrl")
                    or (item.get("thumbnailImages") or [{}])[0].get("imageUrl")
                    or ""
                )
                embed = discord.Embed(
                    title=title,
                    url=url,
                    color=0x0064D2,  # eBay blue
                )
                embed.add_field(name="💰 Price", value=f"{price} {currency}", inline=True)
                embed.add_field(name="📍 Location", value=f"{flag} {location_name}", inline=True)
                embed.set_footer(text="eBay • CGC Listings")
                if image_url:
                    embed.set_image(url=image_url)
                await channel.send(embed=embed)
        except Exception as e:
            print("Error:", e)
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Bot online as {client.user}")
    asyncio.create_task(check_ebay())

client.run(DISCORD_TOKEN)
