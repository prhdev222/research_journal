"""Small PubMed E-utilities helper for Literature Agent seed context."""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET

import httpx

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def search_pubmed(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Return a compact list of PubMed records for prompt grounding."""
    async with httpx.AsyncClient(timeout=20) as client:
        search = await client.get(
            f"{EUTILS}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": str(limit),
                "sort": "relevance",
            },
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        fetch = await client.get(
            f"{EUTILS}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            },
        )
        fetch.raise_for_status()

    root = ET.fromstring(fetch.text)
    papers: list[dict[str, str]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article, ".//PMID")
        title = html.unescape(_text(article, ".//ArticleTitle"))
        journal = _text(article, ".//Journal/Title")
        year = (
            _text(article, ".//JournalIssue/PubDate/Year")
            or _text(article, ".//JournalIssue/PubDate/MedlineDate")[:4]
        )
        abstract_parts = [
            "".join(part.itertext()).strip()
            for part in article.findall(".//Abstract/AbstractText")
        ]
        abstract = " ".join(part for part in abstract_parts if part)
        authors = []
        for author in article.findall(".//Author")[:6]:
            last = _text(author, "LastName")
            initials = _text(author, "Initials")
            if last:
                authors.append(f"{last} {initials}".strip())
        papers.append(
            {
                "pmid": pmid,
                "title": title,
                "authors": ", ".join(authors),
                "journal": journal,
                "year": year,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "abstract": html.unescape(abstract[:1400]),
            }
        )
    return papers


def format_pubmed_seed(papers: list[dict[str, str]]) -> str:
    if not papers:
        return "No PubMed seed papers found."
    lines = []
    for idx, paper in enumerate(papers, 1):
        lines.append(
            "\n".join(
                [
                    f"{idx}. {paper.get('title', '')}",
                    f"   Authors: {paper.get('authors', '')}",
                    f"   Journal/year: {paper.get('journal', '')}, {paper.get('year', '')}",
                    f"   Link: {paper.get('url', '')}",
                    f"   Abstract: {paper.get('abstract', '')}",
                ]
            )
        )
    return "\n\n".join(lines)


def _text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    if found is None or found.text is None:
        return ""
    return found.text.strip()
