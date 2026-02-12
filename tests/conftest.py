import pytest
from fastapi.testclient import TestClient
import sys
import os
import shutil
from unittest.mock import patch
import fitz # PyMuPDF
from ebooklib import epub

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, load_book_cached
from reader3 import process_epub, process_pdf, save_to_pickle

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(scope="function")
def temp_books_dir(tmp_path):
    """Create a temp directory for books and patch server to use it."""
    # Ensure the directory exists
    d = tmp_path / "books"
    d.mkdir()
    
    # Patch server.BOOKS_DIR
    with patch('server.BOOKS_DIR', str(d)):
        # Clear cache so we don't serve stale data
        load_book_cached.cache_clear()
        yield d

@pytest.fixture
def create_test_epub(temp_books_dir):
    """Generates a valid minimal EPUB and imports it."""
    def _create(name="test_book"):
        epub_name = f"{name}.epub"
        epub_path = str(temp_books_dir / epub_name)
        
        # Create EPUB
        book = epub.EpubBook()
        book.set_identifier('id123456')
        book.set_title(name)
        book.set_language('en')
        book.add_author('Test Author')

        # Add generic chapter
        c1 = epub.EpubHtml(title='Intro', file_name='intro.xhtml', lang='en')
        c1.content = '<h1>Intro</h1><p>Test Content</p>'
        book.add_item(c1)
        
        book.toc = (c1,)
        book.spine = ['nav', c1]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(epub_path, book, {})
        
        # Import it (simulating CLI)
        out_dir = temp_books_dir / f"{name}_data"
        # reader3.process_epub returns a Book object
        book_obj = process_epub(epub_path, str(out_dir))
        save_to_pickle(book_obj, str(out_dir))
        
        return f"{name}_data"
    return _create

@pytest.fixture
def create_test_pdf(temp_books_dir):
    """Generates a valid minimal PDF and imports it."""
    def _create(name="test_pdf"):
        pdf_name = f"{name}.pdf"
        pdf_path = str(temp_books_dir / pdf_name)
        
        # Create PDF using PyMuPDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello PDF World")
        doc.save(pdf_path)
        doc.close()
        
        # Import it
        out_dir = temp_books_dir / f"{name}_data"
        book_obj = process_pdf(pdf_path, str(out_dir))
        save_to_pickle(book_obj, str(out_dir))
        
        return f"{name}_data"
    return _create
