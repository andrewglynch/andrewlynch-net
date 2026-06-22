#!/usr/bin/env python3
"""Convert Webflow blog CSV export to Jekyll markdown posts."""

import csv
import os
import re
from html.parser import HTMLParser
from datetime import datetime
from urllib.parse import unquote

CSV_PATH = os.path.expanduser(
    "~/Downloads/AndrewLynch.net - All Blog Posts - 5f9b3cf6e87a1e5e0a099e3f.csv"
)
POSTS_DIR = os.path.join(os.path.dirname(__file__), "_posts")
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "assets", "images")
MISSING_IMAGES_LOG = os.path.join(os.path.dirname(__file__), "missing_images.md")


class HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.current_tag = None
        self.tag_stack = []
        self.list_type_stack = []
        self.in_blockquote = False
        self.in_embed = False
        self.link_href = None
        self.skip_content = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.tag_stack.append(tag)
        self.current_tag = tag

        if tag == "div" and attrs_dict.get("data-rt-embed-type") == "true":
            self.in_embed = True
            return

        if self.in_embed and tag in ("blockquote", "script"):
            if tag == "blockquote" and "instagram-media" in attrs_dict.get("class", ""):
                permalink = attrs_dict.get("data-instgrm-permalink", "")
                if permalink:
                    self.result.append(f"\n\n{{% include instagram.html url=\"{permalink}\" %}}\n\n")
            self.skip_content = True
            return

        if self.skip_content:
            return

        if tag == "p":
            self.result.append("\n\n")
        elif tag == "br":
            self.result.append("\n")
        elif tag in ("strong", "b"):
            self.result.append("**")
        elif tag in ("em", "i"):
            self.result.append("*")
        elif tag == "a":
            self.link_href = attrs_dict.get("href", "")
            self.result.append("[")
        elif tag == "h1":
            self.result.append("\n\n# ")
        elif tag == "h2":
            self.result.append("\n\n## ")
        elif tag == "h3":
            self.result.append("\n\n### ")
        elif tag == "h4":
            self.result.append("\n\n#### ")
        elif tag == "blockquote":
            self.in_blockquote = True
            self.result.append("\n\n> ")
        elif tag == "ul":
            self.list_type_stack.append("ul")
            self.result.append("\n")
        elif tag == "ol":
            self.list_type_stack.append("ol")
            self.result.append("\n")
            self._ol_counter = 0
        elif tag == "li":
            if self.list_type_stack and self.list_type_stack[-1] == "ol":
                self._ol_counter = getattr(self, "_ol_counter", 0) + 1
                self.result.append(f"\n{self._ol_counter}. ")
            else:
                self.result.append("\n- ")
        elif tag == "img":
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "")
            if src:
                local = self._map_image_url(src)
                self.result.append(f"\n\n![{alt}]({local})\n\n")
        elif tag == "figure":
            pass
        elif tag == "figcaption":
            self.result.append("\n*")
        elif tag == "hr":
            self.result.append("\n\n---\n\n")

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

        if tag == "div" and self.in_embed:
            if not any(t == "div" and True for t in self.tag_stack if t == "div"):
                self.in_embed = False
                self.skip_content = False
            return

        if tag == "script" and self.in_embed:
            self.skip_content = False
            return

        if self.skip_content:
            return

        if tag in ("strong", "b"):
            self.result.append("**")
        elif tag in ("em", "i"):
            self.result.append("*")
        elif tag == "a":
            if self.link_href:
                self.result.append(f"]({self.link_href})")
            else:
                self.result.append("]()")
            self.link_href = None
        elif tag == "blockquote":
            self.in_blockquote = False
            self.result.append("\n\n")
        elif tag in ("ul", "ol"):
            if self.list_type_stack:
                self.list_type_stack.pop()
            self.result.append("\n")
        elif tag == "figcaption":
            self.result.append("*\n")
        elif tag in ("h1", "h2", "h3", "h4"):
            self.result.append("\n")
        elif tag == "p":
            pass

        self.current_tag = self.tag_stack[-1] if self.tag_stack else None

    def handle_data(self, data):
        if self.skip_content:
            return
        text = data
        if self.in_blockquote:
            text = text.replace("\n", "\n> ")
        # Collapse non-breaking spaces
        text = text.replace("​", "").replace(" ", " ").replace(" ", "\n")
        self.result.append(text)

    def handle_entityref(self, name):
        if self.skip_content:
            return
        entities = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "nbsp": " "}
        self.result.append(entities.get(name, f"&{name};"))

    def handle_charref(self, name):
        if self.skip_content:
            return
        try:
            if name.startswith("x"):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self.result.append(char)
        except (ValueError, OverflowError):
            self.result.append(f"&#{name};")

    def get_markdown(self):
        md = "".join(self.result)
        # Clean up excessive whitespace
        md = re.sub(r"\n{3,}", "\n\n", md)
        md = re.sub(r"[ \t]+\n", "\n", md)
        md = md.strip()
        return md

    def _map_image_url(self, url):
        """Map an original image URL to a local path."""
        images = os.listdir(IMAGES_DIR)

        # Try exact filename match from Webflow URL
        if "uploads-ssl.webflow.com" in url or "website-assets.com" in url:
            filename = url.split("/")[-1]
            filename = unquote(unquote(filename))
            for img in images:
                if img == filename or unquote(unquote(img)) == filename:
                    return f"/assets/images/{img}"

        # Try Substack URL match
        if "substackcdn.com" in url or "substack-post-media" in url or "bucketeer-" in url:
            # Extract the UUID from the URL
            uuid_match = re.search(
                r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                url,
            )
            if uuid_match:
                uuid = uuid_match.group(1)
                for img in images:
                    if uuid in img:
                        return f"/assets/images/{img}"

        # Fallback: search by any recognizable part of the filename
        for part in url.split("/")[-1:]:
            clean = unquote(unquote(part)).split("?")[0]
            for img in images:
                if clean in img or img in clean:
                    return f"/assets/images/{img}"

        return url


def parse_date(date_str):
    """Parse Webflow date string to Jekyll date."""
    if not date_str:
        return datetime(2020, 1, 1)
    try:
        # "Mon Nov 05 2018 00:00:00 GMT+0000 (Coordinated Universal Time)"
        clean = re.sub(r"\s*\(.*\)\s*$", "", date_str).strip()
        clean = re.sub(r"\s*GMT[+-]\d{4}\s*$", "", clean).strip()
        return datetime.strptime(clean, "%a %b %d %Y %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(date_str[:24], "%a %b %d %Y %H:%M:%S")
        except ValueError:
            return datetime(2020, 1, 1)


def html_to_markdown(html):
    """Convert HTML to Markdown."""
    parser = HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


def convert_posts():
    os.makedirs(POSTS_DIR, exist_ok=True)

    missing_images = []
    post_count = 0

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            slug = row.get("Slug", "").strip()
            body_html = row.get("Post Body", "")
            summary = row.get("Post Summary", "").strip()
            categories = row.get("Categories", "").strip()
            published_date = row.get("Published date", "") or row.get("Published On", "")
            reading_time = row.get("Reading time", "").strip()
            is_draft = row.get("Draft", "false").lower() == "true"
            featured = row.get("Featured?", "false").lower() == "true"
            main_image = row.get("Main Image", "").strip()
            thumbnail = row.get("Thumbnail image", "").strip()

            if not name or not slug:
                continue

            date = parse_date(published_date)
            date_str = date.strftime("%Y-%m-%d")

            # Convert body
            body_md = html_to_markdown(body_html)

            # Check for missing images in the body
            for img_match in re.finditer(r"!\[.*?\]\((https?://[^)]+)\)", body_md):
                img_url = img_match.group(1)
                missing_images.append({"post": name, "slug": slug, "url": img_url})

            # Build tags from categories
            tags = [c.strip() for c in categories.split(";") if c.strip()] if categories else []

            # Map main image
            header_image = ""
            if main_image:
                converter = HTMLToMarkdown()
                mapped = converter._map_image_url(main_image)
                if not mapped.startswith("http"):
                    header_image = mapped

            # Build front matter
            escaped_name = name.replace('"', '\\"')
            front_matter = f"""---
layout: post
title: "{escaped_name}"
date: {date_str}
permalink: /blog/{slug}
"""
            if summary:
                escaped_summary = summary.replace('"', '\\"')
                front_matter += f'description: "{escaped_summary}"\n'
            if tags:
                front_matter += f"tags:\n"
                for tag in tags:
                    front_matter += f"  - {tag}\n"
            if reading_time:
                front_matter += f"reading_time: {reading_time}\n"
            if featured:
                front_matter += "featured: true\n"
            if header_image:
                front_matter += f"image: {header_image}\n"
            front_matter += "---\n"

            filename = f"{date_str}-{slug}.markdown"
            filepath = os.path.join(POSTS_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as pf:
                pf.write(front_matter)
                pf.write("\n")
                pf.write(body_md)
                pf.write("\n")

            post_count += 1

    # Write missing images log
    if missing_images:
        with open(MISSING_IMAGES_LOG, "w") as mf:
            mf.write("# Missing Images\n\n")
            mf.write("These images could not be downloaded and still reference external URLs.\n")
            mf.write("You may need to find replacements manually.\n\n")
            current_post = None
            for item in missing_images:
                if item["post"] != current_post:
                    current_post = item["post"]
                    mf.write(f"\n## {current_post}\n")
                    mf.write(f"Slug: `{item['slug']}`\n\n")
                mf.write(f"- {item['url']}\n")

    print(f"Converted {post_count} posts")
    print(f"Missing images in {len(set(i['post'] for i in missing_images))} posts ({len(missing_images)} total)")


if __name__ == "__main__":
    convert_posts()
