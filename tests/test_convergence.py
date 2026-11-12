import random

from hypothesis import given, settings, strategies as st

from concode.document import Document


@settings(max_examples=500)
@given(st.integers(min_value=0, max_value=2**32), st.integers(min_value=5, max_value=80))
def test_three_replicas_converge(seed, steps):
    rng = random.Random(seed)
    docs = [Document(name) for name in ("alice", "bob", "carol")]
    log = []              # every operation, in the order it was created (like a server)
    cursor = [0, 0, 0]    # how far each person has read in the log

    def deliver_next(i):
        sender, op = log[cursor[i]]
        cursor[i] += 1
        if sender != i:   # you already applied your own edits
            docs[i].apply(op)

    for _ in range(steps):
        i = rng.randrange(3)
        if rng.random() < 0.6:                       # make an edit
            doc = docs[i]
            visible = [c.id for c in doc.chars if not c.deleted]
            if visible and rng.random() < 0.3:
                doc.delete(rng.choice(visible))
            else:
                after = rng.choice([None] + [c.id for c in doc.chars])
                doc.insert_after(after, rng.choice("abcdef"))
            for op in doc.take_outbox():
                log.append((i, op))
        elif cursor[i] < len(log):                   # receive one pending edit
            deliver_next(i)

    for i in range(3):                               # everyone catches up
        while cursor[i] < len(log):
            deliver_next(i)

    assert docs[0].text() == docs[1].text() == docs[2].text()
    ids = [[c.id for c in d.chars] for d in docs]
    assert ids[0] == ids[1] == ids[2]