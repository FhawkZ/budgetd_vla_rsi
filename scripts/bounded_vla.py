"""Versioned common execution surface. No LLM, file browsing, or action repair.

Prefix25 is an explicit adapter: upstream lingbot_act only accepts50. Prefix50
uses the same native RGB/state/language builder, inference and ee chunk_step.
"""
import copy
import numpy as np

class BudgetExceeded(RuntimeError): pass

class BoundedVLA:
    def __init__(self, env, model, build_observation, *, horizon=1200,
                 max_inferences=48, max_observations=48, max_requests=96):
        self.env,self.model,self.build_observation=env,model,build_observation
        self.horizon,self.max_inferences=horizon,max_inferences
        self.max_observations,self.max_requests=max_observations,max_requests
        self.inferences=self.observations=self.requests=0
        self.stopped=False
        self.language=env.get_task_language()
    def status(self):
        s=self.env.last_info['episode_status']
        return dict(stopped=self.stopped,terminal=bool(s['eval_success']),
                    native_actions=int(s['take_action_cnt']),
                    inferences=self.inferences,observations=self.observations,requests=self.requests,
                    remaining_inferences=self.max_inferences-self.inferences)
    def _observation(self):
        observation=self.build_observation()
        if observation['task_language']!=self.language:raise ValueError('native language changed')
        return observation
    def dispatch(self, request):
        if self.requests>=self.max_requests:raise BudgetExceeded('interface request cap')
        self.requests+=1  # invalid and failed requests also count
        if not isinstance(request,dict):raise ValueError('request must be a dict')
        action=request.get('action')
        if action=='stop' and set(request)=={'action'}:
            self.stopped=True;return self.status()
        state=self.status()
        if self.stopped or state['terminal'] or state['native_actions']>=self.horizon:
            raise BudgetExceeded('episode closed')
        if action=='observe' and set(request)=={'action'}:
            if self.observations>=self.max_observations:raise BudgetExceeded('observation cap')
            self.observations+=1
            return self._observation()
        if action!='execute_vla_chunk' or set(request)!={'action','use_length'}:
            raise ValueError('undeclared action or fields')
        length=request['use_length']
        if type(length) is not int or length not in (25,50):raise ValueError('allowed prefixes25/50')
        if self.inferences>=self.max_inferences:raise BudgetExceeded('inference cap')
        observation=self._observation()
        self.inferences+=1 # inference failure is charged and never retried here
        actions=self.model.infer(observation)
        if not isinstance(actions,np.ndarray) or actions.shape!=(50,16) or not np.isfinite(actions).all():
            raise ValueError('expected finite50x16absoluteEEF actions')
        selected=actions[:min(length,self.horizon-state['native_actions'])].copy()
        _,_,_,_,info=self.env.chunk_step(selected,action_type='ee',return_all_frames=False)
        after=self.status();delta=after['native_actions']-state['native_actions']
        if not 0<=delta<=len(selected):raise RuntimeError('native action counter out of contract')
        if int(info.get('executed_actions',0))!=delta:raise RuntimeError('native counts disagree')
        return dict(request=copy.deepcopy(request),before=state,after=after,
                    selected_actions=selected,executed_actions=delta,
                    native_episode_status=copy.deepcopy(self.env.last_info['episode_status']))
