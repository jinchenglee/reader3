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
    if book.source_file.endswith('.pdf'):
         return templates.TemplateResponse("pdf_reader.html", {
            "request": request,
            "book": book,
            "book_id": book_id,
            "pdf_url": f"/books/{book_id}/original.pdf"
        })
        
    return await read_chapter(request, book_id=book_id, chapter_index=0)

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

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx
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
