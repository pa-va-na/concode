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
def exchange(a, b):
    """Both sides send their pending edits to each other, at the same time."""
    ops_a, ops_b = a.take_outbox(), b.take_outbox()
    for op in ops_a:
        b.apply(op)
    for op in ops_b:
        a.apply(op)


def shared_cat():
    alice, bob = Document("alice"), Document("bob")
    c = alice.insert_after(None, "c")
    a = alice.insert_after(c, "a")
    t = alice.insert_after(a, "t")
    exchange(alice, bob)
    assert bob.text() == "cat"
    return alice, bob, c, a, t


def test_concurrent_inserts_converge():
    alice, bob, c, a, t = shared_cat()
    alice.insert_after(c, "X")
    bob.insert_after(c, "Y")
    exchange(alice, bob)
    assert alice.text() == bob.text()
    assert len(alice.text()) == 5


def test_concurrent_insert_and_delete_converge():
    alice, bob, c, a, t = shared_cat()
    alice.delete(a)
    bob.insert_after(a, "s")
    exchange(alice, bob)
    assert alice.text() == bob.text() == "cst"