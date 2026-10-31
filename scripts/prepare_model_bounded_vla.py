from pathlib import Path
import json,hashlib
root=Path('/root/autodl-tmp/budgeted-vla-rsi');runtime=Path('/root/autodl-tmp/Dex_runtime/agent-rsi')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=(root/'scripts/run_bounded_vla_pilot.py').read_text().replace('common_bounded_vla_schedule_diagnostic','common_reduced_model_controller_development')
s=s.replace("cfg['qwen_calls']==0", "cfg['max_qwen_calls_total']==64").replace("cfg['max_episodes']==4","cfg['max_episodes']==2").replace("cfg['max_vla_inferences_total']==192","cfg['max_vla_inferences_total']==96")
s=s.replace("[(x['task'],x['seed'],x['use_length']) for x in cfg['cases']]==[\n        ('stack_blocks_two',2026103011,50),('stack_blocks_two',2026103011,25),\n        ('handover_block',2026103012,50),('handover_block',2026103012,25)]", "[(x['task'],x['seed']) for x in cfg['cases']]==[('stack_blocks_two',2026103011),('handover_block',2026103012)]")
s=s.replace("cfg['total_wall_seconds']==4800", "cfg['total_wall_seconds']==2400")
a=s.index('        prefix_length=cfg[');b=s.index('        report["interface_status"]',a)
s=s[:a]+'''        from bounded_controller import Controller
        tools=json.loads((ROOT/'configs/bounded-vla-interface-v1.json').read_text())['tools']
        initial=harness.dispatch({'action':'observe'})
        # Check initial inputs even when the controller never chooses an action.
        initial_hashes={}
        for name,view in initial['views'].items():
            file=out/('initial-'+name+'.png');Image.fromarray(np.asarray(view['rgb'])).save(file);initial_hashes[name]=digest(file)
        assert initial_hashes==cfg['cases'][index]['initial_image_sha256']
        assert json.dumps(initial['robot_state'],sort_keys=True,default=lambda x:x.tolist())==json.dumps(cfg['cases'][index]['initial_robot_state'],sort_keys=True)
        report['initial_images_equal']=True;report['initial_state_equal']=True
        controller=Controller(tools,initial,'http://127.0.0.1:18029/v1/chat/completions',out/'controller',cfg['max_qwen_calls_per_episode'])
        for _ in range(cfg['max_qwen_calls_per_episode']):
            status=env.last_info['episode_status']
            if status['eval_success'] or status['take_action_cnt']>=cfg['horizon'] or harness.stopped:break
            try:
                decision=controller.decide({'remaining_inferences':48-harness.inferences,'remaining_observations':48-harness.observations,'remaining_native_actions':cfg['horizon']-int(status['take_action_cnt'])})
                report['qwen_calls']=controller.calls;save(out/'episode.json',report)
                append(out/'decisions.jsonl',{'call':controller.calls,'decision':decision})
                result=harness.dispatch(decision)
                if decision['action']=='observe':
                    controller.feedback({'observation_returned':True},result)
                elif decision['action']=='stop':
                    controller.feedback({'stopped':True});break
                else:
                    selected=result.pop('selected_actions');chosen=out/f"executed-prefix-{report['vla_inferences']:03d}.npy";np.save(chosen,selected)
                    result['selected_actions_sha256']=digest(chosen);result['selected_actions_shape']=list(selected.shape)
                    append(out/'chunks.jsonl',{'time':time.time(),'result':result,'robot_state':env.last_info['robot_state']})
                    # No scorer or task outcome supplied to the controller.
                    controller.feedback({'submitted_waypoints':len(selected),'native_action_counter_delta':result['executed_actions']})
                status=env.last_info['episode_status']
                report.update(native_actions=int(status['take_action_cnt']),native_eval_success=bool(status['eval_success']))
                save(out/'episode.json',report)
            except Exception as exc:
                report.update(controller_error=repr(exc),qwen_calls=controller.calls)
                # Closed policy failure: no repaired arguments, retries or forced motion.
                break
''' + s[b:]
s=s.replace('else "inference_cap"','else ("controller_error" if report.get("controller_error") else ("controller_stop" if harness.stopped else "controller_call_cap"))')
s=s.replace('One development scene; no high-level Agent, learning, forgetting or RSI evidence.','One development scene; reduced autonomous controller adaptation, no learning, forgetting or RSI evidence.')
s=s.replace('["scripts/run_bounded_vla_pilot.py","scripts/bounded_vla.py"]','["scripts/run_model_bounded_vla.py","scripts/bounded_vla.py","scripts/bounded_controller.py"]')
s=s.replace('strict_rsi_rounds=0)\n        save(out / "report.json", report)', 'strict_rsi_rounds=0, qwen_calls=sum(x["result"].get("qwen_calls",0) for x in report["episodes"]))\n        save(out / "report.json", report)')
s=s.replace('        run(cfg, args.config.resolve(), args.protocol_sha256)', '''        from qwen_service_owner import service
        def timeout(*unused):raise TimeoutError('overall model-controller wall limit')
        signal.signal(signal.SIGALRM,timeout);signal.alarm(2700)
        try:
            with service(cfg):run(cfg, args.config.resolve(), args.protocol_sha256)
        finally:signal.alarm(0)''')
s=s.replace('Default is CPU-only configuration checking.', 'Autonomous reduced tool controller; explicit adaptation, not native RPent.\nDefault is CPU-only configuration checking.')
runner=root/'scripts/run_model_bounded_vla.py';assert not runner.exists();runner.write_text(s)
base=json.loads((root/'configs/bounded-vla-pair4-20261031-1130.json').read_text());base.update(run_id='bounded-controller-dev64-20261031-1700',classification='common_reduced_model_controller_development',max_episodes=2,max_vla_inferences_total=96,max_qwen_calls_total=64,max_qwen_calls_per_episode=32,total_wall_seconds=2400,runner_sha256=sha(runner),qwen_calls='bounded64',skill_updates=0)
base['cases']=[base['cases'][0],base['cases'][2]]
for c in base['cases']:c.pop('use_length')
q=json.loads((root/'configs/bounded-controller-qual4-20261031-1630.json').read_text());report=runtime/'outputs/bounded-controller-qual4-20261031-1630/report.json';assert json.loads(report.read_text())['status']=='passed'
base.update(model_id=q['model_id'],qwen_asset_receipt=q['asset_receipt'],qwen_asset_receipt_sha256=q['asset_receipt_sha256'],qualification_report=str(report.relative_to(runtime)),qualification_report_sha256=sha(report),controller_code_sha256={rel:sha(root/rel) for rel in ['scripts/bounded_controller.py','scripts/qwen_service_owner.py','scripts/serve_qwen_structured30b.py','scripts/budget_proxy30b.py','scripts/structured_qwen.py','configs/bounded-vla-interface-v1.json']})
base['scope']='Independent64Qwen+96VLAmaximum,32Qwen/task. Same2fixeddevelopmentcases, no retries/resampling/forcedactions. Initial native observations checked even if no execution. Qwen gets native language/RGB/state and counters, no scorer. Stop controller upon any malformed request/error, stop episode at native success/horizon/modelstop/cap. No learning; compare functional fixed50 only descriptively; all model/VLA/setup costs separately.'
p=root/'configs/bounded-controller-dev64-20261031-1700.json';assert not p.exists();p.write_text(json.dumps(base,indent=2)+'\n');print('SHA',sha(p))
