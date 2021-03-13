import numpy as np

from ...expressions import Symbol
from ...relational_algebra import ColumnStr, NamedRelationalAlgebraFrozenSet
from ...relational_algebra_provenance import ProvenanceAlgebraSet


def make_prov_set(iterable, columns):
    return ProvenanceAlgebraSet(
        NamedRelationalAlgebraFrozenSet(columns, iterable),
        ColumnStr(columns[0]),
    )


def eq_prov_relations(pas1, pas2):
    assert isinstance(pas1, ProvenanceAlgebraSet)
    assert isinstance(pas2, ProvenanceAlgebraSet)
    pas1_sorted_np_cols = sorted(pas1.non_provenance_columns)
    pas2_sorted_np_cols = sorted(pas2.non_provenance_columns)
    assert pas1_sorted_np_cols == pas2_sorted_np_cols
    assert (
        pas1.value.projection(*pas1.non_provenance_columns).to_unnamed()
        == pas2.value.projection(*pas1.non_provenance_columns).to_unnamed()
    )
    # ensure the prov col names are different so we can join the sets
    c1 = Symbol.fresh().name
    c2 = Symbol.fresh().name
    x1 = pas1.value.rename_column(pas1.provenance_column, c1)
    x2 = pas2.value.rename_column(pas2.provenance_column, c2)
    joined = x1.naturaljoin(x2)
    probs = list(joined.projection(*(c1, c2)))
    for p1, p2 in probs:
        if isinstance(p1, float) and isinstance(p2, float):
            if not np.isclose(p1, p2):
                return False
        elif p1 != p2:
            return False
    return True
