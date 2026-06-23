#!/usr/bin/env python3
"""Convert Substack export to Jekyll posts, skipping duplicates."""

import csv
import os
import re
from datetime import datetime
from difflib import SequenceMatcher

SUBSTACK_DIR = os.path.expanduser("~/Downloads/m9ymFXbFRYm_jd4cvOGnqA")
POSTS_CSV = os.path.join(SUBSTACK_DIR, "posts.csv")
POSTS_HTML_DIR = os.path.join(SUBSTACK_DIR, "posts")
JEKYLL_POSTS_DIR = os.path.expanduser("~/Documents/andrewlynch.net/_posts")

# Import the HTML converter from the original script
import sys
sys.path.insert(0, os.path.expanduser("~/Documents/andrewlynch.net"))
from convert_posts import HTMLToMarkdown, html_to_markdown


def get_existing_posts():
    """Read existing Jekyll posts and return slug->content mapping."""
    posts = {}
    for filename in os.listdir(JEKYLL_POSTS_DIR):
        if not filename.endswith(".markdown"):
            continue
        filepath = os.path.join(JEKYLL_POSTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Extract slug from permalink in front matter
        slug_match = re.search(r"permalink:\s*/blog/(.+)", content)
        slug = slug_match.group(1).strip() if slug_match else ""
        # Extract title
        title_match = re.search(r'title:\s*"(.+)"', content)
        title = title_match.group(1).strip() if title_match else ""
        # Get body text (after front matter)
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) > 2 else ""
        posts[filename] = {
            "slug": slug,
            "title": title,
            "body_start": body[:500],
            "filepath": filepath,
        }
    return posts


def normalize(text):
    """Normalize text for comparison."""
    text = re.sub(r"[^a-z0-9\s]", "", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_duplicate(substack_title, substack_body_start, existing_posts):
    """Check if a Substack post already exists in Jekyll."""
    sub_title_norm = normalize(substack_title)
    sub_body_norm = normalize(substack_body_start)

    for fname, post in existing_posts.items():
        # Exact slug match
        # (not reliable alone since slugs differ between platforms)

        # Fuzzy title match
        existing_title_norm = normalize(post["title"])
        title_ratio = SequenceMatcher(None, sub_title_norm, existing_title_norm).ratio()
        if title_ratio > 0.8:
            return True, post["title"], "title match ({:.0%})".format(title_ratio)

        # Content similarity (first 300 chars of body)
        if sub_body_norm and post["body_start"]:
            existing_body_norm = normalize(post["body_start"])
            body_ratio = SequenceMatcher(
                None, sub_body_norm[:300], existing_body_norm[:300]
            ).ratio()
            if body_ratio > 0.7:
                return True, post["title"], "content match ({:.0%})".format(body_ratio)

    return False, None, None


def strip_substack_widgets(html):
    """Remove Substack subscribe widgets and buttons from HTML."""
    html = re.sub(
        r'<div class="subscription-widget-wrap-editor".*?</div>\s*</div>\s*</div>',
        "",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<p class="button-wrapper".*?</p>', "", html, flags=re.DOTALL
    )
    # Remove trailing "appeared first on AndrewLynch.net" lines
    html = re.sub(
        r"<p>The post.*?appeared first on.*?</p>", "", html, flags=re.DOTALL
    )
    return html


def convert_substack_posts():
    existing = get_existing_posts()
    print(f"Found {len(existing)} existing Jekyll posts")

    # Read Substack posts CSV
    with open(POSTS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        substack_posts = list(reader)

    print(f"Found {len(substack_posts)} Substack posts in CSV")

    new_count = 0
    skip_count = 0
    draft_count = 0
    empty_count = 0
    duplicates = []

    for post in substack_posts:
        title = post.get("title", "").strip()
        slug_part = post.get("post_id", "").split(".")[-1] if "." in post.get("post_id", "") else ""
        post_id_full = post.get("post_id", "")

        # Extract slug from post_id (format: "12345.slug-here")
        parts = post_id_full.split(".", 1)
        post_id = parts[0]
        slug = parts[1] if len(parts) > 1 else ""

        is_published = post.get("is_published", "").lower() == "true"
        post_date = post.get("post_date", "")

        if not is_published:
            draft_count += 1
            continue

        if not title:
            empty_count += 1
            continue

        # Find the HTML file
        html_file = None
        for f in os.listdir(POSTS_HTML_DIR):
            if f.startswith(post_id + ".") and f.endswith(".html"):
                html_file = os.path.join(POSTS_HTML_DIR, f)
                break

        if not html_file or not os.path.exists(html_file):
            print(f"  WARNING: No HTML file found for '{title}' (id: {post_id})")
            continue

        with open(html_file, "r", encoding="utf-8") as hf:
            html_content = hf.read()

        if not html_content.strip():
            empty_count += 1
            continue

        # Clean up Substack-specific widgets
        html_content = strip_substack_widgets(html_content)

        # Convert to markdown
        body_md = html_to_markdown(html_content)

        if not body_md.strip():
            empty_count += 1
            continue

        # Check for duplicates
        is_dup, match_title, match_reason = is_duplicate(
            title, body_md[:500], existing
        )

        if is_dup:
            duplicates.append((title, match_title, match_reason))
            skip_count += 1
            continue

        # Parse date
        try:
            dt = datetime.fromisoformat(post_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            date_str = "2020-01-01"

        # Build front matter
        escaped_title = title.replace('"', '\\"')
        subtitle = post.get("subtitle", "").strip()
        front_matter = f"""---
layout: post
title: "{escaped_title}"
date: {date_str}
permalink: /blog/{slug}
"""
        if subtitle:
            escaped_sub = subtitle.replace('"', '\\"')
            front_matter += f'description: "{escaped_sub}"\n'
        front_matter += "---\n"

        # Write the file
        filename = f"{date_str}-{slug}.markdown"
        filepath = os.path.join(JEKYLL_POSTS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as pf:
            pf.write(front_matter)
            pf.write("\n")
            pf.write(body_md)
            pf.write("\n")

        new_count += 1
        print(f"  NEW: {title} -> {filename}")

    print(f"\n--- Summary ---")
    print(f"New posts created: {new_count}")
    print(f"Duplicates skipped: {skip_count}")
    print(f"Drafts skipped: {draft_count}")
    print(f"Empty/no-content skipped: {empty_count}")

    if duplicates:
        print(f"\n--- Duplicate matches ---")
        for sub_title, jekyll_title, reason in duplicates:
            print(f"  '{sub_title}' matched '{jekyll_title}' ({reason})")


if __name__ == "__main__":
    convert_substack_posts()
