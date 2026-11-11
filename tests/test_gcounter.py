from hypothesis import given, strategies as st

from concode.gcounter import GCounter


def make(counts):
    c = GCounter("x")
    c.counts = dict(counts)
    return c


def merged(x, y):
    result = make(x.counts)
    result.merge(y)
    return result


counts = st.dictionaries(
    st.sampled_from(["a", "b", "c"]),
    st.integers(min_value=0, max_value=100),
)


def test_two_replicas_converge():
    a, b = GCounter("a"), GCounter("b")
    a.increment()
    a.increment()
    b.increment()
    a.merge(b)
    b.merge(a)
    assert a.value() == b.value() == 3


@given(counts, counts)
def test_merge_is_commutative(x, y):
    assert merged(make(x), make(y)).counts == merged(make(y), make(x)).counts


@given(counts, counts, counts)
def test_merge_is_associative(x, y, z):
    left = merged(merged(make(x), make(y)), make(z))
    right = merged(make(x), merged(make(y), make(z)))
    assert left.counts == right.counts


@given(counts)
def test_merge_is_idempotent(x):
    assert merged(make(x), make(x)).counts == x