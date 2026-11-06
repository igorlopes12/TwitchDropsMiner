import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from webgui.views import campaign_view, channel_view, drop_view, game_option

ENDS = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)
STARTS = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)


def make_drop(name="Supply Crate", current=48, required=60, claimed=False, campaign=None):
    drop = NS(
        id=f"d-{name}",
        name=name,
        current_minutes=current,
        required_minutes=required,
        remaining_minutes=max(required - current, 0),
        progress=min(current / required, 1.0) if current > 0 else 0.0,
        is_claimed=claimed,
        benefits=[NS(image_url=f"https://img/{name}.png")],
        campaign=campaign,
    )
    return drop


def make_campaign(game="Hunt: Showdown 1896", drops=None, upcoming=False, finished=False, expired=False):
    campaign = NS(
        id="c1",
        name="Hunt 1896 (Week 2, Pt. 3)",
        game=NS(name=game),
        image_url="https://img/box.jpg",
        starts_at=STARTS,
        ends_at=ENDS,
        upcoming=upcoming,
        finished=finished,
        expired=expired,
        remaining_minutes=215,
    )
    campaign.drops = drops if drops is not None else [make_drop(campaign=campaign)] + [
        make_drop(f"Drop {i}", current=0, campaign=campaign) for i in range(4)
    ]
    for d in campaign.drops:
        d.campaign = campaign
    campaign.total_drops = len(campaign.drops)
    campaign.claimed_drops = sum(d.is_claimed for d in campaign.drops)
    return campaign


def test_drop_view_values():
    campaign = make_campaign()
    view = drop_view(campaign.drops[0])
    assert view["name"] == "Supply Crate"
    assert view["game"] == "Hunt: Showdown 1896"
    assert view["campaign"] == "Hunt 1896 (Week 2, Pt. 3)"
    assert view["percent"] == 80.0
    assert view["remaining_minutes"] == 12
    assert view["campaign_claimed"] == 0
    assert view["campaign_total"] == 5
    assert view["campaign_remaining_minutes"] == 215
    assert view["image"] == "https://img/Supply Crate.png"


def test_campaign_status_upcoming():
    assert campaign_view(make_campaign(upcoming=True), wanted=True)["status"] == "upcoming"


def test_campaign_status_finished_when_expired():
    assert campaign_view(make_campaign(expired=True), wanted=True)["status"] == "finished"


def test_campaign_status_active():
    view = campaign_view(make_campaign(), wanted=False)
    assert view["status"] == "active"
    assert view["wanted"] is False
    assert view["ends_at"] == ENDS.isoformat()


def test_campaign_drop_states():
    campaign = make_campaign(drops=[
        make_drop("a", current=60, claimed=True),
        make_drop("b", current=30),
        make_drop("c", current=0),
    ])
    states = [d["state"] for d in campaign_view(campaign, wanted=True)["drops"]]
    assert states == ["claimed", "progress", "pending"]


def test_channel_viewers_none_when_offline():
    channel = NS(id=7, name="crowbait_tv", online=False, pending_online=False, viewers=None, game=None)
    view = channel_view(channel, watching=False)
    assert view["status"] == "offline"
    assert view["viewers"] is None
    assert view["game"] is None


def test_channel_online_watching():
    channel = NS(id=1, name="huntshowdown", online=True, pending_online=False, viewers=2431,
                 game=NS(name="Hunt: Showdown 1896"))
    view = channel_view(channel, watching=True)
    assert view == {
        "id": 1, "name": "huntshowdown", "status": "online", "viewers": 2431,
        "game": "Hunt: Showdown 1896", "watching": True,
    }


def test_game_option_uses_soonest_end():
    later = make_campaign()
    sooner = make_campaign()
    sooner.ends_at = datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc)
    view = game_option(later.game, [later, sooner])
    assert view["name"] == "Hunt: Showdown 1896"
    assert view["drops"] == 10
    assert view["ends_at"] == sooner.ends_at.isoformat()
    assert view["image"] == "https://img/box.jpg"


def test_views_are_json_serializable():
    nasty = '"</script>😀'
    campaign = make_campaign(game=nasty)
    payload = [drop_view(campaign.drops[0]), campaign_view(campaign, wanted=True),
               game_option(campaign.game, [campaign])]
    assert json.loads(json.dumps(payload))[1]["game"] == nasty
