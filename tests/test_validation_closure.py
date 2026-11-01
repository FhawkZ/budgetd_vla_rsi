import pytest
from audit_paired_validation import selection_status


def test_censoring_cannot_be_dropped_or_called_policy_failure():
    expected = [dict(task='old', seed=1, role='baseline'), dict(task='old', seed=1, role='candidate')]
    baseline = dict(expected[0], status='completed', native_eval_success=True)
    censored = dict(expected[1], status='infrastructure_error', native_eval_success=None)
    assert selection_status(expected, [baseline, censored]) == 'inconclusive_incomplete_panel_no_promotion'
    assert selection_status(expected, [baseline]) == 'inconclusive_incomplete_panel_no_promotion'
    completed = dict(expected[1], status='completed', native_eval_success=False)
    assert selection_status(expected, [baseline, completed]) == 'complete_requires_full_predeclared_gate'
    with pytest.raises(ValueError):
        selection_status(expected, [baseline, baseline])
    with pytest.raises(ValueError):
        selection_status(expected, [censored, baseline])
