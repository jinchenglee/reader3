import fitz
import os
import sys
import glob

def ocr_pdf(pdf_path):
    """
    Scans a PDF and adds a text layer to pages that are missing it using OCR.
    """
    print(f"Processing: {pdf_path}")
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return

    modified = False
    
    # Create a temporary output path
    output_path = pdf_path.replace(".pdf", "_ocr.pdf")
    
    for i, page in enumerate(doc):
        # Check if page has text
        text = page.get_text()
        # Threshold: if less than 50 chars, assume it's a scanned page (or blank)
        # We can also check for images to be sure it's not just a blank page
        has_images = len(page.get_images()) > 0
        
        if len(text.strip()) < 50 and has_images:
            print(f"Page {i+1}: undetected text ({len(text.strip())} chars), running OCR...", end="", flush=True)
            
            try:
                # full=True enables full page analysis
                # textpage = page.get_textpage_ocr(flags=3, language="eng", dpi=300, full=True)
                # We need to insert the text back into the page. 
                # Actually fitz doesn't support *modifying* the page in-place with OCR easily in one step 
                # to add a text layer *over* the image without re-drawing
                # BUT, we can use a pdfwriter or just use the highly convenient:
                # page.insert_pdf(src_doc, ...) ?? No.
                
                # Correct approach with PyMuPDF 1.20+:
                # Use a partial PDF from OCR and overlay it?
                # Or rely on `page.get_textpage_ocr()` just getting us the text, 
                # but to *save* it we need to insert it.
                
                # Wait, looking at PyMuPDF docs, `get_textpage_ocr` creates a TextPage.
                # To add the text to the PDF, we effectively need to overlay invisible text.
                # There isn't a one-line "convert this page to OCR'd page" method in core fitz 
                # exactly like `ocrmypdf`.
                
                # However, since v1.19.0, we can do this pattern:
                # 1. Get OCR text page
                # 2. Insert the text invisible over the mage?
                # Actually, `page.pdf_insert_text` isn't a thing.
                
                # Let's use the standard recipe for "OCR a page and replace it":
                # We can't easily "replace" the page content in-place with its OCR'd version 
                # without losing the original image quality unless we are careful.
                
                # SIMPLER APPROACH:
                # generate a new PDF page from the OCR result (image + text) and replace the old page?
                # No, that might re-compress images.
                
                # CORRECT APPROACH for "Adding Text Layer":
                # Only insert invisible text. 
                # PyMuPDF doesn't have high-level "insert invisible text from OCR" method.
                # But we can iterate over the text blocks from OCR and insert them using `page.insert_text`.
                
                # Let's try to get the text blocks and write them invisible.
                tp = page.get_textpage_ocr(flags=3, language="eng", dpi=150, full=True)
                
                # Now we iterate blocks and write them
                # render_mode=3 is 'invisible'
                # extractWORDS returns list of (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                words = tp.extractWORDS()
                
                for w in words:
                    # x0, y0, x1, y1, text, block, line, word
                    x0, y0, x1, y1, text, block, line, word = w
                    
                    # Create rect
                    rect = fitz.Rect(x0, y0, x1, y1)
                    
                    # Estimate fontsize (height of word box)
                    fontsize = y1 - y0
                    # Tesseract sometimes gives tight boxes, maybe scale slightly? 
                    # Actually fontsize usually matches height well.
                    
                    # Insert text invisible
                    # We use the bottom-left coordinate for insertion
                    page.insert_text((x0, y1), text, fontsize=fontsize, render_mode=3)
                                
                modified = True
                print(f" Done ({len(words)} words).")
                
            except Exception as e:
                print(f" Failed: {e}")
        else:
            # print(f"Page {i+1}: has text or no images, skipping.")
            pass

    if modified:
        print(f"Saving to {output_path} (fast)...")
        # Faster save: no garbage collection, no deflate
        doc.save(output_path)
        
        # Backup original and replace
        backup_path = pdf_path + ".bak"
        if not os.path.exists(backup_path):
            os.rename(pdf_path, backup_path)
            print(f"Backed up original to {backup_path}")
        
        os.rename(output_path, pdf_path)
        print(f"Replaced original with OCR'd version.")
    else:
        print("No pages needed OCR.")
        doc.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        
        # If target has "books/", strictly use it
        if "books/" in target:
             pdf_path = os.path.join(target, "original.pdf") if os.path.isdir(target) else target
             ocr_pdf(pdf_path)
        else:
            # Case 1: Full path to PDF
            if target.endswith(".pdf") and os.path.exists(target):
                ocr_pdf(target)
            else:
                # Case 2: Book ID or directory name in books/
                # Check exact match first
                possible_path = os.path.join("books", target, "original.pdf")
                if os.path.exists(possible_path):
                     ocr_pdf(possible_path)
                else:
                    # Glob search
                    search_pattern = os.path.join("books", f"*{target}*", "original.pdf")
                    found = glob.glob(search_pattern)
                    if found:
                        for p in found:
                            ocr_pdf(p)
                    else:
                        print(f"Could not find book matching '{target}'")
    else:
        print("Usage: python tools/ocr_book.py <book_directory_or_pdf>")
