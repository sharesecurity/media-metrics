"""
GDELT Ingest Pipeline
Downloads and ingests articles from the GDELT Project's GKG (Global Knowledge Graph).
GDELT is free, massive, and covers global news in real-time.
"""

import httpx
import pandas as pd
import io
import zipfile
import uuid
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models import Article, Source

# GDELT GKG master file list (updated every 15 minutes)
GDELT_MASTERLIST_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist-translation.txt"
GDELT_GKG_URL_BASE = "http://data.gdeltproject.org/gdeltv2/"

engine = create_async_engine(settings.database_url)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)

KNOWN_SOURCES = {
    "nytimes.com": "The New York Times",
    "foxnews.com": "Fox News",
    "reuters.com": "Reuters",
    "theguardian.com": "The Guardian",
    "washingtonpost.com": "The Washington Post",
    "wsj.com": "The Wall Street Journal",
    "apnews.com": "AP News",
    "bbc.com": "BBC News",
    "bbc.co.uk": "BBC News",
    "cnn.com": "CNN",
    "nbcnews.com": "NBC News",
    "abcnews.go.com": "ABC News",
    "cbsnews.com": "CBS News",
    "politico.com": "Politico",
    "thehill.com": "The Hill",
    "huffpost.com": "HuffPost",
    "breitbart.com": "Breitbart",
    "npr.org": "NPR",
    "usatoday.com": "USA Today",
    "latimes.com": "Los Angeles Times",
}

def extract_domain(url: str) -> Optional[str]:
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return match.group(1) if match else None

async def get_or_create_source(db: AsyncSession, domain: str, name: str) -> Optional[uuid.UUID]:
    result = await db.execute(select(Source).where(Source.name == name))
    source = result.scalar_one_or_none()
    if source:
        return source.id
    source = Source(name=name, domain=domain, country="US")
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source.id

async def ingest_gdelt_sample(limit: int = 100, date: Optional[str] = None):
    """
    Download a sample of recent GDELT articles and store them in the DB.
    Uses the GDELT Events CSV (simpler than GKG for getting started).
    """
    print(f"[GDELT] Starting ingest: limit={limit}, date={date}")

    # Use GDELT's simpler events endpoint for the last available day
    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
    else:
        dt = datetime.now(timezone.utc) - timedelta(days=1)

    date_str = dt.strftime("%Y%m%d")

    # Download GDELT GKG CSV for that date (contains URLs and themes)
    url = f"http://data.gdeltproject.org/gkg/{date_str}.gkg.csv.zip"
    print(f"[GDELT] Downloading {url}")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code != 200:
                # Fall back to a known good sample from kaggle-style embedded data
                print(f"[GDELT] Failed to download GKG ({resp.status_code}), using embedded sample")
                await ingest_embedded_sample(limit)
                return

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                df = pd.read_csv(f, sep='\t', header=None, on_bad_lines='skip',
                                 usecols=[0,1,3,4,7,9], nrows=limit * 5)

        print(f"[GDELT] Downloaded {len(df)} rows from GKG")

        # GKG columns: DATE, NUMARTS, V2Counts, V2Themes, V2Locations, V2SourceCommonName, DocumentIdentifier...
        # Simplified: col 0=date, col 3=themes, col 9=source URL
        ingested = 0
        async with AsyncSession_() as db:
            for _, row in df.iterrows():
                if ingested >= limit:
                    break
                try:
                    url_val = str(row.iloc[5]) if len(row) > 5 else ""
                    if not url_val or url_val == "nan" or not url_val.startswith("http"):
                        continue

                    domain = extract_domain(url_val)
                    if not domain:
                        continue

                    # Only keep known English news sources
                    source_name = KNOWN_SOURCES.get(domain)
                    if not source_name:
                        continue

                    # Check if URL already ingested
                    existing = await db.execute(select(Article).where(Article.url == url_val))
                    if existing.scalar_one_or_none():
                        continue

                    source_id = await get_or_create_source(db, domain, source_name)
                    date_val = str(row.iloc[0])
                    try:
                        pub_date = datetime.strptime(date_val[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
                    except Exception:
                        pub_date = None

                    themes = str(row.iloc[3]) if len(row) > 3 else ""
                    tags = [t.strip() for t in themes.split(";") if t.strip()][:10]

                    article = Article(
                        source_id=source_id,
                        url=url_val,
                        title=f"Article from {source_name} ({pub_date.date() if pub_date else 'unknown'})",
                        published_at=pub_date,
                        tags=tags,
                        section=_guess_section(tags),
                        gdelt_id=date_val,
                    )
                    db.add(article)
                    await db.commit()
                    ingested += 1
                    if ingested % 10 == 0:
                        print(f"[GDELT] Ingested {ingested} articles")
                except Exception as e:
                    print(f"[GDELT] Row error: {e}")
                    await db.rollback()
                    continue

        print(f"[GDELT] Done. Ingested {ingested} articles.")

    except Exception as e:
        print(f"[GDELT] Error: {e}")
        await ingest_embedded_sample(limit)

def _guess_section(tags: list) -> str:
    tag_str = " ".join(tags).upper()
    if "POLITIC" in tag_str or "GOV" in tag_str or "ELECT" in tag_str:
        return "politics"
    if "ECON" in tag_str or "MARKET" in tag_str or "FINANC" in tag_str:
        return "economy"
    if "HEALTH" in tag_str or "MED" in tag_str or "COVID" in tag_str:
        return "health"
    if "TECH" in tag_str or "DIGIT" in tag_str or "CYBER" in tag_str:
        return "technology"
    if "SPORT" in tag_str:
        return "sports"
    if "ENV" in tag_str or "CLIMAT" in tag_str:
        return "environment"
    if "CRIME" in tag_str or "LEGAL" in tag_str:
        return "crime"
    return "general"

async def ingest_embedded_sample(limit: int = 50):
    """
    Fallback: ingest a small set of hard-coded sample articles for demo purposes.
    These are realistic synthetic articles suitable for bias testing.
    """
    print("[GDELT] Using embedded sample data")

    SAMPLE_ARTICLES = [
        {
            "source": "The New York Times", "domain": "nytimes.com",
            "title": "Senate Democrats Push Major Climate Legislation Forward",
            "url": "https://nytimes.com/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-15",
            "text": """Senate Democrats on Wednesday pushed forward sweeping climate legislation 
that would allocate $400 billion for renewable energy infrastructure over the next decade. 
The bill, championed by progressive members of the caucus, faces fierce opposition from 
Republican lawmakers who argue it would devastate the fossil fuel industry and drive up 
energy costs for working families. Climate scientists and environmental advocates praised 
the measure as a necessary step to address the accelerating crisis of global warming. 
Critics from the energy sector warn of potential job losses in coal and oil communities."""
        },
        {
            "source": "Fox News", "domain": "foxnews.com",
            "title": "Democrat Climate Bill Would Destroy American Energy Jobs, Critics Warn",
            "url": "https://foxnews.com/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-15",
            "text": """The radical climate legislation pushed by Senate Democrats would 
devastate American energy independence and eliminate thousands of well-paying jobs 
in the fossil fuel sector, industry experts and Republican lawmakers warned Wednesday. 
The $400 billion spending package, derided by conservatives as a Green New Deal 
reboot, would force working families to pay higher electricity bills while enriching 
green energy corporations with taxpayer money. The Heritage Foundation estimates the 
bill could cost up to 500,000 jobs by 2030."""
        },
        {
            "source": "Reuters", "domain": "reuters.com",
            "title": "U.S. Senate Advances $400 Billion Climate Package",
            "url": "https://reuters.com/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-15",
            "text": """The U.S. Senate advanced a $400 billion climate and energy package 
on Wednesday in a procedural vote, with Democrats arguing the bill would accelerate 
the transition to clean energy while Republicans said it would harm fossil fuel workers. 
The legislation includes tax credits for electric vehicles, subsidies for solar and wind 
power installations, and penalties for companies exceeding carbon emission thresholds. 
Both sides cited economic studies supporting their respective positions."""
        },
        {
            "source": "AP News", "domain": "apnews.com",
            "title": "Senate Climate Vote: What's in the $400B Bill",
            "url": "https://apnews.com/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-15",
            "text": """The Senate voted Wednesday to advance a $400 billion climate and 
energy spending bill. Here's what's in it: The legislation allocates funds across 
several areas including renewable energy development, grid modernization, electric 
vehicle incentives, and support programs for workers in fossil fuel industries 
transitioning to other employment. The bill passed its procedural hurdle 51-49 
along party lines and now advances to full debate."""
        },
        {
            "source": "The Guardian", "domain": "theguardian.com",
            "title": "US Climate Bill: A Turning Point or Too Little, Too Late?",
            "url": "https://theguardian.com/sample/climate-bill-2024",
            "section": "environment",
            "published_at": "2024-01-15",
            "text": """As the Senate advanced its landmark climate legislation Wednesday, 
environmentalists celebrated what they called a historic step while warning that 
even this ambitious package falls short of what scientists say is needed to prevent 
catastrophic warming. The bill's $400 billion would represent the largest US climate 
investment ever, but critics note it still permits continued fossil fuel extraction. 
Indigenous communities near proposed renewable energy sites have raised concerns about 
land rights and consultation processes."""
        },
        {
            "source": "The Washington Post", "domain": "washingtonpost.com",
            "title": "How the Senate Climate Bill Could Reshape American Energy",
            "url": "https://washingtonpost.com/sample/climate-bill-2024",
            "section": "economy",
            "published_at": "2024-01-16",
            "text": """The Senate's landmark climate legislation, advancing through procedural 
votes this week, could fundamentally reshape the American energy landscape over the 
next decade. Analysis from the Congressional Budget Office suggests the $400 billion 
package would reduce US greenhouse gas emissions by approximately 40% from 2005 levels 
by 2030. Energy economists are divided on the economic impact, with some projecting 
job gains in the clean energy sector and others warning of disruption in fossil fuel 
dependent regions."""
        },
        {
            "source": "Breitbart", "domain": "breitbart.com",
            "title": "Green New Deal 2.0: Democrats' $400B Climate Scam Moves Forward",
            "url": "https://breitbart.com/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-15",
            "text": """Radical Democrats have pushed their $400 billion climate slush fund 
one step closer to passage, advancing what critics call the most economically destructive 
legislation in American history. The bill, a thinly veiled wealth redistribution scheme, 
would funnel taxpayer money to Democrat-connected green energy cronies while making 
gasoline and electricity unaffordable for ordinary Americans. China, which continues 
to build coal plants at record rates, would benefit most as American energy production 
is strangled by these radical regulations."""
        },
        {
            "source": "NPR", "domain": "npr.org",
            "title": "The Senate's Climate Bill: Winners, Losers, And Uncertain Outcomes",
            "url": "https://npr.org/sample/climate-bill-2024",
            "section": "politics",
            "published_at": "2024-01-16",
            "text": """The climate legislation moving through the Senate this week would 
create clear winners and losers across the American economy. Electric vehicle manufacturers 
and renewable energy developers stand to gain significantly from expanded tax credits 
and subsidies. Coal miners and oil field workers face potential job losses, though 
the bill includes $20 billion in transition assistance. Rural communities hosting 
wind and solar installations could see new tax revenue, while consumer advocates 
are uncertain whether energy costs will ultimately rise or fall."""
        },
    ]

    async with AsyncSession_() as db:
        ingested = 0
        for sample in SAMPLE_ARTICLES[:limit]:
            try:
                existing = await db.execute(select(Article).where(Article.url == sample["url"]))
                if existing.scalar_one_or_none():
                    continue

                source_id = await get_or_create_source(db, sample["domain"], sample["source"])
                pub_date = datetime.strptime(sample["published_at"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

                article = Article(
                    source_id=source_id,
                    url=sample["url"],
                    title=sample["title"],
                    published_at=pub_date,
                    section=sample["section"],
                    raw_text=sample["text"],
                    word_count=len(sample["text"].split()),
                    tags=[sample["section"], "climate", "senate"],
                )
                db.add(article)
                await db.commit()
                ingested += 1
            except Exception as e:
                print(f"[Sample] Error: {e}")
                await db.rollback()

    print(f"[Sample] Ingested {ingested} sample articles")
