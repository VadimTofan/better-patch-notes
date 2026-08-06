from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from urllib.parse import urlsplit

from automation.models import RegisteredSource, SourceDocument


OFFICIAL_FORUM_GROUPS = {
    "blizzard",
    "community-manager",
    "wow-developer",
}


class UnsupportedSourceShape(ValueError):
    """An official source no longer matches its reviewed structure."""


def _matches_title(title: str, source: RegisteredSource) -> bool:
    normalized_title = title.casefold()

    return any(
        pattern.casefold() in normalized_title
        for pattern in source.title_patterns
    )


def _is_official_blizzard_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")

    return parsed.scheme == "https" and (
        host == "blizzard.com"
        or host.endswith(".blizzard.com")
        or host == "battle.net"
        or host.endswith(".battle.net")
    )


def _parse_iso_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise UnsupportedSourceShape(f"forum topic is missing {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise UnsupportedSourceShape(
            f"forum topic has invalid {field}",
        ) from error
    if parsed.tzinfo is None:
        raise UnsupportedSourceShape(
            f"forum topic {field} must include a timezone",
        )

    return parsed


def discover_news_documents(
    body: bytes,
    source: RegisteredSource,
) -> tuple[SourceDocument, ...]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsupportedSourceShape("news feed is invalid JSON") from error
    if not isinstance(payload, dict):
        raise UnsupportedSourceShape("news feed must be an object")
    feed = payload.get("feed")
    if not isinstance(feed, dict):
        raise UnsupportedSourceShape("news feed is missing its feed object")
    content_items = feed.get("contentItems")
    if not isinstance(content_items, list):
        raise UnsupportedSourceShape("news feed is missing content items")

    documents: list[SourceDocument] = []
    for item in content_items:
        if not isinstance(item, dict):
            raise UnsupportedSourceShape("news feed contains an invalid item")
        properties = item.get("properties")
        if not isinstance(properties, dict):
            raise UnsupportedSourceShape(
                "news feed item is missing properties",
            )

        title_value = properties.get("title")
        title = title_value.strip() if isinstance(title_value, str) else ""
        if not title or not _matches_title(title, source):
            continue

        url_value = properties.get("newsUrl")
        published_value = properties.get("lastUpdated")
        description_value = properties.get("summary")
        author_value = properties.get("author")
        url = url_value.strip() if isinstance(url_value, str) else ""
        published_text = (
            published_value.strip()
            if isinstance(published_value, str)
            else ""
        )
        description = (
            description_value.strip()
            if isinstance(description_value, str)
            else ""
        )
        if not url or not published_text or not description:
            raise UnsupportedSourceShape(
                "news feed item is missing required fields",
            )
        if not _is_official_blizzard_url(url):
            raise UnsupportedSourceShape(
                "news feed item URL is not an official Blizzard URL",
            )
        published_at = _parse_iso_datetime(published_text, "lastUpdated")

        encoded_body = description.encode("utf-8")
        documents.append(
            SourceDocument(
                url=url,
                channel=source.channel,
                patch=source.patch,
                locale=source.locale,
                title=title,
                author=(
                    author_value.strip()
                    if isinstance(author_value, str) and author_value.strip()
                    else "Blizzard Entertainment"
                ),
                published_at=published_at,
                updated_at=None,
                body=encoded_body,
                mime_type="text/html",
                content_hash=sha256(encoded_body).hexdigest(),
                author_is_blue=True,
            )
        )

    return tuple(sorted(documents, key=lambda item: (item.published_at, item.url)))


def discover_forum_topic_urls(
    body: bytes,
    source: RegisteredSource,
) -> tuple[str, ...]:
    try:
        category = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsupportedSourceShape("forum category is invalid JSON") from error
    if not isinstance(category, dict):
        raise UnsupportedSourceShape("forum category must be an object")
    topic_list = category.get("topic_list")
    if not isinstance(topic_list, dict):
        raise UnsupportedSourceShape("forum category is missing topic_list")
    topics = topic_list.get("topics")
    if not isinstance(topics, list):
        raise UnsupportedSourceShape("forum category is missing topics")

    parsed_source = urlsplit(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"
    topic_ids: set[int] = set()
    for topic in topics:
        if not isinstance(topic, dict):
            raise UnsupportedSourceShape(
                "forum category contains an invalid topic",
            )
        topic_id = topic.get("id")
        title = topic.get("title")
        if not isinstance(topic_id, int) or not isinstance(title, str):
            raise UnsupportedSourceShape(
                "forum category topic is missing required fields",
            )
        if not _matches_title(title, source):
            continue
        _parse_iso_datetime(topic.get("created_at"), "created_at")
        _parse_iso_datetime(topic.get("last_posted_at"), "last_posted_at")
        topic_ids.add(topic_id)

    return tuple(
        f"{base_url}/en/wow/t/{topic_id}.json"
        for topic_id in sorted(topic_ids)
    )


def discover_forum_documents(
    body: bytes,
    source: RegisteredSource,
    blue_authors: frozenset[str],
) -> tuple[SourceDocument, ...]:
    try:
        topic = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsupportedSourceShape("forum topic is invalid JSON") from error
    if not isinstance(topic, dict):
        raise UnsupportedSourceShape("forum topic must be an object")

    title = topic.get("title")
    topic_id = topic.get("id")
    slug = topic.get("slug")
    post_stream = topic.get("post_stream")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(topic_id, int)
        or not isinstance(slug, str)
        or not slug.strip()
        or not isinstance(post_stream, dict)
        or not isinstance(post_stream.get("posts"), list)
    ):
        raise UnsupportedSourceShape("forum topic is missing required fields")
    if not _matches_title(title, source):
        return ()

    parsed_source = urlsplit(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"
    documents_by_url: dict[str, SourceDocument] = {}
    for raw_post in post_stream["posts"]:
        if not isinstance(raw_post, dict):
            raise UnsupportedSourceShape("forum topic contains an invalid post")

        username = raw_post.get("username")
        group = raw_post.get("primary_group_name")
        author_is_blue = (
            isinstance(username, str)
            and username in blue_authors
            and isinstance(group, str)
            and group.casefold() in OFFICIAL_FORUM_GROUPS
            and raw_post.get("staff") is True
        )
        if not author_is_blue:
            continue

        post_type = raw_post.get("post_type")
        if not isinstance(post_type, int):
            raise UnsupportedSourceShape(
                "forum topic blue post is missing post_type",
            )
        if post_type != 1:
            continue

        post_number = raw_post.get("post_number")
        cooked = raw_post.get("cooked")
        if (
            not isinstance(post_number, int)
            or post_number < 1
            or not isinstance(cooked, str)
            or not cooked.strip()
        ):
            raise UnsupportedSourceShape(
                "forum topic blue post is missing required fields",
            )

        published_at = _parse_iso_datetime(
            raw_post.get("created_at"),
            "created_at",
        )
        updated_at = _parse_iso_datetime(
            raw_post.get("updated_at"),
            "updated_at",
        )
        url = (
            f"{base_url}/en/wow/t/{slug}/{topic_id}/{post_number}"
        )
        encoded_body = cooked.encode("utf-8")
        documents_by_url[url] = SourceDocument(
            url=url,
            channel=source.channel,
            patch=source.patch,
            locale=source.locale,
            title=title.strip(),
            author=username,
            published_at=published_at,
            updated_at=updated_at,
            body=encoded_body,
            mime_type="text/html",
            content_hash=sha256(encoded_body).hexdigest(),
            author_is_blue=True,
        )

    return tuple(
        sorted(
            documents_by_url.values(),
            key=lambda item: (item.published_at, item.url),
        )
    )
