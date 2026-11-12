from concode.document import CharId, DeleteOp, InsertOp
from concode.protocol import decode, encode


def test_insert_round_trip():
    op = InsertOp(CharId(3, "alice"), CharId(2, "alice"), "x")
    assert decode(encode(op)) == op


def test_insert_at_start_round_trip():
    op = InsertOp(CharId(1, "bob"), None, "h")
    assert decode(encode(op)) == op


def test_delete_round_trip():
    op = DeleteOp(CharId(5, "carol"))
    assert decode(encode(op)) == op