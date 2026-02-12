import json
import re
import pytest

def test_read_root(client):
    """Verify the root page loads."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Library" in response.text

def test_read_epub_page_loads(client, create_test_epub):
    """Verify EPUB reader loads and contains valid JSON data block."""
    book_id = create_test_epub("my_test_epub")
    
    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    
    # Check for the data script block
    assert 'id="reader-data"' in response.text, "reader-data block missing"
    
    # Extract and validate JSON
    match = re.search(r'<script type="application/json" id="reader-data">\s*(\{.*?\})\s*</script>', response.text, re.DOTALL)
    assert match, "Could not extract reader-data JSON"
    
    data_str = match.group(1)
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON in reader-data: {e}")
        
    assert data["bookId"] == book_id
    assert "spineMap" in data
    assert isinstance(data["spineMap"], dict)

def test_read_pdf_page_loads(client, create_test_pdf):
    """Verify PDF reader loads and contains valid JSON data block."""
    book_id = create_test_pdf("my_test_pdf")
    
    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    
    # Check for the data script block
    assert 'id="pdf-data"' in response.text, "pdf-data block missing"
    
    # Extract and validate JSON
    match = re.search(r'<script type="application/json" id="pdf-data">\s*(\{.*?\})\s*</script>', response.text, re.DOTALL)
    assert match, "Could not extract pdf-data JSON"
    
    data_str = match.group(1)
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON in pdf-data: {e}")
        
    assert data["bookId"] == book_id
    assert "pdfUrl" in data
    assert data["pdfUrl"].endswith(".pdf")

def test_chat_history_api(client, temp_books_dir):
    """Verify chat history CRUD operations."""
    # We don't strictly need a book to exist for chat history API as it's just file I/O 
    # in the book folder, but let's be safe and use a dummy ID.
    # The server creates the folder if it doesn't exist for save_chat_history.
    book_id = "test_book_history"
    
    # Cleanup before test (implicit because temp_books_dir is fresh per function??)
    # temp_books_dir is scope='function', so it's fresh.
    
    # 1. Get empty history
    resp = client.get(f"/api/chat-history/{book_id}")
    assert resp.status_code == 200
    assert resp.json() == []

    # 2. Append message
    msg = {"role": "user", "content": "Hello world"}
    resp = client.post(f"/api/chat-history/{book_id}", json=msg)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    
    # 3. Get history with message
    resp = client.get(f"/api/chat-history/{book_id}")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 1
    assert history[0]["content"] == "Hello world"
    
    # 4. Cleanup
    resp = client.delete(f"/api/chat-history/{book_id}")
    assert resp.status_code == 200
    
    # Verify empty again
    resp = client.get(f"/api/chat-history/{book_id}")
    assert resp.json() == []
