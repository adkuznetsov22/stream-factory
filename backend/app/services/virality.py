"""
Virality Score Calculator

Calculates a virality score for videos based on:
- Views per day (velocity)
- Engagement rate (likes + comments / views)
- Recency boost (newer content scores higher)

Score range: 0-100
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class VideoLike(Protocol):
    """Protocol for video-like objects with metrics."""
    views: int | None
    likes: int | None
    comments: int | None
    published_at: datetime | None


def calculate_virality_score(
    views: int | None,
    likes: int | None,
    comments: int | None,
    shares: int | None,
    published_at: datetime | None,
    *,
    subscribers: int | None = None,
) -> float:
    """
    Calculate virality score (0-100) for a video.
    
    Formula components:
    1. Views velocity: views / days_since_published (normalized)
    2. Engagement rate: (likes + comments + shares) / views
    3. Recency boost: exponential decay based on age
    4. Subscriber ratio: views / subscribers (if available)
    
    Weights:
    - velocity: 40%
    - engagement: 30%
    - recency: 20%
    - subscriber_ratio: 10%
    """
    if not views or views <= 0:
        return 0.0
    
    now = datetime.now(timezone.utc)
    
    # Days since published (minimum 1 to avoid division by zero)
    days_old = 1.0
    if published_at:
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        delta = now - published_at
        days_old = max(delta.total_seconds() / 86400, 1.0)
    
    # 1. Views velocity (views per day)
    velocity = views / days_old
    # Normalize: 10k views/day = 100 points, logarithmic scale
    velocity_score = min(100, (velocity / 100) ** 0.5 * 10)
    
    # 2. Engagement rate
    engagement_total = (likes or 0) + (comments or 0) + (shares or 0)
    engagement_rate = engagement_total / views if views > 0 else 0
    # Normalize: 10% engagement = 100 points
    engagement_score = min(100, engagement_rate * 1000)
    
    # 3. Recency boost (exponential decay)
    # Videos lose 50% of recency score every 30 days
    decay_rate = 0.023  # ln(2) / 30
    recency_score = 100 * (2.718 ** (-decay_rate * days_old))
    
    # 4. Subscriber ratio (optional)
    sub_ratio_score = 50.0  # default if no subscriber data
    if subscribers and subscribers > 0:
        ratio = views / subscribers
        # 1x subscriber count views = 50 points, 10x = 100 points
        sub_ratio_score = min(100, ratio * 50)
    
    # Weighted average
    weights = {
        "velocity": 0.40,
        "engagement": 0.30,
        "recency": 0.20,
        "sub_ratio": 0.10,
    }
    
    final_score = (
        velocity_score * weights["velocity"]
        + engagement_score * weights["engagement"]
        + recency_score * weights["recency"]
        + sub_ratio_score * weights["sub_ratio"]
    )
    
    return round(min(100, max(0, final_score)), 2)


def calculate_virality_for_youtube(video: Any, subscribers: int | None = None) -> float:
    """Calculate virality score for a YouTubeVideo object."""
    return calculate_virality_score(
        views=video.views,
        likes=video.likes,
        comments=video.comments,
        shares=None,
        published_at=video.published_at,
        subscribers=subscribers,
    )


def calculate_virality_for_tiktok(video: Any, followers: int | None = None) -> float:
    """Calculate virality score for a TikTokVideo object."""
    return calculate_virality_score(
        views=video.views,
        likes=video.likes,
        comments=video.comments,
        shares=getattr(video, "shares", None),
        published_at=video.published_at,
        subscribers=followers,
    )


def calculate_virality_for_vk(video: Any, members: int | None = None) -> float:
    """Calculate virality score for a VKVideo or VKClip object."""
    return calculate_virality_score(
        views=video.views,
        likes=video.likes,
        comments=video.comments,
        shares=getattr(video, "reposts", None),
        published_at=video.published_at,
        subscribers=members,
    )


def calculate_virality_for_instagram(post: Any, followers: int | None = None) -> float:
    """Calculate virality score for an InstagramPost object."""
    return calculate_virality_score(
        views=post.views,
        likes=post.likes,
        comments=post.comments,
        shares=None,
        published_at=post.published_at,
        subscribers=followers,
    )
