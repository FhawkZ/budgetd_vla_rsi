# Public robot API contract for future bounded authors

This document describes the common permission boundary, not a new task-solving hint.
Only these seven methods are available to a skill:
- task_spec(): instruction and role-to-category mapping only. No criterion source, layout or evaluator state.
- observe(): camera-derived components and frozen CLIP role assignments. Includes ok/failure_code or roles and estimated table height. position_world comes from RGBD, not simulator object truth. Custom perception receives only RGB, depth in millimetres, and camera calibration; the camera transform and CLIP remain fixed.
- ee_pose(arm): measured simulation end-effector pose, seven numbers; arm is left or right.
- gripper_state(arm): commanded, measured and open. commanded is the previous control request; measured is the normalized real driver-joint position or null. open is command-derived. None is a direct contact/success oracle.
- move_pose(arm,pose): original native workspace/quaternion checks, planning latch reset and boolean API return retained. A true return is not proof of object/task success.
- gripper(arm,value): native open-scale command in [0,1], native latch and API boolean.
- wait(seconds): bounded by the common experiment wait_max and native simulation accounting.

Observe/move/gripper/wait consume the original primitive budget. Read-only task_spec/pose/gripper-state do not consume native primitive budget; an independent transport request cap still applies. No arbitrary files, imports, shell, networking, simulator handles, scorer or sealed evaluation. Validation and scoring stay outside author control.

Author outputs are exactly SKILL.md, skills.py, perception.py and rationale.md. Preserve original static syntax/atom/document contracts. All versions and rejected attempts are retained. Passing static checks does not authorize candidate execution or promotion. Current input manifests are preparation only: no author model calls or robot evaluation are authorized by this document.

Development feedback contains API returns and initial proprioception, not a continuous state trajectory or task success labels. Relative image references in the text packet do not grant arbitrary filesystem access or imply the author has viewed those images. A separate frozen request must specify any actual image attachments.
