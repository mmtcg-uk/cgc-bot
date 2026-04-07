import discord
import requests
import asyncio
import json
import os

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

EBAY_CLIENT_ID = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]

SEEN_FILE = "seen_items.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def load_seen_items():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_seen_items(seen_items):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_items), f)

seen_items = load_seen_items()

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
    response = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "CGC 9.5", "limit": 5},
        timeout=30
    )
    response.raise_for_status()
    return response.json().get("itemSummaries", [])

def is_cgc_95(item):
    return "cgc 9.5" in item.get("title", "").lower()

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
                if not item_id or item_id in seen_items or not is_cgc_95(item):
                    continue
                seen_items.add(item_id)
                save_seen_items(seen_items)
                title = item.get("title", "No title")
                price_data = item.get("price", {})
                price = price_data.get("value", "N/A")
                currency = price_data.get("currency", "")
                url = item.get("itemWebUrl", "")
                await channel.send(f"{title}\n{price} {currency}\n{url}")
        except Exception as e:
            print("Error:", e)
        await asyncio.sleep(300)

@client.event
async def on_ready():
    print(f"Bot online as {client.user}")
    asyncio.create_task(check_ebay())

client.run(DISCORD_TOKEN)
