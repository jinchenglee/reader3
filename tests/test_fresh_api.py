import pytest
from fastapi.testclient import TestClient
from server import app
import os
import shutil

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_book_with_annotations():
    import uuid
    book_id = f"test_book_{uuid.uuid4().hex}"
    # Use absolute path to ensure no CWD ambiguity
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    book_dir = os.path.join(project_root, "books", f"{book_id}_data")
    
    # Cleanup before
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir)
    
    # Ensure it's gone
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir) # Try again?
        
    os.makedirs(book_dir, exist_ok=True)
    
    # Create empty annotations.json
    with open(os.path.join(book_dir, "annotations.json"), "w") as f:
        f.write("[]")
        
    yield book_id
    
    # Cleanup after
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir)

def test_create_and_get_annotation_with_rects_fresh(client, test_book_with_annotations):
    """
    Verify that an annotation with 'rects' (list of lists) is correctly saved and retrieved.
    """
    book_id = test_book_with_annotations
    
    payload = {
        "type": "highlight",
        "target": {
            "chapter_index": 0,
            "page_num": 5,
            "rect": [0.1, 0.1, 0.5, 0.5], # Legacy field
            "rects": [
                [0.1, 0.1, 0.5, 0.1],
                [0.1, 0.2, 0.4, 0.1]
            ],
            "quote": "Test Quote"
        },
        "content": {
            "text": "",
            "color": "pink"
        }
    }
    
    # 1. Create
    response = client.post(f"/api/annotations/{book_id}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    ann_id = data["id"]
    
    # 2. Retrieve (List)
    response = client.get(f"/api/annotations/{book_id}")
    assert response.status_code == 200
    annotations = response.json()
    
    assert len(annotations) == 1
    saved_ann = annotations[0]
    assert saved_ann["id"] == ann_id
    assert "rects" in saved_ann["target"]
    assert len(saved_ann["target"]["rects"]) == 2
    assert saved_ann["target"]["rects"][0] == [0.1, 0.1, 0.5, 0.1]
