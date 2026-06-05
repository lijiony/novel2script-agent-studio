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
        "adaptation_profile": {
            "format_type": "short_drama",
            "adaptation_scale": "balanced",
            "style_focus": "psychological",
            "preserve_items": [],
            "forbidden_changes": [],
            "author_notes": None,
        },
        "adaptation_strategy": ["Externalize inner narration into playable actions."],
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
                "source_excerpt": "A enters the room.",
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Open",
                "scene_purpose": "Open the mystery.",
                "conflict": "A wants answers but fears the room.",
                "emotional_shift": "From calm to alert.",
                "production_risk": "May become exposition-heavy.",
                "format_type": "short_drama",
                "actions": [{"text": "A enters.", "beat": "entrance", "origin": "ai_adapted"}],
                "dialogues": [],
                "ai_added_content": [],
                "revision_suggestions": [],
                "adaptation_notes": [],
            },
            {
                "id": "sc_002",
                "title": "Two",
                "source_chapters": [2],
                "source_excerpt": "A searches.",
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Continue",
                "scene_purpose": "Escalate the investigation.",
                "conflict": "The clue helps A but also raises stakes.",
                "emotional_shift": "From alert to anxious.",
                "production_risk": "Needs a visible obstacle.",
                "format_type": "short_drama",
                "actions": [{"text": "A searches.", "beat": "search", "origin": "ai_adapted"}],
                "dialogues": [],
                "ai_added_content": [],
                "revision_suggestions": [],
                "adaptation_notes": [],
            },
            {
                "id": "sc_003",
                "title": "Three",
                "source_chapters": [3],
                "source_excerpt": "A decides.",
                "location_id": "loc_room",
                "time_of_day": "night",
                "characters": ["char_a"],
                "purpose": "Close",
                "scene_purpose": "Push A into the next act.",
                "conflict": "A must choose safety or truth.",
                "emotional_shift": "From anxious to determined.",
                "production_risk": "Decision needs a playable trigger.",
                "format_type": "short_drama",
                "actions": [{"text": "A decides.", "beat": "decision", "origin": "ai_adapted"}],
                "dialogues": [],
                "ai_added_content": [],
                "revision_suggestions": [],
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
adaptation_profile:
  format_type: short_drama
  adaptation_scale: balanced
  style_focus: psychological
  preserve_items: []
  forbidden_changes: []
  author_notes:
adaptation_strategy:
  - Externalize inner narration into playable actions.
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
    source_excerpt: A enters the room.
    location_id: loc_room
    time_of_day: night
    characters: [char_a]
    purpose: Open
    scene_purpose: Open the mystery.
    conflict: A wants answers but fears the room.
    emotional_shift: From calm to alert.
    production_risk: May become exposition-heavy.
    format_type: short_drama
    actions:
      - text: A enters.
        beat: entrance
        origin: ai_adapted
    dialogues: []
    ai_added_content: []
    revision_suggestions: []
    adaptation_notes: []
adaptation_notes: []
"""
    report = validate_yaml_text(yaml_text)
    assert report.valid
