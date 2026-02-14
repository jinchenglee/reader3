import pytest
from bs4 import BeautifulSoup

def test_regression_sidebar_css_fix(client, create_test_epub):
    """
    Step Id: 312
    User reported that sidebar resizing was broken/blocked.
    Diagnosis: #right-sidebar lacked 'position: relative', causing the absolute-positioned
    resize handle to be positioned relative to the viewport (likely off-screen or far left)
    instead of the sidebar edge.
    
    This test verifies:
    1. #right-sidebar has 'position: relative' in its inline styles or style block.
    2. #chat-sidebar does NOT have a resize handle div (id="resize-handle").
    """
    
    book_id = create_test_epub("test_book_ui")
    
    # Use the correct route /read/{book_id}
    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Check for position: relative in #right-sidebar CSS
    # Note: Styles are likely in a <style> block in components/right_sidebar.html
    # We search all style blocks.
    style_content = ""
    for style in soup.find_all('style'):
        if style.string:
            style_content += style.string
            
    # Normalize whitespace for check
    style_content = " ".join(style_content.split())
    
    # We expect strict checking for #right-sidebar { ... position: relative
    # But string matching is brittle. Let's check if the specific rule exists.
    assert "#right-sidebar" in style_content
    # Check if 'position: relative' is near '#right-sidebar'
    # This is a bit heuristic but sufficient for regression
    
    # Alternatively, check if we find the resize handle attached to it? No that's JS.
    
    # Let's rely on checking the text of the template file? No, integration test is better.
    # The rendered HTML will have the styles.
    
    # Let's check strictly for the fix we made:
    # #right-sidebar { ... position: relative; ... }
    # We can just check that 'position: relative' is present in the CSS for #right-sidebar
    # Extract the block for #right-sidebar
    import re
    match = re.search(r'#right-sidebar\s*{([^}]*)}', style_content)
    assert match is not None, "Could not find #right-sidebar CSS rule"
    css_props = match.group(1)
    
    assert "position: relative" in css_props, "Regression: #right-sidebar missing 'position: relative'"


def test_regression_chat_component_cleanup(client, create_test_epub):
    """
    Verifies that the Chat Component no longer has the conflicting resize handle.
    """
    book_id = create_test_epub("test_book_ui_2")

    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # The chat sidebar id is 'chat-sidebar'
    chat_sidebar = soup.find(id='chat-sidebar')
    assert chat_sidebar is not None
    
    # Did we successfully remove the resize-handle?
    resize_handle = chat_sidebar.find(id='resize-handle')
    assert resize_handle is None, "Regression: Conflicting 'resize-handle' found inside Chat Component"

def test_regression_ask_ai_context_wiring(client, create_test_epub):
    """
    Step Id: 387
    User requested: 'Ask AI' should open Global Chat with a cancellable context box,
    instead of creating a new Thread annotation.
    
    This test verifies:
    1. right_sidebar.html contains 'openGlobalChat' method.
    2. reader.html 'Ask AI' button calls 'triggerAskAI' (not triggerAnnotation).
    """
    book_id = create_test_epub("test_book_ai_wiring")
    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    
    text = response.text
    
    # 1. Check for openGlobalChat definition in the JS
    assert "openGlobalChat:" in text, "RightSidebar missing openGlobalChat method"
    
    # 2. Check for Ask AI button wiring
    soup = BeautifulSoup(text, 'html.parser')
    selection_menu = soup.find(id="selection-menu")
    assert selection_menu is not None
    
    buttons = selection_menu.find_all("button")
    ask_btn = None
    for btn in buttons:
        if "Ask AI" in btn.text:
            ask_btn = btn
            break
            
    assert ask_btn is not None, "Ask AI button not found"
    onclick = ask_btn.get("onclick", "")
    assert "triggerAskAI()" in onclick, "Ask AI button should call triggerAskAI()"
    assert "triggerAnnotation('ask')" not in onclick, "Ask AI button should NOT call triggerAnnotation('ask')"

    assert "triggerAnnotation('ask')" not in onclick, "Ask AI button should NOT call triggerAnnotation('ask')"


def test_regression_pdf_highlight_wiring(client, create_test_pdf):
    """
    Step Id: 470
    User reported: Highlights didn't scale/persist on PDF zoom/resize.
    renderHighlights() must be called after render completes (so highlights scale with zoom).
    """
    book_id = create_test_pdf("test_book_pdf_scaling")
    response = client.get(f"/read/{book_id}")
    assert response.status_code == 200
    text = response.text
    assert "function renderHighlights()" in text
    count = text.count("renderHighlights()")
    assert count >= 3, "renderHighlights() should be called in loadAnnotations and after render (single + dual)"
    # After render we call it inside requestAnimationFrame in the promise .then()
    assert "requestAnimationFrame" in text and "renderHighlights()" in text, "renderHighlights() must run after layout (e.g. in requestAnimationFrame after render)"


def test_regression_ui_simplification(client, create_test_epub, create_test_pdf):
    """
    Step Id: 511
    User requested: 
    1. Remove 'Note' button from selection menu.
    2. Remove 'Thread' tab from sidebar.
    3. PDF highlights normalized to [0,1].
    
    This test verifies:
    1. 'Note' button is NOT present in reader.html and pdf_reader.html.
    2. 'Thread' tab is NOT present in right_sidebar.html (via rendered page).
    3. pdf_reader.html contains logic for normalization (heuristic).
    """
    
    # 1. EPUB check
    book_id = create_test_epub("test_book_ui_simple")
    resp_epub = client.get(f"/read/{book_id}")
    assert 'onclick="triggerAnnotation(\'note\')"' not in resp_epub.text, "EPUB: 'Note' button wasn't removed"
    
    # 2. PDF check
    pdf_id = create_test_pdf("test_book_ui_simple_pdf")
    resp_pdf = client.get(f"/read/{pdf_id}")
    assert 'onclick="triggerAnnotation(\'note\')"' not in resp_pdf.text, "PDF: 'Note' button wasn't removed"
    
    # 3. Sidebar check (Thread tab removal)
    # The tab button id was 'tab-btn-thread'
    assert 'id="tab-btn-thread"' not in resp_epub.text, "Sidebar: Thread tab button should be removed"
    assert 'id="tab-thread"' not in resp_epub.text, "Sidebar: Thread tab content div should be removed"
    
    # 4. PDF Normalization check
    # We look for the division by containerRect.width or similar in the mouseup handler logic
    # "x: (rect.left - containerRect.left) / containerRect.width"
    # Or check renderHighlights using '%'
    assert "div.style.left = (ann.target.rect[0] * 100) + '%'" in resp_pdf.text, "PDF: Render logic should use percentages"


def test_regression_pdf_annotation_edit_delete_and_scale(client, create_test_pdf):
    """
    Regression: PDF annotations tab edit/delete and highlight scaling.
    - PDF reader must define updateAnnotationContent and reloadAnnotations so edit/delete work.
    - Highlights use dedicated .highlight-layer overlay (same coordinate system as selection) for correct scaling.
    - Annotations list is per-page (visiblePages / dual-page aware).
    """
    book_id = create_test_pdf("test_pdf_ann")
    resp = client.get(f"/read/{book_id}")
    assert resp.status_code == 200
    text = resp.text
    assert "window.updateAnnotationContent = updateAnnotationContent" in text, "PDF: updateAnnotationContent must be exposed"
    assert "window.reloadAnnotations = loadAnnotations" in text, "PDF: reloadAnnotations must be exposed for delete refresh"
    assert "highlight-layer" in text, "PDF: highlights use dedicated overlay layer for zoom scaling"
    assert "visiblePages" in text and "visibleAnns" in text, "PDF: annotations list must be per-page (visible pages filter)"


def test_regression_sidebar_delete_reloads_annotations(client, create_test_epub):
    """
    Regression: After deleting an annotation, UI must reload from server (reloadAnnotations).
    """
    resp = client.get(f"/read/{create_test_epub('test_sidebar_reload')}")
    assert resp.status_code == 200
    assert "window.reloadAnnotations" in resp.text, "Sidebar or reader must use reloadAnnotations"
    assert "reloadAnnotations()" in resp.text or "reloadAnnotations();" in resp.text, "reloadAnnotations must be invoked after delete"


def test_regression_epub_annotation_navigate_and_reload(client, create_test_epub):
    """
    Regression: EPUB annotations - reloadAnnotations, activateHighlight with chapter navigation.
    - Annotations list is per-section (chapterAnns filter by chapterIndex).
    - Multi-node highlight support (findRangeForQuote) so highlights across elements are visible.
    """
    book_id = create_test_epub("test_epub_ann")
    resp = client.get(f"/read/{book_id}")
    assert resp.status_code == 200
    text = resp.text
    assert "window.reloadAnnotations = loadAnnotations" in text, "EPUB: reloadAnnotations must be set for delete refresh"
    assert "currentAnnotations" in text, "EPUB: currentAnnotations used for edit/delete"
    assert "activateHighlight" in text and "loadChapter" in text, "EPUB: activateHighlight should use loadChapter when different chapter"
    assert "ann-edit-btn" in text and "ann-delete-btn" in text, "EPUB: edit/delete use data-id buttons to allow edit-again"
    assert "chapterAnns" in text and "chapter_index === chapterIndex" in text, "EPUB: annotations list must be per-section (current chapter only)"
    assert "findRangeForQuote" in text or "extractContents" in text, "EPUB: multi-node range for highlight visibility across elements"
