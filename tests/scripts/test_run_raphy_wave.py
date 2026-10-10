import json
from pathlib import Path
from scripts.run_raphy_wave import get_open_stories, mark_story_pass, mark_story_dropped

def test_get_open_stories(tmp_path: Path):
    prd_path = tmp_path / "prd.json"
    prd_path.write_text(json.dumps({
        "userStories": [
            {"id": "RA-104", "title": "Test 1", "passes": False},
            {"id": "RA-105", "title": "Test 2", "passes": True},
            {"id": "RA-106", "title": "Test 3", "passes": False, "dropped": True}
        ]
    }), encoding="utf-8")
    
    open_stories = get_open_stories(prd_path)
    assert len(open_stories) == 1
    assert open_stories[0]["id"] == "RA-104"

def test_mark_story_pass(tmp_path: Path):
    prd_path = tmp_path / "prd.json"
    prd_path.write_text(json.dumps({
        "userStories": [
            {"id": "RA-104", "title": "Test 1", "passes": False}
        ]
    }), encoding="utf-8")
    
    mark_story_pass(prd_path, "RA-104", notes="Passed cleanly")
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    assert data["userStories"][0]["passes"] is True
    assert data["userStories"][0]["notes"] == "Passed cleanly"

def test_mark_story_dropped(tmp_path: Path):
    prd_path = tmp_path / "prd.json"
    prd_path.write_text(json.dumps({
        "userStories": [
            {"id": "RA-104", "title": "Test 1", "passes": False}
        ]
    }), encoding="utf-8")
    
    mark_story_dropped(prd_path, "RA-104", reason="Proved negative value")
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    assert data["userStories"][0]["passes"] is False
    assert data["userStories"][0]["dropped"] is True
    assert "Proved negative value" in data["userStories"][0]["notes"]
