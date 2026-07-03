from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Dict, List

from timestamp_parser import parse_timestamp


JUNK_HEADLINE_MARKERS = (
    ".css-",
    "@media",
    "schema.org",
    "imageobject",
    "inline-size",
    "block-size",
    "aspect-ratio",
    "display:",
    "background:",
    "object-fit:",
    "{",
    "}",
)


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_a = False
        self.href = ""
        self.text = ""
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.in_a = True
            self.href = dict(attrs).get("href", "")
            self.text = ""

    def handle_data(self, data):
        if self.in_a:
            self.text += data

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.in_a:
            text = clean_text(self.text)
            if is_probable_headline(text):
                self.items.append({"headline": text, "url": self.href})
            self.in_a = False


def fetch_source(source: Dict, timeout: int = 15, user_agent: str = "BlueLotus3-NewsReporter/1.0") -> Dict:
    url = source["url"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/rss+xml,application/xml,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(900_000).decode("utf-8", "ignore")
            content_type = resp.headers.get("content-type", "")
        events = parse_feed_or_html(body, url, source)
        return {"source": source["id"], "status": "OK", "events": events, "content_type": content_type}
    except Exception as exc:
        return {"source": source["id"], "status": "ERROR", "events": [], "error": str(exc)[:240]}


def parse_feed_or_html(body: str, base_url: str, source: Dict) -> List[Dict]:
    stripped = body.lstrip()
    if stripped.startswith("<?xml") or "<rss" in stripped[:400].lower() or "<feed" in stripped[:400].lower():
        return parse_xml_feed(body, source)
    return parse_html_page(body, base_url, source)


def parse_xml_feed(body: str, source: Dict) -> List[Dict]:
    out = []
    try:
        root = ET.fromstring(body)
    except Exception:
        return out
    for item in root.findall(".//item")[:30]:
        title = text_of(item, "title")
        link = text_of(item, "link")
        summary = text_of(item, "description")
        published_raw = text_of(item, "pubDate") or text_of(item, "published") or text_of(item, "updated")
        if title:
            out.append(make_event(source, title, link, summary, published_raw))
    ns_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in ns_items[:30]:
        title = text_of(item, "{http://www.w3.org/2005/Atom}title")
        link_el = item.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        summary = text_of(item, "{http://www.w3.org/2005/Atom}summary")
        published_raw = text_of(item, "{http://www.w3.org/2005/Atom}published") or text_of(item, "{http://www.w3.org/2005/Atom}updated")
        if title:
            out.append(make_event(source, title, link, summary, published_raw))
    return out


def parse_html_page(body: str, base_url: str, source: Dict) -> List[Dict]:
    scmp_cards = parse_scmp_live_cards(body, base_url, source)
    if scmp_cards:
        return dedupe_events(scmp_cards)[:40]

    structured = parse_json_ld_articles(body, base_url, source)
    if structured:
        return dedupe_events(structured)[:40]

    parser = AnchorParser()
    try:
        parser.feed(body)
    except Exception:
        pass
    out = []
    for item in parser.items[:40]:
        headline = item["headline"]
        url = absolutize(base_url, item.get("url", ""))
        out.append(make_event(source, headline, url, "", ""))
    return dedupe_events(out)


def parse_scmp_live_cards(body: str, base_url: str, source: Dict) -> List[Dict]:
    if source.get("id") != "SCMP" and "ContentItemLivePrimary" not in body:
        return []
    out = []
    blocks = re.findall(
        r'<div[^>]+data-qa="ContentItemLivePrimary-Container"[^>]*>(.*?)(?=<div[^>]+data-qa="ContentItemLivePrimary-Container"|</body>|$)',
        body,
        flags=re.I | re.S,
    )
    for block in blocks:
        headline_match = re.search(
            r'data-qa="ContentHeadline-Headline"[^>]*>(.*?)</span>',
            block,
            flags=re.I | re.S,
        )
        if not headline_match:
            continue
        headline = clean_text(strip_tags(headline_match.group(1)))
        if not is_probable_headline(headline):
            continue

        url_match = re.search(r'href="([^"]*/article/[^"]+)"', block, flags=re.I)
        summary_match = re.search(
            r'data-qa="ContentSummary-ContainerWithTag"[^>]*>(.*?)</h3>',
            block,
            flags=re.I | re.S,
        )
        time_match = re.search(
            r'<time[^>]+(?:dateTime|datetime)="([^"]+)"[^>]*>(.*?)</time>',
            block,
            flags=re.I | re.S,
        )
        if not time_match:
            time_match = re.search(r'<time[^>]*>(.*?)</time>', block, flags=re.I | re.S)

        url = absolutize(base_url, html.unescape(url_match.group(1))) if url_match else base_url
        summary = clean_text(strip_tags(summary_match.group(1))) if summary_match else ""
        published_raw = ""
        if time_match:
            published_raw = time_match.group(1) if time_match.lastindex and time_match.lastindex >= 1 else ""
            if time_match.lastindex and time_match.lastindex >= 2 and not published_raw:
                published_raw = strip_tags(time_match.group(2))
        out.append(make_event(source, headline, url, summary, published_raw))
    return out


def parse_json_ld_articles(body: str, base_url: str, source: Dict) -> List[Dict]:
    out = []
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        body,
        flags=re.I | re.S,
    )
    for script in scripts:
        raw = html.unescape(script).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for node in walk_json(data):
            node_type = node.get("@type") or node.get("type")
            if isinstance(node_type, list):
                types = {str(x).lower() for x in node_type}
            else:
                types = {str(node_type).lower()}
            if not (types & {"newsarticle", "article", "reportagenewsarticle"}):
                continue
            headline = clean_text(str(node.get("headline") or node.get("name") or ""))
            if not is_probable_headline(headline):
                continue
            url = value_url(node.get("url") or node.get("mainEntityOfPage") or "")
            summary = clean_text(str(node.get("description") or ""))
            published_raw = str(node.get("datePublished") or node.get("dateModified") or "")
            out.append(make_event(source, headline, absolutize(base_url, url), summary, published_raw))
    return out


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def value_url(value) -> str:
    if isinstance(value, dict):
        return str(value.get("@id") or value.get("url") or "")
    return str(value or "")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def is_probable_headline(text: str) -> bool:
    if not 24 <= len(text) <= 220:
        return False
    low = text.lower()
    if any(marker in low for marker in JUNK_HEADLINE_MARKERS):
        return False
    if urllib.parse.urlparse(text).scheme in {"http", "https"}:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    if len(words) < 4:
        return False
    return True


def dedupe_events(events: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for event in events:
        key = (event.get("headline") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(event)
    return out


def make_event(source: Dict, headline: str, url: str, summary: str, published_raw: str) -> Dict:
    published_utc, parse_status = parse_timestamp(published_raw)
    return {
        "source": source["label"],
        "source_id": source["id"],
        "headline": clean_text(headline),
        "url": url or source["url"],
        "summary": clean_text(summary)[:280],
        "published_at_raw": published_raw,
        "published_at_utc": published_utc.isoformat() if published_utc else None,
        "timestamp_parse_status": parse_status,
    }


def text_of(item, name: str) -> str:
    el = item.find(name)
    return "".join(el.itertext()).strip() if el is not None else ""


def absolutize(base: str, url: str) -> str:
    if not url:
        return base
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        m = re.match(r"https?://[^/]+", base)
        return (m.group(0) if m else base).rstrip("/") + url
    return url
