from concode.document import Document


def test_type_and_delete():
    doc = Document("alice")
    c = doc.insert_after(None, "c")
    a = doc.insert_after(c, "a")
    doc.insert_after(a, "t")
    assert doc.text() == "cat"

    doc.delete(a)
    assert doc.text() == "ct"
    assert len(doc.chars) == 3  # the deleted 'a' is still stored