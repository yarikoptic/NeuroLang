import typing
from typing import AbstractSet

from ..datalog.expression_processing import EQ, conjunct_formulas
from ..datalog.instance import MapInstance
from ..expression_pattern_matching import add_match
from ..expression_walker import PatternWalker
from ..expressions import Constant, FunctionApplication, Symbol
from ..logic import TRUE, Implication, Union
from .cplogic.program import CPLogicProgram
from .expression_processing import (
    construct_within_language_succ_result,
    is_within_language_prob_query,
    within_language_succ_query_to_intensional_rule,
)
from .expressions import Condition, ProbabilisticPredicate


class QueryBasedProbFactToDetRule(PatternWalker):
    """
    Translate a query-based probabilistic fact to two rules. A deterministic
    rule that takes care of inferring the set of tuples in the probabilistic
    table and a probabilistic rule that transforms the result from the
    deterministic resolution into a proper probabilistic table by re-attaching
    the deterministically-obtained probabilities.

    For example, the rule `P(x) : f(x) :- Q(x)` is translated into the rules

        _f1_(_f2_, x) :- Q(x), _f2_ = f(x)
        P(x) : _f2_ :- _f1_(_f2_, x)

    where `_f1_` and `_f2_` are fresh symbols. Note: we make sure not to
    expose the resulting `_f1_` relation to the user, as it is not part of
    her program.

    """

    @add_match(
        Implication(ProbabilisticPredicate, ...),
        lambda implication: implication.antecedent != TRUE
        and not (
            isinstance(implication.antecedent, FunctionApplication)
            and implication.antecedent.functor.is_fresh
        ),
    )
    def query_based_probabilistic_fact(self, impl):
        prob_symb = Symbol.fresh()
        det_pred_symb = Symbol.fresh()
        eq_formula = EQ(prob_symb, impl.consequent.probability)
        det_antecedent = conjunct_formulas(impl.antecedent, eq_formula)
        det_consequent = det_pred_symb(prob_symb, *impl.consequent.body.args)
        det_rule = Implication(det_consequent, det_antecedent)
        prob_consequent = ProbabilisticPredicate(
            prob_symb, impl.consequent.body
        )
        prob_rule = Implication(prob_consequent, det_consequent)
        return self.walk(Union((det_rule, prob_rule)))


def _solve_within_language_prob_query(
    cpl: CPLogicProgram,
    rule: Implication,
    succ_prob_solver: typing.Callable,
    marg_prob_solver: typing.Callable,
) -> Constant[AbstractSet]:
    query = within_language_succ_query_to_intensional_rule(rule)
    if isinstance(rule.antecedent, Condition):
        provset = marg_prob_solver(query, cpl)
    else:
        provset = succ_prob_solver(query, cpl)
    relation = construct_within_language_succ_result(provset, rule)
    return relation


def _solve_for_probabilistic_rule(
    cpl: CPLogicProgram,
    rule: Implication,
    succ_prob_solver: typing.Callable,
):
    provset = succ_prob_solver(rule, cpl)
    relation = Constant[AbstractSet](
        provset.value,
        auto_infer_type=False,
        verify_type=False,
    )
    return relation


def compute_probabilistic_solution(
    det_edb,
    pfact_edb,
    pchoice_edb,
    prob_idb,
    succ_prob_solver,
    marg_prob_solver,
):
    solution = MapInstance()
    cpl = _build_probabilistic_program(
        det_edb, pfact_edb, pchoice_edb, prob_idb
    )
    for rule in prob_idb.formulas:
        if is_within_language_prob_query(rule):
            relation = _solve_within_language_prob_query(
                cpl, rule, succ_prob_solver, marg_prob_solver
            )
        else:
            relation = _solve_for_probabilistic_rule(
                cpl, rule, succ_prob_solver
            )
        solution[rule.consequent.functor] = Constant[AbstractSet](
            relation.value.to_unnamed()
        )
    return solution


def _build_probabilistic_program(det_edb, pfact_edb, pchoice_edb, prob_idb):
    cpl = CPLogicProgram()
    db_to_add_fun = [
        (det_edb, cpl.add_extensional_predicate_from_tuples),
        (pfact_edb, cpl.add_probabilistic_facts_from_tuples),
        (pchoice_edb, cpl.add_probabilistic_choice_from_tuples),
    ]
    for database, add_fun in db_to_add_fun:
        for pred_symb, expr in database.items():
            # handle set-based probabilistic tables
            if isinstance(expr, Constant[typing.AbstractSet]):
                ra_set = expr
            # handle query-based probabilistic facts
            elif isinstance(expr, Implication):
                # we know the rule is of the form
                # P(x_1, ..., x_n) : y :- Q(y, x_1, ..., x_n)
                # so the values can be retrieved from the EDB
                ra_set = det_edb[expr.antecedent.functor]
            add_fun(pred_symb, ra_set.value.unwrap())
    cpl.walk(prob_idb)
    return cpl
