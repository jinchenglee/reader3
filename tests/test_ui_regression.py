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
    
    # 4. PDF Normalization check (Multi-rect support & Styling)
    # The new logic iterates over `rects` and uses `r[0]`, `r[1]`, etc.
    # We check for the loop or the new variable usage.
    assert "rects.forEach(r => {" in resp_pdf.text or "div.style.left = (r[0] * 100) + '%'" in resp_pdf.text, "PDF: Render logic should use percentages with multi-rect support"
    
    # 5. Styling Check (Pink Underline)
    # Ensure background is transparent and border is pink (or borderBottom is set)
    assert "div.style.background = 'transparent'" in resp_pdf.text or "div.style.background='transparent'" in resp_pdf.text, "PDF: Highlight background should be transparent"
    assert "div.style.borderBottom" in resp_pdf.text and "#ff69b4" in resp_pdf.text, "PDF: Highlight should use pink underline (#ff69b4)"


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


def test_regression_chat_history_format_parsing(client, create_test_epub):
    """
    Step Id: 54
    User requested: Chat history should include quoted text in a foldable format.
    The frontend JS (chat_component.html) detects "Context:\\n\\"\\"\\"..." pattern
    and renders a <details> element.
    
    This test verifies:
    1. The JS logic checks for `text.startsWith('Context:\\n\\"\\"\\"')`
    2. The JS logic creates a `details` element.
    3. The JS logic creates a `summary` element.
    """
    book_id = create_test_epub("test_chat_format")
    # Chat component is included in read page
    resp = client.get(f"/read/{book_id}")
    assert resp.status_code == 200
    text = resp.text
    
    # Check for the specific parsing logic we added
    assert "Context:\\n\"\"\"" in text, "Chat component missing context detection logic"
    assert "document.createElement('details')" in text, "Chat component missing <details> creation"
    assert "document.createElement('summary')" in text, "Chat component missing <summary> creation"
    # Verify truncation logic (30 chars) and new "Quoted: " label
    assert "context.substring(0, 30)" in text, "Chat component missing 30-char truncation"
    assert 'summary.textContent = "Quoted: "' in text, "Chat component missing 'Quoted:' label"
    
    # Verify Highlight button
    assert 'id="chat-context-highlight"' in text, "Chat component missing highlight button"
    assert 'window.handleHighlightFromChat' in text, "Chat component missing handleHighlightFromChat call"


def test_mobile_touch_selection_support(client, create_test_epub, create_test_pdf):
    """
    Verifies that both EPUB and PDF readers support touch-device text selection.
    On touch devices (pointer: coarse), a persistent header action bar replaces
    the floating popup (which conflicts with the iOS native selection toolbar).
    """
    epub_id = create_test_epub("test_touch_epub")
    pdf_id = create_test_pdf("test_touch_pdf")

    resp_epub = client.get(f"/read/{epub_id}")
    assert resp_epub.status_code == 200

    resp_pdf = client.get(f"/read/{pdf_id}")
    assert resp_pdf.status_code == 200

    for label, text in [("EPUB", resp_epub.text), ("PDF", resp_pdf.text)]:
        assert 'id="touch-action-bar"' in text, f"{label}: touch-action-bar element missing"
        assert 'pointer: coarse' in text, f"{label}: touch detection media query missing"
        assert 'selectionchange' in text, f"{label}: selectionchange listener missing"
        assert 'isTouchPrimary' in text, f"{label}: isTouchPrimary guard variable missing"
        assert 'mouseup' in text, f"{label}: mouseup handler (desktop path) must still be present"
        # Touch bar buttons must wire to the correct handlers
        assert "onclick=\"triggerAnnotation('highlight')\"" in text, \
            f"{label}: touch-action-bar Highlight button must call triggerAnnotation('highlight')"
        assert 'onclick="triggerAskAI()"' in text, \
            f"{label}: touch-action-bar Ask AI button must call triggerAskAI()"

    # PDF refactors selection logic into a reusable helper so both mouseup and
    # selectionchange can call it without duplicating code
    assert 'computePdfSelectionState' in resp_pdf.text, \
        "PDF: computePdfSelectionState helper must exist for shared mouseup/selectionchange logic"


def test_mobile_viewport_dvh_fix(client, create_test_epub, create_test_pdf):
    """
    Both readers use 100dvh (dynamic viewport height) so the layout fits the
    actual visible area on iOS/Android when browser chrome (address/toolbar) is shown.
    100vh is kept as a fallback for browsers that don't support dvh.
    viewport-fit=cover is required so the layout is not inset from the screen
    edges on devices with notches / Face ID.
    """
    epub_id = create_test_epub("test_dvh_epub")
    pdf_id = create_test_pdf("test_dvh_pdf")

    for label, book_id in [("EPUB", epub_id), ("PDF", pdf_id)]:
        text = client.get(f"/read/{book_id}").text
        assert '100dvh' in text, \
            f"{label}: must use 100dvh for dynamic viewport height on mobile"
        assert '100vh' in text, \
            f"{label}: must keep 100vh as fallback for browsers without dvh support"
        assert 'viewport-fit=cover' in text, \
            f"{label}: viewport-fit=cover required for safe-area handling on notched devices"


def test_epub_touch_quote_caching(client, create_test_epub):
    """
    On iOS, tapping a button clears the text selection before the JS onclick
    handler runs.  The EPUB reader caches the selected quote in currentEpubQuote
    when selectionchange fires so that triggerAnnotation and triggerAskAI can
    still read it after the selection has been cleared by the tap.

    Also verifies that the containment check uses closest() (upward DOM traversal,
    same as the PDF pattern) instead of contains(), which is more robust for the
    anchor nodes that iOS produces.
    """
    book_id = create_test_epub("test_epub_quote_cache")
    text = client.get(f"/read/{book_id}").text

    # Cache variable declared
    assert 'currentEpubQuote' in text, \
        "EPUB: currentEpubQuote cache variable must be declared"

    # Containment check uses closest() not contains()
    assert "closest('#book-content-div')" in text, \
        "EPUB: selectionchange must use closest('#book-content-div') for anchor node check"

    # triggerAnnotation falls back to cached quote when live selection is gone
    assert "getSelectedQuote() || currentEpubQuote" in text, \
        "EPUB: triggerAnnotation must fall back to currentEpubQuote if selection was cleared by tap"

    # triggerAskAI falls back to cached quote when live selection is gone
    assert "toString().trim() || currentEpubQuote" in text, \
        "EPUB: triggerAskAI must fall back to currentEpubQuote if selection was cleared by tap"


def test_epub_highlight_immediate_feedback(client, create_test_epub):
    """
    After creating a highlight annotation the sidebar should open to the
    annotations list immediately (same UX as notes and PDF).
    openThread() scrolls the new span into view and forces a compositor
    repaint on iOS — without this call the yellow span is invisible until
    another action triggers a re-render.

    Also verifies that clicking an existing highlight span opens the sidebar
    to that specific annotation (openThread), not just the generic open().
    """
    book_id = create_test_epub("test_epub_hl_feedback")
    text = client.get(f"/read/{book_id}").text

    # After creating a highlight, openThread is called (not skipped like before)
    assert "type === 'note' || type === 'highlight'" in text, \
        "EPUB: triggerAnnotation must call openThread for both 'note' and 'highlight' types"

    # Clicking an existing highlight span must call openThread (not bare open())
    assert "RightSidebar.openThread(ann.id)" in text, \
        "EPUB: highlight span onclick must call openThread(ann.id) to navigate the sidebar"
