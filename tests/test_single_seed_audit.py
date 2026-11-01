import copy
import pytest
from audit_single_seed_validation import promotion_gate

def fixture():
    cases=[{'task':task,'seed':1,'role':role} for task in ('stack_blocks_two','handover_block') for role in ('baseline','candidate')]
    eps=[dict(c,status='completed') for c in cases]
    pairs=[dict(task='stack_blocks_two',baseline=True,candidate=True,initial_inputs_equal=True),dict(task='handover_block',baseline=False,candidate=True,initial_inputs_equal=True)]
    return cases,eps,pairs

def test_full_gate_only_positive_passes():
    c,e,p=fixture();assert promotion_gate(c,e,p)['promotable']
    p[1]['baseline']=True;assert not promotion_gate(c,e,p)['promotable']

def test_invalid_or_missing_cannot_hide_behind_valid_gain():
    c,e,p=fixture();e[0]['status']='scene_invalid'
    assert not promotion_gate(c,e,p)['promotable']
    e=fixture()[1][:-1]
    assert not promotion_gate(c,e,p)['promotable']

def test_retention_is_nonvacuous_and_per_case():
    c,e,p=fixture();p[0]['candidate']=False
    assert not promotion_gate(c,e,p)['promotable']
    p[0]['baseline']=False
    assert not promotion_gate(c,e,p)['promotable']

def test_duplicate_episode_rejected():
    c,e,p=fixture();e[1]=copy.deepcopy(e[0])
    with pytest.raises(ValueError):promotion_gate(c,e,p)
