import os
import json
import uuid
from datetime import datetime
from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field

# --- Data Models ---

class AnnotationTarget(BaseModel):
    chapter_index: int
    # For EPUB:
    cfi: Optional[str] = None 
    quote: Optional[str] = None
    # For PDF:
    page_num: Optional[int] = None
    rect: Optional[List[float]] = None # Deprecated, use rects
    rects: Optional[List[List[float]]] = None 

    from pydantic import model_validator

    @model_validator(mode='before')
    @classmethod
    def migrate_rect_to_rects(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # If 'rect' is present but 'rects' is missing, migrate it
            if 'rect' in data and data['rect'] and 'rects' not in data:
                data['rects'] = [data['rect']]
        return data 

class ChatMessage(BaseModel):
    role: str
    content: str

class AnnotationContent(BaseModel):
    text: Optional[str] = None  # Markdown string for notes
    color: Optional[str] = None # e.g. "#ffff00"
    chat_messages: Optional[List[ChatMessage]] = None

class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    type: Literal['highlight', 'note', 'chat_thread']
    target: AnnotationTarget
    content: AnnotationContent

# --- Storage Logic ---

def _get_annotations_path(books_dir: str, book_id: str) -> str:
    return os.path.join(books_dir, book_id, "annotations.json")

def load_annotations(books_dir: str, book_id: str) -> List[Annotation]:
    path = _get_annotations_path(books_dir, book_id)
    if not os.path.exists(path):
        return []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            return [Annotation(**item) for item in raw_data]
    except Exception as e:
        print(f"Error loading annotations for {book_id}: {e}")
        return []

def save_annotation_to_disk(books_dir: str, book_id: str, new_annotation: Annotation):
    # Load existing
    annotations = load_annotations(books_dir, book_id)
    annotations.append(new_annotation)
    
    # Save back
    path = _get_annotations_path(books_dir, book_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            # dumping model_dump(mode='json') handles datetime/uuid serialization
            json.dump([a.model_dump(mode='json') for a in annotations], f, indent=2)
    except Exception as e:
        print(f"Error saving annotation for {book_id}: {e}")
        raise e

def delete_annotation_from_disk(books_dir: str, book_id: str, annotation_id: str):
    annotations = load_annotations(books_dir, book_id)
    filtered = [a for a in annotations if a.id != annotation_id]
    
    if len(filtered) == len(annotations):
        return False # ID not found
    
    path = _get_annotations_path(books_dir, book_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([a.model_dump(mode='json') for a in filtered], f, indent=2)
        return True
    except Exception as e:
        print(f"Error deleting annotation for {book_id}: {e}")
        raise e

def update_annotation_in_disk(books_dir: str, book_id: str, updated_annotation: Annotation):
    annotations = load_annotations(books_dir, book_id)
    found = False
    for i, a in enumerate(annotations):
        if a.id == updated_annotation.id:
            annotations[i] = updated_annotation
            found = True
            break
    
    if not found:
        return False

    path = _get_annotations_path(books_dir, book_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([a.model_dump(mode='json') for a in annotations], f, indent=2)
        return True
    except Exception as e:
        print(f"Error updating annotation for {book_id}: {e}")
        raise e
