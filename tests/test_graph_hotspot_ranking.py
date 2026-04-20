from sediment.platform_services import rank_hotspots


def test_rank_hotspots_prefers_recent_tacit_nodes() -> None:
    ranked = rank_hotspots(
        [
            {
                "id": "entry::stable",
                "node_type": "canonical_entry",
                "recentness": 0.12,
                "burst_level": 0.08,
                "stability": 0.94,
                "formation_stage": "stable",
                "energy": 0.44,
            },
            {
                "id": "insight::forming",
                "node_type": "insight_proposal",
                "recentness": 0.9,
                "burst_level": 0.68,
                "stability": 0.22,
                "formation_stage": "condensing",
                "energy": 0.58,
            },
        ]
    )

    assert ranked[0]["id"] == "insight::forming"
    assert ranked[0]["reason_code"] == "tacit"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_hotspots_kind_filter_keeps_only_matching_nodes() -> None:
    ranked = rank_hotspots(
        [
            {
                "id": "entry::recent",
                "node_type": "canonical_entry",
                "recentness": 0.82,
                "burst_level": 0.3,
                "stability": 0.9,
                "formation_stage": "stable",
                "energy": 0.5,
            },
            {
                "id": "insight::forming",
                "node_type": "insight_proposal",
                "recentness": 0.66,
                "burst_level": 0.62,
                "stability": 0.28,
                "formation_stage": "condensing",
                "energy": 0.54,
            },
        ],
        kind="tacit",
    )

    assert [item["id"] for item in ranked] == ["insight::forming"]
