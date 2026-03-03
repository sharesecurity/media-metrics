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
from app.models import Article, Source, Author

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

_ORG_KEYWORDS = frozenset([
    "news", "press", "wire", "staff", "report", "reporter", "reporters",
    "network", "media", "times", "post", "journal", "tribune", "bureau",
    "service", "agency", "reuters", "bloomberg", "editors", "editorial",
    "desk", "correspondent", "correspondents", "team",
    # Domain/URL fragments that appear in publisher bylines (e.g. "Dailymail com")
    "com", "co", "org", "net", "uk", "dailymail", "mailonline",
])


def _is_org_byline(name: str) -> bool:
    """Return True if the name looks like an organisation rather than a person."""
    lower_words = set(name.lower().split())
    return bool(lower_words & _ORG_KEYWORDS)


def split_author_names(raw: str) -> list:
    """
    Split a raw author string that may contain multiple names into a list
    of individual clean person-name strings.

    Handles separators: comma, ' and ', ' & ', semicolon.
    Each part must look like a real person name (≥ 2 words, ≤ 5 words,
    starts with capital letter, not an organisation byline).
    Falls back to [raw] if nothing valid is found after splitting.

    Examples:
        "Evan Halper, Rachel Siegel"  → ["Evan Halper", "Rachel Siegel"]
        "John Smith and Jane Doe"     → ["John Smith", "Jane Doe"]
        "Alice Johnson & Bob Lee"     → ["Alice Johnson", "Bob Lee"]
        "Single Author"               → ["Single Author"]
        "Associated Press"            → []   (org keyword)
        "Breitbart News"              → []   (org keyword)
    """
    if not raw or not raw.strip():
        return []

    # Normalise whitespace first
    raw = " ".join(raw.split())

    # Reject whole string if it looks like an organisation byline
    if _is_org_byline(raw):
        return []

    # Split on typical multi-author separators
    parts = re.split(r',\s+|\s+and\s+|\s*&\s*|\s*;\s*', raw)

    valid = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Skip organisation-like parts
        if _is_org_byline(part):
            continue
        words = part.split()
        # Need at least 2 words to look like a real "First Last" name and
        # avoid treating honorific suffixes ("Jr.", "III") as standalone names.
        if len(words) < 2:
            continue
        # Sanity: not excessively long (titles / org names slip through otherwise)
        if len(words) > 5:
            continue
        # At least the first word should start with a capital letter
        if not words[0][0].isupper():
            continue
        valid.append(part)

    return valid if valid else ([raw.strip()] if raw.strip() and not _is_org_byline(raw) else [])


def extract_author_from_text(text: str) -> Optional[str]:
    """Extract author name from article text using common byline patterns."""
    if not text:
        return None
    patterns = [
        r'^By ([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r'By ([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[|\n\r]',
        r'Written by ([A-Z][a-z]+ [A-Z][a-z]+)',
        r'Reported by ([A-Z][a-z]+ [A-Z][a-z]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:500])
        if match:
            name = match.group(1).strip()
            # Sanity check: no more than 4 words, each capitalized
            parts = name.split()
            if 2 <= len(parts) <= 4:
                return name
    return None

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

async def get_or_create_author(db: AsyncSession, name: str, source_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Find or create an author record, with demographic inference on creation."""
    from app.services.demographics import infer_demographics
    result = await db.execute(
        select(Author).where(Author.name == name, Author.source_id == source_id)
    )
    author = result.scalar_one_or_none()
    if author:
        return author.id
    demo = infer_demographics(name)
    author = Author(
        name=name,
        source_id=source_id,
        gender=demo.get("gender"),
        ethnicity=demo.get("ethnicity"),
        created_at=datetime.now(timezone.utc),
    )
    db.add(author)
    await db.commit()
    await db.refresh(author)
    return author.id

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
                print(f"[GDELT] Failed to download GKG ({resp.status_code}), using embedded sample")
                await ingest_embedded_sample(limit)
                return

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                # GKG 1.0 columns:
                #   0=DATE, 3=THEMES, 9=SOURCES (domains), 10=SOURCEURLS (URLs)
                # Read all cols up to 11 to safely access col 10
                df = pd.read_csv(f, sep='\t', header=None, on_bad_lines='skip', nrows=limit * 20)

        print(f"[GDELT] Downloaded {len(df)} rows from GKG")

        ingested = 0
        async with AsyncSession_() as db:
            for _, row in df.iterrows():
                if ingested >= limit:
                    break
                try:
                    # GKG 1.0: col 9 = SOURCES (domains), col 10 = SOURCEURLS
                    if len(row) <= 10:
                        continue
                    sources_str = str(row.iloc[9]) if not pd.isna(row.iloc[9]) else ""
                    urls_str = str(row.iloc[10]) if not pd.isna(row.iloc[10]) else ""
                    themes_str = str(row.iloc[3]) if not pd.isna(row.iloc[3]) else ""
                    date_val = str(row.iloc[0])

                    source_domains = [d.strip() for d in sources_str.split(";") if d.strip()]
                    source_urls = [u.strip() for u in urls_str.split(";") if u.strip()]

                    # Pair each domain with its URL and filter to known outlets
                    for domain, url_val in zip(source_domains, source_urls):
                        if ingested >= limit:
                            break
                        domain = domain.replace("www.", "")
                        source_name = KNOWN_SOURCES.get(domain)
                        if not source_name:
                            continue
                        if not url_val.startswith("http"):
                            continue

                        existing = await db.execute(select(Article).where(Article.url == url_val))
                        if existing.scalar_one_or_none():
                            continue

                        source_id = await get_or_create_source(db, domain, source_name)
                        try:
                            pub_date = datetime.strptime(date_val[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
                        except Exception:
                            pub_date = None

                        tags = [t.strip() for t in themes_str.split(";") if t.strip()][:10]

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

# ---------------------------------------------------------------------------
# Expanded embedded sample articles — 6 stories × multiple outlets × dates
# ---------------------------------------------------------------------------

SAMPLE_ARTICLES = [
    # =========================================================================
    # STORY 1: Senate Climate Bill (January 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Senate Democrats Push Major Climate Legislation Forward",
        "url": "https://nytimes.com/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-15",
        "author": "Sarah Mitchell",
        "text": """By Sarah Mitchell

Senate Democrats on Wednesday pushed forward sweeping climate legislation that would allocate $400 billion for renewable energy infrastructure over the next decade. The bill, championed by progressive members of the caucus, faces fierce opposition from Republican lawmakers who argue it would devastate the fossil fuel industry and drive up energy costs for working families. Climate scientists and environmental advocates praised the measure as a necessary step to address the accelerating crisis of global warming. Critics from the energy sector warn of potential job losses in coal and oil communities."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Democrat Climate Bill Would Destroy American Energy Jobs, Critics Warn",
        "url": "https://foxnews.com/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-15",
        "author": "Tucker Reynolds",
        "text": """By Tucker Reynolds

The radical climate legislation pushed by Senate Democrats would devastate American energy independence and eliminate thousands of well-paying jobs in the fossil fuel sector, industry experts and Republican lawmakers warned Wednesday. The $400 billion spending package, derided by conservatives as a Green New Deal reboot, would force working families to pay higher electricity bills while enriching green energy corporations with taxpayer money. The Heritage Foundation estimates the bill could cost up to 500,000 jobs by 2030."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. Senate Advances $400 Billion Climate Package",
        "url": "https://reuters.com/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-15",
        "text": """The U.S. Senate advanced a $400 billion climate and energy package on Wednesday in a procedural vote, with Democrats arguing the bill would accelerate the transition to clean energy while Republicans said it would harm fossil fuel workers. The legislation includes tax credits for electric vehicles, subsidies for solar and wind power installations, and penalties for companies exceeding carbon emission thresholds. Both sides cited economic studies supporting their respective positions."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "Senate Climate Vote: What's in the $400B Bill",
        "url": "https://apnews.com/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-15",
        "text": """The Senate voted Wednesday to advance a $400 billion climate and energy spending bill. The legislation allocates funds across several areas including renewable energy development, grid modernization, electric vehicle incentives, and support programs for workers in fossil fuel industries transitioning to other employment. The bill passed its procedural hurdle 51-49 along party lines and now advances to full debate."""
    },
    {
        "source": "The Guardian", "domain": "theguardian.com",
        "title": "US Climate Bill: A Turning Point or Too Little, Too Late?",
        "url": "https://theguardian.com/sample/climate-bill-2024",
        "section": "environment", "published_at": "2024-01-15",
        "text": """As the Senate advanced its landmark climate legislation Wednesday, environmentalists celebrated what they called a historic step while warning that even this ambitious package falls short of what scientists say is needed to prevent catastrophic warming. The bill's $400 billion would represent the largest US climate investment ever, but critics note it still permits continued fossil fuel extraction. Indigenous communities near proposed renewable energy sites have raised concerns about land rights and consultation processes."""
    },
    {
        "source": "The Washington Post", "domain": "washingtonpost.com",
        "title": "How the Senate Climate Bill Could Reshape American Energy",
        "url": "https://washingtonpost.com/sample/climate-bill-2024",
        "section": "economy", "published_at": "2024-01-16",
        "text": """The Senate's landmark climate legislation, advancing through procedural votes this week, could fundamentally reshape the American energy landscape over the next decade. Analysis from the Congressional Budget Office suggests the $400 billion package would reduce US greenhouse gas emissions by approximately 40% from 2005 levels by 2030. Energy economists are divided on the economic impact, with some projecting job gains in the clean energy sector and others warning of disruption in fossil fuel dependent regions."""
    },
    {
        "source": "Breitbart", "domain": "breitbart.com",
        "title": "Green New Deal 2.0: Democrats' $400B Climate Scam Moves Forward",
        "url": "https://breitbart.com/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-15",
        "text": """Radical Democrats have pushed their $400 billion climate slush fund one step closer to passage, advancing what critics call the most economically destructive legislation in American history. The bill, a thinly veiled wealth redistribution scheme, would funnel taxpayer money to Democrat-connected green energy cronies while making gasoline and electricity unaffordable for ordinary Americans. China, which continues to build coal plants at record rates, would benefit most as American energy production is strangled by these radical regulations."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "The Senate's Climate Bill: Winners, Losers, And Uncertain Outcomes",
        "url": "https://npr.org/sample/climate-bill-2024",
        "section": "politics", "published_at": "2024-01-16",
        "text": """The climate legislation moving through the Senate this week would create clear winners and losers across the American economy. Electric vehicle manufacturers and renewable energy developers stand to gain significantly from expanded tax credits and subsidies. Coal miners and oil field workers face potential job losses, though the bill includes $20 billion in transition assistance. Rural communities hosting wind and solar installations could see new tax revenue, while consumer advocates are uncertain whether energy costs will ultimately rise or fall."""
    },

    # =========================================================================
    # STORY 2: Immigration / Border Security Bill (March 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Bipartisan Border Bill Collapses Amid Political Pressures",
        "url": "https://nytimes.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-08",
        "author": "James Caldwell",
        "text": """By James Caldwell

A rare bipartisan border security deal collapsed in the Senate on Thursday after former President Donald Trump urged Republicans to reject the legislation, depriving his party of a major immigration achievement in an election year. The bill, negotiated over months by a small group of senators, would have tightened asylum standards, provided emergency authority to quickly turn away migrants at the border, and allocated $20 billion for enforcement. Democrats said they were willing to make historic concessions on border security, only to see Republicans walk away at the last minute for partisan purposes."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Senate Border Bill 'Amnesty in Disguise,' GOP Senators Say",
        "url": "https://foxnews.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-08",
        "author": "Brad Hawkins",
        "text": """By Brad Hawkins

Republican senators delivered a decisive defeat to the Senate border bill Thursday, with conservatives arguing the legislation would codify mass illegal immigration and reward lawbreakers with a pathway to remain in the United States. Critics called the measure amnesty in disguise, pointing to provisions that would allow migrants to request asylum even after crossing illegally. Border state Republicans said the bill would actually weaken deportation authority and allow the Biden administration to release up to 1.8 million migrants per year before triggering any emergency restrictions."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. Senate Rejects Bipartisan Border Security Legislation",
        "url": "https://reuters.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-08",
        "text": """The U.S. Senate on Thursday failed to advance a bipartisan border security bill that would have represented the most significant changes to immigration law in decades. The legislation fell 49-50, short of the 60-vote threshold needed to proceed, after most Republicans withdrew their support following criticism from the presumptive GOP presidential nominee. The bill would have raised the legal standard for initial asylum screenings, expanded immigration court capacity, and given the executive branch new emergency deportation powers."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "Senate Border Bill Fails: By the Numbers",
        "url": "https://apnews.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-08",
        "text": """The Senate's bipartisan border security bill failed Thursday on a 49-50 procedural vote, with most Republicans opposing the measure despite having helped write it. The bill would have set a daily threshold of 5,000 illegal crossings before triggering automatic border closures, hired 4,300 new asylum officers, and allocated $2.3 billion for border wall construction. It also included $60 billion in military aid for Ukraine. The White House called the vote a failure of leadership; Republican leadership said the bill was flawed from the start."""
    },
    {
        "source": "The Guardian", "domain": "theguardian.com",
        "title": "The US Border Bill's Demise Exposes the Cynicism of Immigration Politics",
        "url": "https://theguardian.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-09",
        "text": """The collapse of the Senate border security deal reveals the degree to which immigration policy has become a weapon rather than a governance challenge in American politics. Democrats made sweeping concessions — agreeing to the most restrictive asylum changes since the 1996 immigration reform — only to see Republicans abandon the bill the moment their party's presumptive presidential nominee signaled his opposition. Human rights advocates warned that several provisions in the bill would have endangered legitimate asylum seekers fleeing persecution."""
    },
    {
        "source": "The Washington Post", "domain": "washingtonpost.com",
        "title": "Inside the Collapse of the Senate's Last Best Hope on Border Security",
        "url": "https://washingtonpost.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-09",
        "author": "Elena Torres",
        "text": """By Elena Torres

Months of painstaking negotiations collapsed in days when the former president weighed in against the Senate border security deal, illustrating how thoroughly the Republican Party has come to defer to one man's political calculations over legislating. Senators who had spent weeks hammering out compromise language scrambled to distance themselves from a bill they had championed, afraid of primary challenges and social media backlash. The episode leaves the southern border without new legal authorities Congress had been promising voters for years."""
    },
    {
        "source": "Breitbart", "domain": "breitbart.com",
        "title": "Patriots Kill Dangerous Open Borders Bill: 'America First' Wins",
        "url": "https://breitbart.com/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-08",
        "text": """American patriots in the United States Senate killed a dangerous open borders bill Thursday that would have permanently enshrined Joe Biden's invasion of America into law. The so-called border security bill — written by globalist RINO senators in concert with left-wing open borders groups — would have allowed over 1.8 million illegal aliens per year to flood into the country before any emergency restrictions kicked in. President Trump urged Republicans to reject the amnesty scheme and hold out for a real solution after the election, when Americans can elect a president who will actually secure the border."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "Border Bill Failure Leaves Immigration System In Limbo",
        "url": "https://npr.org/sample/border-bill-2024",
        "section": "politics", "published_at": "2024-03-09",
        "text": """The Senate's failure to pass a bipartisan border security bill leaves the immigration system straining under record crossings with no new legal authorities or funding to address the backlog. Immigration courts now have over 3 million pending cases. Border communities report humanitarian challenges with inadequate shelter and services. Immigration advocates say Congress's repeated failure to act forces migrants into dangerous situations. Republican critics say the Biden administration's policies created the crisis and a new administration is needed before real reform is possible."""
    },

    # =========================================================================
    # STORY 3: Healthcare / Drug Price Negotiation (May 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Medicare Drug Price Negotiations Yield Significant Savings, Officials Say",
        "url": "https://nytimes.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-14",
        "author": "Patricia Greene",
        "text": """By Patricia Greene

For the first time in its history, Medicare has successfully negotiated lower prices for a set of widely used prescription drugs, the Biden administration announced Tuesday, claiming savings of up to 79% on some medications. The negotiations, authorized by the Inflation Reduction Act, cover 10 drugs including blood thinners, diabetes medications, and cancer treatments. Starting in 2026, Medicare enrollees will pay significantly less for these drugs. The announcement marks a major victory for advocates who have spent decades pushing to allow Medicare to leverage its purchasing power against pharmaceutical companies."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Biden Drug Price Controls Could Slash Drug Innovation, Industry Warns",
        "url": "https://foxnews.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-14",
        "author": "Robert Chase",
        "text": """By Robert Chase

The Biden administration's government drug price controls will ultimately harm American patients by discouraging pharmaceutical companies from investing in the development of new, life-saving medications, industry executives and Republican lawmakers warned Tuesday. While the White House claimed significant savings on a limited set of drugs, critics said the policy sets a dangerous precedent of government interference in the free market that could cost the US its global leadership in medical innovation. Pharmaceutical companies have announced reduced research budgets and scaled-back clinical trials in anticipation of the controls."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. Announces First Medicare Drug Price Deals, Savings Vary",
        "url": "https://reuters.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-14",
        "text": """The Biden administration announced Tuesday the results of Medicare's first-ever drug price negotiations, with discounts ranging from 38% to 79% on 10 medications. The Centers for Medicare and Medicaid Services said the negotiated prices will take effect in 2026. Pharmaceutical companies have challenged the negotiations in court, arguing they amount to unconstitutional government seizure of private property. The administration said the savings represent just the beginning and that more drugs will be added to future negotiation rounds."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "Medicare Announces Drug Price Deals: What Patients Can Expect",
        "url": "https://apnews.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-14",
        "text": """Medicare has reached its first negotiated drug prices under a law passed two years ago, with 10 medications seeing price reductions that will benefit millions of seniors. Here's what Medicare beneficiaries need to know: The new prices apply only to Medicare Part D drug coverage; prices are negotiated with individual manufacturers; the changes take effect January 2026; and patients must still pay deductibles and copayments. Analysts say the negotiations represent a modest but meaningful first step toward controlling prescription costs that have long been higher in the U.S. than in other countries."""
    },
    {
        "source": "The Guardian", "domain": "theguardian.com",
        "title": "America's Drug Pricing Reckoning Has Finally Begun",
        "url": "https://theguardian.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-15",
        "text": """The United States has finally crossed a threshold that advocates once thought unthinkable: the federal government negotiating drug prices with pharmaceutical companies. Tuesday's announcement is a landmark, even if the scope is limited. For too long, Americans have paid two to three times more for the same medications sold in Europe and Canada, a disparity that has forced millions of people to ration life-saving drugs or skip them entirely. The pharmaceutical industry's political power has long blocked reform, making this week's announcement all the more significant."""
    },
    {
        "source": "The Washington Post", "domain": "washingtonpost.com",
        "title": "Drug Price Negotiations Signal Shift in U.S. Healthcare Policy",
        "url": "https://washingtonpost.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-15",
        "text": """Medicare's first drug price negotiations represent a significant shift in how the federal government approaches pharmaceutical costs, analysts said Wednesday. The savings announced by the administration — averaging 55% across the 10 negotiated drugs — are substantial, though experts note they apply only to a small fraction of the medications covered by Medicare. Healthcare economists say the longer-term impact depends on whether future administrations expand the program and whether the courts ultimately uphold the law's constitutionality."""
    },
    {
        "source": "Breitbart", "domain": "breitbart.com",
        "title": "Socialist Drug Price Controls Will Kill Future Cancer Cures",
        "url": "https://breitbart.com/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-14",
        "text": """Biden's socialist price control scheme targeting the American pharmaceutical industry will directly cause the deaths of future patients by killing the financial incentives that drive medical innovation, conservatives warned Tuesday. The government has no business dictating prices in the free market, and its interference will cause drug companies to abandon research into treatments for rare diseases and cancel development pipelines for the next generation of cancer therapies. The short-term political benefit to Democrats is not worth the devastating long-term cost to patients who will never see the cures that could have saved their lives."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "Medicare Drug Negotiations: Significant Win, But Many Gaps Remain",
        "url": "https://npr.org/sample/drug-prices-2024",
        "section": "health", "published_at": "2024-05-15",
        "text": """Medicare's first drug price negotiations mark a meaningful step toward addressing the high cost of prescription drugs in the United States, health policy experts said, though they cautioned that significant gaps remain. The 10 drugs covered represent a fraction of Medicare spending, and many of the highest-cost medications — particularly newer biologics — are not included in this round. Patient advocates expressed concern that drug companies may respond by launching future drugs at even higher initial prices to offset negotiated discounts. The overall impact on healthcare affordability will take years to assess."""
    },

    # =========================================================================
    # STORY 4: AI / Tech Regulation (August 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Senate AI Safety Bill Passes Committee Despite Tech Industry Pressure",
        "url": "https://nytimes.com/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-20",
        "author": "Michael Chen",
        "text": """By Michael Chen

A sweeping artificial intelligence safety bill cleared a key Senate committee Wednesday over objections from major technology companies, setting up a potential floor vote on landmark AI regulation before the end of the year. The legislation would require companies developing advanced AI models to conduct safety testing and disclose potential risks before deploying their systems to the public. Supporters argue the bill is essential to prevent catastrophic misuse of rapidly advancing AI capabilities. The tech industry has mounted an aggressive lobbying campaign, arguing the regulations would stifle innovation and push AI development offshore."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Government AI Regulation Would Cede Tech Leadership to China",
        "url": "https://foxnews.com/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-20",
        "text": """Heavy-handed government regulation of artificial intelligence would hand America's technological edge to China and other authoritarian competitors who face no such restrictions, Republicans and tech executives warned Wednesday as a Senate committee advanced AI legislation. While China races ahead in AI development with government backing and no safety requirements, Democrats are pushing rules that would slow American innovation and force US companies to compete with one hand tied behind their backs. The bill's liability provisions could effectively prevent smaller AI startups from competing with established tech giants."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "Senate Committee Advances AI Safety Legislation",
        "url": "https://reuters.com/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-20",
        "text": """A U.S. Senate committee on Wednesday approved legislation that would establish safety requirements for the most powerful artificial intelligence systems, advancing the first major AI-specific regulation through Congress. The bill cleared the committee 12-8, largely along party lines. It would require frontier AI companies to conduct pre-deployment safety evaluations and report results to federal regulators. Industry groups said the bill's definitions are too broad and could capture systems far less powerful than those the legislation intends to govern."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "What the Senate AI Safety Bill Would Actually Do",
        "url": "https://apnews.com/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-21",
        "text": """A Senate committee has advanced a bill to regulate artificial intelligence. Here's what it would require: AI models above a certain computational threshold would need pre-deployment safety testing; companies would have to report safety evaluation results to a new federal AI safety office; and there would be civil liability for harms caused by inadequately tested AI systems. The bill applies only to the largest AI models, exempting smaller systems and academic research. Supporters say it provides minimal reasonable guardrails; opponents say it would slow AI development."""
    },
    {
        "source": "The Washington Post", "domain": "washingtonpost.com",
        "title": "AI Safety Legislation Faces Long Road Despite Committee Win",
        "url": "https://washingtonpost.com/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-21",
        "author": "David Park",
        "text": """By David Park

The Senate AI safety bill's committee passage represents a significant milestone, but the legislation faces steep hurdles before it could become law. Several senators who voted yes in committee have signaled concerns about specific provisions and may not support the bill on the floor. The tech industry's lobbying operation has been one of the most intense Washington has seen in years, with executives making direct appeals to legislators and funding think-tank studies questioning the bill's economic impact. Civil liberties groups have raised concerns about government access to proprietary AI model information."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "Inside the Debate Over How to Regulate Artificial Intelligence",
        "url": "https://npr.org/sample/ai-regulation-2024",
        "section": "technology", "published_at": "2024-08-22",
        "text": """As Congress debates how to regulate artificial intelligence, a wide range of experts disagree on what risks to prioritize, what regulations would help, and whether the US can regulate AI without ceding ground to less regulated competitors. AI safety researchers say the risks from the most powerful AI systems justify mandatory testing requirements. Industry representatives argue voluntary standards and industry self-governance are more appropriate and flexible. Civil society groups warn that AI regulations focused on catastrophic risks could distract from more immediate harms like algorithmic discrimination and privacy violations."""
    },

    # =========================================================================
    # STORY 5: Gun Control Legislation (October 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "House Passes Expanded Background Check Bill in Narrow Vote",
        "url": "https://nytimes.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-10",
        "author": "Lisa Martinez",
        "text": """By Lisa Martinez

The House of Representatives passed legislation Wednesday that would close loopholes in the federal background check system for gun purchases, requiring checks for sales at gun shows and through online marketplaces. The bill passed 220-210, with eight Republicans joining all Democrats in support. Advocates for gun safety called the vote a long-overdue step to ensure that the same rules that apply to licensed dealers apply everywhere guns change hands. The legislation now moves to the Senate, where its prospects are uncertain given the 60-vote threshold needed to overcome a filibuster."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Democrats' Gun Bill Would Create National Firearms Registry, Critics Warn",
        "url": "https://foxnews.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-10",
        "text": """The Democrats' so-called universal background check bill would effectively create a national firearms registry and burden law-abiding gun owners while doing nothing to stop criminals who already obtain weapons illegally, Second Amendment advocates and Republican lawmakers charged Wednesday. The bill, which passed with minimal Republican support, would expand background checks to private sales between individuals and impose new record-keeping requirements that gun rights groups say constitute a de facto registration scheme prohibited by federal law. The NRA vowed to fight the bill in the Senate."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. House Passes Gun Background Check Expansion Bill",
        "url": "https://reuters.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-10",
        "text": """The U.S. House of Representatives passed a bill on Wednesday that would expand federal background check requirements to cover gun show and online sales, where current law allows private transactions without checks. The vote was 220-210, with the legislation advancing largely along party lines. The bill would require sellers at gun shows to conduct FBI background checks before completing sales, closing what gun control advocates call the gun show loophole. Second Amendment groups and most Republicans opposed the measure, arguing it would infringe on constitutional rights without reducing gun violence."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "House Background Check Bill: What Changes and What Doesn't",
        "url": "https://apnews.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-10",
        "text": """The House passed a bill Wednesday to expand background checks for gun purchases. Currently, federal law requires background checks only for sales by licensed dealers. The new bill would extend this requirement to gun shows and online marketplaces. Private transactions between individuals — such as selling a gun to a neighbor — would still not require background checks under the legislation. Gun control researchers say closing the gun show loophole could prevent some sales to prohibited buyers; gun rights advocates say most criminals already circumvent background checks by other means."""
    },
    {
        "source": "The Guardian", "domain": "theguardian.com",
        "title": "Gun Bill Passes House But America's Gun Violence Crisis Demands More",
        "url": "https://theguardian.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-11",
        "text": """Wednesday's House passage of the background check expansion bill is a step in the right direction, but gun violence researchers warn it falls far short of what is needed to address an epidemic that kills over 45,000 Americans annually. The United States has more guns per capita than any other country and a gun death rate significantly higher than peer nations. The bill does not address assault-style weapons, high-capacity magazines, or safe storage requirements. Gun violence survivors groups, while welcoming the vote, called it a floor rather than a ceiling for what Congress must do."""
    },
    {
        "source": "Breitbart", "domain": "breitbart.com",
        "title": "Democrats' Tyrannical Gun Grab Passes House, Faces Senate Firewall",
        "url": "https://breitbart.com/sample/gun-control-2024",
        "section": "politics", "published_at": "2024-10-10",
        "text": """House Democrats rammed through their unconstitutional gun control bill Wednesday, in a brazen attack on the Second Amendment rights of every law-abiding American. The bill, which Republicans overwhelmingly rejected, would pave the way for government tracking of private gun sales and ultimately lead to a national firearms registry that the federal government could use to confiscate weapons from citizens. Fortunately, the bill faces a much higher bar in the Senate, where Republicans have the votes to stop this freedom-destroying legislation from reaching the president's desk."""
    },

    # =========================================================================
    # STORY 6: Federal Budget / Spending Showdown (November 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Congress Averts Shutdown With Short-Term Spending Bill",
        "url": "https://nytimes.com/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-22",
        "author": "Kevin Walsh",
        "text": """By Kevin Walsh

Congress passed a short-term funding measure Friday that averts a government shutdown for 90 days, buying time for negotiations on a comprehensive spending package after failing to reach agreement on a full-year budget. The continuing resolution passed 234-198 in the House and 56-44 in the Senate, with members from both parties expressing frustration at another stopgap measure. Conservatives had demanded deeper spending cuts while Democrats insisted on maintaining funding levels for domestic programs. The deal punts the hardest decisions to the new Congress that takes office in January."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "RINO Sellout: Republicans Cave on Spending Cuts, Fund Biden's Agenda",
        "url": "https://foxnews.com/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-22",
        "text": """Establishment Republicans betrayed their base Friday by passing a spending bill that funds Joe Biden's radical left-wing agenda for another 90 days without extracting a single meaningful concession on border security or the soaring national debt. Conservative lawmakers who have been demanding real spending reductions blasted the deal as a complete capitulation to Democrat demands. The national debt now stands at $35 trillion, and Congress is once again kicking the can down the road instead of making the hard choices American families have to make every day. Fiscal conservatives say this is exactly why voters don't trust Washington."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. Congress Passes Stopgap Funding Bill, Averts Shutdown",
        "url": "https://reuters.com/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-22",
        "text": """The U.S. Congress on Friday passed a 90-day continuing resolution to keep the federal government funded and avoid a shutdown that would have affected hundreds of thousands of federal workers. The vote came after weeks of failed negotiations on a comprehensive spending package. The stopgap measure maintains current funding levels with few modifications and includes supplemental disaster relief funding. Congressional leaders indicated that resolving the full-year budget impasse would be left to the incoming Congress and new administration in January."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "Shutdown Averted: Congress Passes Stopgap Spending Bill",
        "url": "https://apnews.com/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-22",
        "text": """Congress passed a temporary spending bill Friday to keep the federal government open through late February, avoiding a shutdown that would have halted federal services and furloughed hundreds of thousands of workers. The continuing resolution maintains funding at current levels. Without the bill, the government would have shut down Saturday at midnight. The vote came after House and Senate leaders abandoned efforts to pass a full-year appropriations package after disagreements over spending levels, border security funding, and policy riders. Lawmakers will face the same choices in early 2025."""
    },
    {
        "source": "The Washington Post", "domain": "washingtonpost.com",
        "title": "Another Stopgap, Another Punt: Washington's Budget Dysfunction Continues",
        "url": "https://washingtonpost.com/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-23",
        "text": """Friday's passage of another short-term spending measure continues a pattern of congressional dysfunction that budget experts say is increasingly costly and damaging to the federal government's ability to plan and operate effectively. Agencies operating under continuing resolutions cannot start new programs or adjust spending to changing circumstances. Defense officials say the inability to pass full-year budgets hampers military readiness. Domestic agencies report administrative costs of managing funding uncertainty. Both parties point blame at each other, but budget analysts note that Congress has passed on-time, full-year budgets only four times in the past 45 years."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "What Shutdown Avoidance Means — And What It Doesn't Solve",
        "url": "https://npr.org/sample/budget-2024",
        "section": "politics", "published_at": "2024-11-23",
        "text": """Congress's last-minute passage of a stopgap spending bill averts the immediate crisis of a government shutdown, but leaves the underlying fiscal disagreements unresolved. Budget analysts say the 90-day extension means the new Congress and administration will inherit a fractured budget process on top of a crowded legislative calendar. The federal government has been running significant deficits, and the national debt continues to grow, though economists disagree on the urgency of addressing it. Social safety net programs remain funded at current levels, but long-term pressures on Social Security and Medicare remain unaddressed."""
    },

    # =========================================================================
    # STORY 7: Supreme Court Decision — Presidential Immunity (December 2024)
    # =========================================================================
    {
        "source": "The New York Times", "domain": "nytimes.com",
        "title": "Supreme Court's Immunity Ruling Draws Fierce Criticism from Legal Scholars",
        "url": "https://nytimes.com/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-03",
        "author": "Rachel Kim",
        "text": """By Rachel Kim

Constitutional law scholars reacted with alarm Tuesday to the Supreme Court's ruling that former presidents enjoy broad immunity from criminal prosecution for official acts, with many calling the decision the most consequential expansion of executive power in the court's history. The 6-3 ruling along ideological lines effectively delays criminal trials stemming from the 2020 election until courts determine which alleged acts were official and which were private. Critics said the majority had invented a doctrine with no basis in the Constitution's text or the founders' understanding of limited government."""
    },
    {
        "source": "Fox News", "domain": "foxnews.com",
        "title": "Supreme Court Protects Presidents From Politically Motivated Prosecutions",
        "url": "https://foxnews.com/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-03",
        "text": """The Supreme Court wisely ruled Tuesday that American presidents cannot be dragged into criminal court for the exercise of their official duties, protecting the executive branch from the weaponization of the justice system by political opponents. The landmark ruling, hailed by conservatives as a necessary safeguard for presidential authority, recognizes that presidents must be able to make difficult decisions without fear that their political enemies will prosecute them after leaving office. The left's hysterical reaction reveals their true goal: using the courts to destroy Donald Trump and anyone who supports America First policies."""
    },
    {
        "source": "Reuters", "domain": "reuters.com",
        "title": "U.S. Supreme Court Rules Ex-Presidents Have Immunity for Official Acts",
        "url": "https://reuters.com/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-03",
        "text": """The U.S. Supreme Court ruled Tuesday that former presidents have immunity from criminal prosecution for official actions taken while in office, a landmark decision that narrows the scope of federal criminal cases involving former President Donald Trump. The 6-3 ruling written by Chief Justice John Roberts distinguishes between official presidential acts, which are immune from prosecution, and unofficial acts, which are not. The court sent cases back to lower courts to determine which alleged acts fall into which category, a process that legal experts said could take months or years."""
    },
    {
        "source": "AP News", "domain": "apnews.com",
        "title": "Supreme Court Rules on Presidential Immunity: What It Means",
        "url": "https://apnews.com/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-03",
        "text": """The Supreme Court issued a major ruling Tuesday on presidential immunity. Here's what it means: The court held that presidents are absolutely immune from prosecution for core constitutional powers; that there is presumptive immunity for other official acts; and that private, unofficial conduct has no immunity protection. Lower courts must now sort through what actions in pending cases qualify as official versus unofficial. Legal experts say the distinction is unclear and will require extensive litigation. The ruling does not end any criminal cases but significantly complicates the timeline for any trials."""
    },
    {
        "source": "The Guardian", "domain": "theguardian.com",
        "title": "America's Highest Court Has Placed the President Above the Law",
        "url": "https://theguardian.com/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-04",
        "text": """The Supreme Court's immunity ruling has created what legal scholars are calling a king-in-all-but-name: a president who can take virtually any official action without fear of criminal accountability. Tuesday's decision, written by a conservative supermajority that includes three justices appointed by the same former president who benefits from the ruling, has drawn comparisons to the court's most criticized decisions in history. The ruling inverts the principle that no one is above the law and potentially immunizes future presidents for abuses of power that the founders explicitly intended criminal law to deter."""
    },
    {
        "source": "NPR", "domain": "npr.org",
        "title": "The Presidential Immunity Ruling: Big Questions Left Unanswered",
        "url": "https://npr.org/sample/scotus-immunity-2024",
        "section": "politics", "published_at": "2024-12-04",
        "text": """The Supreme Court's presidential immunity ruling settles one question — that former presidents have some immunity for official acts — while generating many more. Legal scholars are debating what counts as an official act, how courts will evaluate evidence about motives when immunity is claimed, and whether the decision creates incentives for future presidents to use official channels for misconduct. The dissenting justices wrote that the ruling will make it harder to prosecute clear abuses of power. The majority said the rule is necessary to ensure presidents can govern without second-guessing from prosecutors."""
    },
]

async def ingest_embedded_sample(limit: int = 50):
    """
    Ingest hard-coded sample articles for demo/testing purposes.
    Covers 7 major news stories across multiple outlets and dates (Jan–Dec 2024).
    Includes author extraction from bylines in article text.
    """
    print("[Sample] Using embedded sample data")

    async with AsyncSession_() as db:
        ingested = 0
        for sample in SAMPLE_ARTICLES[:limit]:
            try:
                existing = await db.execute(select(Article).where(Article.url == sample["url"]))
                if existing.scalar_one_or_none():
                    continue

                source_id = await get_or_create_source(db, sample["domain"], sample["source"])
                pub_date = datetime.strptime(sample["published_at"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

                # Author: use explicit key if provided, otherwise try to extract from text
                raw_author = sample.get("author") or extract_author_from_text(sample.get("text", ""))
                author_id = None
                if raw_author:
                    for i, name in enumerate(split_author_names(raw_author)):
                        aid = await get_or_create_author(db, name, source_id)
                        if i == 0:
                            author_id = aid  # primary author on the article

                text = sample.get("text", "")
                article = Article(
                    source_id=source_id,
                    author_id=author_id,
                    url=sample["url"],
                    title=sample["title"],
                    published_at=pub_date,
                    section=sample["section"],
                    raw_text=text,
                    word_count=len(text.split()),
                    tags=[sample["section"]],
                )
                db.add(article)
                await db.commit()
                ingested += 1
            except Exception as e:
                print(f"[Sample] Error ingesting '{sample.get('title', '?')}': {e}")
                await db.rollback()

    print(f"[Sample] Ingested {ingested} sample articles ({len(SAMPLE_ARTICLES)} total defined)")
