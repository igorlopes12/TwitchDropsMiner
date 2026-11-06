"""
Plain-dict snapshots of core objects, ready to be sent to the web page as JSON.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from channel import Channel
    from inventory import DropsCampaign, TimedDrop
    from utils import Game


def _drop_image(drop: TimedDrop) -> str | None:
    return str(drop.benefits[0].image_url) if drop.benefits else None


def _drop_state(drop: TimedDrop) -> str:
    if drop.is_claimed:
        return "claimed"
    if drop.current_minutes > 0:
        return "progress"
    return "pending"


def drop_view(drop: TimedDrop) -> dict[str, Any]:
    campaign = drop.campaign
    return {
        "id": drop.id,
        "name": drop.name,
        "game": campaign.game.name,
        "campaign": campaign.name,
        "image": _drop_image(drop),
        "percent": round(drop.progress * 100, 1),
        "remaining_minutes": int(drop.remaining_minutes),
        "campaign_claimed": int(campaign.claimed_drops),
        "campaign_total": int(campaign.total_drops),
        "campaign_remaining_minutes": int(campaign.remaining_minutes),
    }


def campaign_view(campaign: DropsCampaign, wanted: bool) -> dict[str, Any]:
    if campaign.upcoming:
        status = "upcoming"
    elif campaign.finished or campaign.expired:
        status = "finished"
    else:
        status = "active"
    return {
        "id": campaign.id,
        "name": campaign.name,
        "game": campaign.game.name,
        "game_image": str(campaign.image_url),
        "starts_at": campaign.starts_at.isoformat(),
        "ends_at": campaign.ends_at.isoformat(),
        "status": status,
        "wanted": wanted,
        "drops": [
            {
                "id": drop.id,
                "name": drop.name,
                "image": _drop_image(drop),
                "state": _drop_state(drop),
                "percent": round(drop.progress * 100, 1),
            }
            for drop in campaign.drops
        ],
    }


def channel_view(channel: Channel, watching: bool) -> dict[str, Any]:
    if channel.online:
        status = "online"
    elif channel.pending_online:
        status = "pending"
    else:
        status = "offline"
    return {
        "id": channel.id,
        "name": channel.name,
        "status": status,
        "viewers": channel.viewers if status == "online" else None,
        "game": channel.game.name if channel.game is not None else None,
        "watching": watching,
    }


def game_option(game: Game, campaigns: list[DropsCampaign]) -> dict[str, Any]:
    soonest = min(campaigns, key=lambda c: c.ends_at)
    return {
        "name": game.name,
        "image": str(soonest.image_url),
        "drops": sum(c.total_drops for c in campaigns),
        "ends_at": soonest.ends_at.isoformat(),
    }
