import json

from concode.document import CharId, DeleteOp, InsertOp, Op


def _id_to_list(char_id):
    return None if char_id is None else [char_id.counter, char_id.client]


def _id_from_list(data):
    return None if data is None else CharId(data[0], data[1])


def encode(op: Op) -> str:
    if isinstance(op, InsertOp):
        return json.dumps({
            "type": "insert",
            "id": _id_to_list(op.id),
            "after": _id_to_list(op.after),
            "value": op.value,
        })
    return json.dumps({"type": "delete", "id": _id_to_list(op.id)})


def decode(text: str) -> Op:
    data = json.loads(text)
    if data["type"] == "insert":
        return InsertOp(
            _id_from_list(data["id"]),
            _id_from_list(data["after"]),
            data["value"],
        )
    return DeleteOp(_id_from_list(data["id"]))