import pytest
from fastapi.testclient import TestClient
import os
import shutil
from unittest.mock import patch
import json

# Import directly to test Pydantic models
from annotations import Annotation, AnnotationTarget, AnnotationContent, ChatMessage

def test_annotation_models():
    """Verify Pydantic models structure and validation."""
    target = AnnotationTarget(chapter_index=1, cfi="/2/4/1:0", quote="Hello")
    content = AnnotationContent(text="**Bold Note**", color="#ffff00")
    
    ann = Annotation(type="note", target=target, content=content)
    
    assert ann.id is not None
    assert ann.type == "note"
    assert ann.target.chapter_index == 1
    assert ann.content.text == "**Bold Note**"
    
    # JSON serialization check
    json_str = ann.model_dump_json()
    assert "**Bold Note**" in json_str

@pytest.fixture
def sample_annotation(client):
    """Fixture to create a sample annotation for regression tests."""
    book_id = "test_book_regressions"
    ann = {
        "type": "highlight",
        "target": {"chapter_index": 0, "quote": "Test Quote"},
        "content": {"text": "Original text", "color": "yellow"}
    }
    resp = client.post(f"/api/annotations/{book_id}", json=ann)
    assert resp.status_code == 200
    return book_id, resp.json()["id"]

def test_regression_edit_annotation(client, sample_annotation):
    """Regression Test #4: Verify annotations can be edited (PUT)."""
    book_id, ann_id = sample_annotation
    
    # 1. Update text
    updated_data = {
        "id": ann_id,
        "type": "note", # Changing type
        "target": {"chapter_index": 0, "quote": "Test Quote"},
        "content": {"text": "Edited Note Content", "color": "blue"}
    }
    
    resp = client.put(f"/api/annotations/{book_id}/{ann_id}", json=updated_data)
    assert resp.status_code == 200, f"Update failed: {resp.text}"
    
    # 2. Verify persistence
    resp = client.get(f"/api/annotations/{book_id}")
    anns = resp.json()
    saved = next(a for a in anns if a["id"] == ann_id)
    assert saved["content"]["text"] == "Edited Note Content"
    assert saved["content"]["color"] == "blue"
    assert saved["type"] == "note"

def test_regression_delete_annotation(client, sample_annotation):
    """Regression Test #4: Verify annotations can be deleted."""
    book_id, ann_id = sample_annotation
    
    # 1. Delete
    resp = client.delete(f"/api/annotations/{book_id}/{ann_id}")
    assert resp.status_code == 200
    
    # 2. Verify gone
    resp = client.get(f"/api/annotations/{book_id}")
    anns = resp.json()
    assert not any(a["id"] == ann_id for a in anns)

def test_regression_ask_ai_flow(client, sample_annotation):
    """Regression Test #3: Verify 'Ask AI' flow (appending chat messages)."""
    book_id, ann_id = sample_annotation
    
    # 1. Send chat message (simulating "Ask AI" or user reply)
    chat_msg = {"role": "user", "content": "Explain this context"}
    resp = client.post(f"/api/annotations/{book_id}/{ann_id}/chat", json=chat_msg)
    assert resp.status_code == 200
    
    # 2. Verify message appended
    resp = client.get(f"/api/annotations/{book_id}")
    anns = resp.json()
    saved = next(a for a in anns if a["id"] == ann_id)
    
    assert saved["type"] == "chat_thread" # Should auto-update type
    assert len(saved["content"]["chat_messages"]) == 1
    assert saved["content"]["chat_messages"][0]["content"] == "Explain this context"

def test_error_handling_nonexistent_ids(client, temp_books_dir):
    """Verify clean error handling for bad IDs."""
    book_id = "test_book_missing"
    
    # Delete missing
    resp = client.delete(f"/api/annotations/{book_id}/bad-id")
    assert resp.status_code == 404
    
    # Update missing
    fake_ann = {
        "id": "bad-id", 
        "type": "note",
        "target": {"chapter_index": 0},
        "content": {}
    }
    resp = client.put(f"/api/annotations/{book_id}/bad-id", json=fake_ann)
    # Could be 404 or 500 depending on impl, but 404 is ideal. 
    # Current impl might raise 404 or 500. Let's check impl:
    # server.py update_annotation returns 404 if not found.
    assert resp.status_code == 404, f"Expected 404 but got {resp.status_code}. Details: {resp.text}"
