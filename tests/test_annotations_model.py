import pytest
from annotations import AnnotationTarget

def test_annotation_target_legacy_rect():
    """
    Test that providing a legacy 'rect' (single list of floats) 
    is accepted and ideally accessible. 
    (Future: verify it migrates to 'rects' if we implement a validator)
    """
    data = {
        "chapter_index": 0,
        "page_num": 1,
        "rect": [0.1, 0.1, 0.5, 0.5]
    }
    target = AnnotationTarget(**data)
    assert target.chapter_index == 0
    assert target.page_num == 1
    # Check if 'rect' is still accessible or migrated
    # Based on plan, we might keep 'rect' as Optional or migrate it. 
    # Let's assume for now we perform migration in the model.
    
    if hasattr(target, "rects") and target.rects:
        assert len(target.rects) == 1
        assert target.rects[0] == [0.1, 0.1, 0.5, 0.5]
    else:
        # Fallback if migration isn't implemented yet, just ensure model accepts it
        assert target.rect == [0.1, 0.1, 0.5, 0.5]

def test_annotation_target_new_rects():
    """Test providing 'rects' (list of lists) directly."""
    data = {
        "chapter_index": 0,
        "page_num": 1,
        "rects": [
            [0.1, 0.1, 0.5, 0.1],
            [0.1, 0.2, 0.4, 0.1]
        ]
    }
    # This will fail until we update the model, which is expected for TDD/regression
    try:
        target = AnnotationTarget(**data)
        assert target.rects == [
            [0.1, 0.1, 0.5, 0.1],
            [0.1, 0.2, 0.4, 0.1]
        ]
    except Exception:
        pytest.fail("Model should accept 'rects'")

def test_annotation_target_mixed_priority():
    """Test that if both are provided, 'rects' takes precedence or both exist."""
    data = {
        "chapter_index": 0,
        "page_num": 1,
        "rect": [0.0, 0.0, 1.0, 1.0],
        "rects": [[0.1, 0.1, 0.2, 0.2]]
    }
    target = AnnotationTarget(**data)
    assert target.rects == [[0.1, 0.1, 0.2, 0.2]]
