import os
import pickle
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import os
import signal
import sys

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry
import json
from typing import List
from pydantic import BaseModel

class ProgressUpdate(BaseModel):
    chapter_index: int
    page_num: int = 1  # For PDFs
    scroll_position: float = 0.0
    zoom: float = 100.0
    dual_page: bool = False

class ChatMessage(BaseModel):
    role: str
    content: str

app = FastAPI()
app.mount("/books", StaticFiles(directory="books"), name="books")
templates = Jinja2Templates(directory="templates")

# Where are the book folders located?
BOOKS_DIR = "books"

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

OLD_PROGRESS_FILE = "reading_progress.json"

# --- Per-book storage helpers ---

def _book_dir(book_id: str) -> str:
    return os.path.join(BOOKS_DIR, book_id)

def load_progress(book_id: str) -> dict:
    path = os.path.join(_book_dir(book_id), "progress.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading progress for {book_id}: {e}")
        return {}

def save_progress_helper(book_id: str, data: dict):
    d = _book_dir(book_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "progress.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_chat_history(book_id: str) -> list:
    path = os.path.join(_book_dir(book_id), "chat_history.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading chat history for {book_id}: {e}")
        return []

def save_chat_history(book_id: str, messages: list):
    d = _book_dir(book_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "chat_history.json")
    with open(path, "w") as f:
        json.dump(messages, f, indent=2)

def delete_chat_history(book_id: str):
    path = os.path.join(_book_dir(book_id), "chat_history.json")
    if os.path.exists(path):
        os.remove(path)

def migrate_global_progress():
    """One-time migration: split global reading_progress.json into per-book files."""
    if not os.path.exists(OLD_PROGRESS_FILE):
        return
    try:
        with open(OLD_PROGRESS_FILE, "r") as f:
            all_data = json.load(f)
        for book_id, data in all_data.items():
            # Only migrate if per-book file doesn't already exist
            per_book_path = os.path.join(_book_dir(book_id), "progress.json")
            if not os.path.exists(per_book_path):
                save_progress_helper(book_id, data)
                print(f"  Migrated progress for: {book_id}")
        # Rename old file to .bak
        os.rename(OLD_PROGRESS_FILE, OLD_PROGRESS_FILE + ".bak")
        print(f"Migration complete. Old file renamed to {OLD_PROGRESS_FILE}.bak")
    except Exception as e:
        print(f"Error during progress migration: {e}")

# Run migration on module load
print("Checking for progress migration...")
migrate_global_progress()

@app.post("/api/progress/{book_id}")
async def save_progress(book_id: str, update: ProgressUpdate):
    data = update.model_dump()
    save_progress_helper(book_id, data)
    return {"status": "ok"}

@app.get("/api/chat-history/{book_id}")
async def get_chat_history(book_id: str):
    messages = load_chat_history(book_id)
    return JSONResponse(messages)

@app.post("/api/chat-history/{book_id}")
async def append_chat_message(book_id: str, message: ChatMessage):
    messages = load_chat_history(book_id)
    messages.append(message.model_dump())
    save_chat_history(book_id, messages)
    return {"status": "ok"}

@app.delete("/api/chat-history/{book_id}")
async def clear_chat_history(book_id: str):
    delete_chat_history(book_id)
    return {"status": "ok"}

# --- Annotations API ---

from annotations import (
    Annotation, AnnotationContent, AnnotationTarget, ChatMessage,
    load_annotations, save_annotation_to_disk, 
    delete_annotation_from_disk, update_annotation_in_disk
)

@app.get("/api/annotations/{book_id}")
async def get_annotations(book_id: str):
    return load_annotations(BOOKS_DIR, book_id)

@app.post("/api/annotations/{book_id}")
async def create_annotation(book_id: str, annotation: Annotation):
    # Ensure ID is unique (it's UUID so unlikely to collide but good practice)
    # save_annotation_to_disk simply appends
    try:
        save_annotation_to_disk(BOOKS_DIR, book_id, annotation)
        return {"status": "ok", "id": annotation.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/annotations/{book_id}/{annotation_id}")
async def delete_annotation(book_id: str, annotation_id: str):
    try:
        found = delete_annotation_from_disk(BOOKS_DIR, book_id, annotation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not found:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "ok"}

@app.put("/api/annotations/{book_id}/{annotation_id}")
async def update_annotation(book_id: str, annotation_id: str, annotation: Annotation):
    # Ensure ID matches
    if annotation.id != annotation_id:
        raise HTTPException(status_code=400, detail="ID mismatch")
        
    try:
        found = update_annotation_in_disk(BOOKS_DIR, book_id, annotation)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    if not found:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "ok"}

@app.post("/api/annotations/{book_id}/{annotation_id}/chat")
async def append_annotation_chat(book_id: str, annotation_id: str, message: ChatMessage):
    """
    Appends a new message to an existing annotation's chat thread.
    Use this for context-aware chatting.
    """
    annotations = load_annotations(BOOKS_DIR, book_id)
    target_annotation = None
    for a in annotations:
        if a.id == annotation_id:
            target_annotation = a
            break
            
    if not target_annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
        
    # Ensure chat_messages list exists
    if target_annotation.content.chat_messages is None:
        target_annotation.content.chat_messages = []
        
    target_annotation.content.chat_messages.append(message)
    
    # Update type if it was just a highlight before?
    # Maybe strict typing matters, but for now we just save content.
    if target_annotation.type == 'highlight':
         target_annotation.type = 'chat_thread'

    try:
        update_annotation_in_disk(BOOKS_DIR, book_id, target_annotation)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine)
                    })

    return templates.TemplateResponse("library.html", {"request": request, "books": books})

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(request: Request, book_id: str):
    """Helper to just go to chapter 0 OR open PDF."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
        
    # Check if it is a PDF
    # We stored "original.pdf" as source_file for PDFs
    progress = load_progress(book_id)
    
    if book.source_file.endswith('.pdf'):
         initial_page = progress.get("page_num", 1)
         initial_zoom = progress.get("zoom", 1.0)
         initial_dual_page = "true" if progress.get("dual_page", False) else "false"
         
         return templates.TemplateResponse("pdf_reader.html", {
            "request": request,
            "book": book,
            "book_id": book_id,
            "pdf_url": f"/books/{book_id}/original.pdf",
            "initial_page": initial_page,
            "initial_zoom": initial_zoom,
            "initial_dual_page": initial_dual_page
        })
        
    # For EPUB, redirect to last read chapter if available
    chapter_idx = progress.get("chapter_index", 0)
    # Ensure valid index
    if chapter_idx < 0 or chapter_idx >= len(book.spine):
        chapter_idx = 0
        
    return await read_chapter(request, book_id=book_id, chapter_index=chapter_idx)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    # Load progress to restore scroll/zoom if applicable
    progress = load_progress(book_id)
    initial_scroll = 0
    # Always restore zoom — it's a per-book preference
    initial_zoom = progress.get("zoom", 100)
    
    # Only restore scroll position for the same chapter
    if progress.get("chapter_index") == chapter_index:
        initial_scroll = progress.get("scroll_position", 0)

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx,
        "initial_scroll": initial_scroll,
        "initial_zoom": initial_zoom
    })

@app.get("/api/chapter/{book_id}/{chapter_index}")
async def get_chapter_content(book_id: str, chapter_index: int):
    """Returns chapter HTML + navigation metadata as JSON for AJAX navigation."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return JSONResponse({
        "content": current_chapter.content,
        "chapter_index": chapter_index,
        "href": current_chapter.href,
        "prev_idx": prev_idx,
        "next_idx": next_idx,
        "total_chapters": len(book.spine)
    })

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

@app.post("/api/chat")
async def chat_proxy(payload: dict = Body(...)):
    """
    Proxies chat requests to LLM providers to avoid CORS issues.
    Payload: {
        "provider": "openai" | "anthropic" | "custom",
        "apiKey": "sk-...",
        "baseUrl": "https://...",
        "model": "gpt-4o",
        "messages": [...]
    }
    """
    provider = payload.get("provider")
    api_key = payload.get("apiKey")
    base_url = payload.get("baseUrl")
    model = payload.get("model")
    messages = payload.get("messages")

    if not provider or not messages:
        raise HTTPException(status_code=400, detail="Missing provider or messages")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                data = {"model": model or "gpt-4o", "messages": messages}
                resp = await client.post(url, json=data, headers=headers)
                resp.raise_for_status()
                return resp.json()

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                data = {"model": model or "claude-3-5-sonnet-20240620", "messages": messages, "max_tokens": 1024}
                resp = await client.post(url, json=data, headers=headers)
                resp.raise_for_status()
                return resp.json()

            elif provider == "custom":
                # For custom, we expect a full URL in baseUrl (e.g. http://localhost:1234/v1/chat/completions)
                # Or we can construct it if strictly OpenAI compatible. 
                # Let's assume user provides full URL for maximum flexibility
                if not base_url: 
                     raise HTTPException(status_code=400, detail="Custom provider requires baseUrl")
                else:
                    url = "http://localhost:1234/api/chat/completions"
                
                heading = {}
                if api_key:
                    heading["Authorization"] = f"Bearer {api_key}"
                
                # Assume OpenAI format for custom
                data = {"model": model, "messages": messages} if model else {"messages": messages}
                resp = await client.post(base_url, json=data, headers=heading)
                resp.raise_for_status()
                return resp.json()

            else:
                raise HTTPException(status_code=400, detail="Unknown provider")

    except httpx.HTTPStatusError as e:
        print(f"Upstream error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Upstream error: {e.response.text}")
    except Exception as e:
        print(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/shutdown")
def shutdown_server():
    """Shuts down the server."""
    print("Shutting down server...")
    # Schedule kill
    os.kill(os.getpid(), signal.SIGTERM)
    return {"message": "Server shutting down"}

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
