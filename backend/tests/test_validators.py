from app.domain.validators import validate_script_payload, validate_yaml_text


def valid_payload():
    return {
        "metadata": {
            "title": "Test",
            "source_chapter_count": 3,
            "language": "zh-CN",
            "genre": "drama",
            "logline": "A test logline.",
        },
        "characters": [
            {
                "id": "char_a",
                "name": "A",
                "role": "protagonist",
                "description": "Hero",
                "first_appearance_chapter": 1,
            }
        ],
        "locations": [
            {
                "id": "loc_room",
                "name": "Room",
                "description": "A test room.",
            }
        ],
        "props": [],
        "scenes": [
            {
                "id": "sc_001",
                "title": "One",
                "source_chapters": [1],
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Open",
                "actions": [{"text": "A enters.", "beat": "entrance"}],
                "dialogues": [],
                "adaptation_notes": [],
            },
            {
                "id": "sc_002",
                "title": "Two",
                "source_chapters": [2],
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Continue",
                "actions": [{"text": "A searches.", "beat": "search"}],
                "dialogues": [],
                "adaptation_notes": [],
            },
            {
                "id": "sc_003",
                "title": "Three",
                "source_chapters": [3],
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Close",
                "actions": [{"text": "A decides.", "beat": "decision"}],
                "dialogues": [],
                "adaptation_notes": [],
            },
        ],
        "adaptation_notes": [],
    }


def test_valid_script_payload_passes():
    report = validate_script_payload(valid_payload())
    assert report.valid
    assert report.issues == []


def test_unknown_character_fails_semantic_validation():
    payload = valid_payload()
    payload["scenes"][0]["characters"] = ["char_missing"]
    report = validate_script_payload(payload)
    assert not report.valid
    assert any("Unknown character" in issue.message for issue in report.issues)


def test_validate_yaml_text():
    yaml_text = """
metadata:
  title: Test
  source_chapter_count: 3
  language: zh-CN
  genre: drama
  logline: A test logline.
characters:
  - id: char_a
    name: A
    role: protagonist
    description: Hero
    first_appearance_chapter: 1
locations:
  - id: loc_room
    name: Room
    description: A test room.
props: []
scenes:
  - id: sc_001
    title: One
    source_chapters: [1, 2, 3]
    location_id: loc_room
    time_of_day: night
    characters: [char_a]
    purpose: Open
    actions:
      - text: A enters.
        beat: entrance
    dialogues: []
    adaptation_notes: []
adaptation_notes: []
"""
    report = validate_yaml_text(yaml_text)
    assert report.valid
