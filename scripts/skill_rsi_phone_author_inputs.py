"""Owner-side builder of pinned place_phone_stand author INPUTS (stdlib, CPU only).

Prepares two deterministic conditions (from_scratch, inheritance) for a future
offline author runner.  It never calls a model, never imports/executes any
source file it reads, never downloads, never loads weights and never runs a
robot or skill.  `pins` is trusted owner configuration; nothing here accepts
paths or pins from model output.

Only these exact files are opened (no directory listing/recursive discovery):
  durable_episode/{task-spec.json, initial-proprioception.json, calls.jsonl,
                   observation_00/calibration.json}
  repo/docs/skill-rsi-author-api-v1.md
  runtime/vendor/<SKILL_RSI>/runtime/prompts/TASK.md
  runtime/vendor/<SKILL_RSI>/frozen_skills/place_phone_stand_10bbaf/{SKILL.md,skills.py,perception.py}
episode.json, scorer, layout and other observations are never read.
"""
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

TASK = "place_phone_stand"
VENDOR = "vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4"
SKILL_DIR = "place_phone_stand_10bbaf"
API_DOC = "docs/skill-rsi-author-api-v1.md"
TASK_TEMPLATE = VENDOR + "/runtime/prompts/TASK.md"
EPISODE_FILES = ("task-spec.json", "initial-proprioception.json", "calls.jsonl",
                 "observation_00/calibration.json")
INHERITED = ("SKILL.md", "skills.py", "perception.py")
OUTPUT_FILES = ("SKILL.md", "skills.py", "perception.py", "rationale.md")
ROLES = ("phone", "stand")
START = "## What to deliver each attempt"
END = "## The API your skills use"
MAX_INPUT_FILE_BYTES = 262144
MAX_TOTAL_INPUT_BYTES = 1048576
LIMITS = {
    "max_input_tokens": 24000, "max_output_tokens": 8192, "context_tokens": 32768,
    "total_responses": 2, "responses_per_condition": 1, "retries": 0,
    "partial_repair": False,
    "token_count_status": "TOKENIZER_CHECK_PENDING",
    "token_count_note": ("byte sizes are not token counts; a future runner must count with the "
                         "pinned tokenizer and reject (never truncate) any input over max_input_tokens"),
}
_HEX = re.compile(r"^[0-9a-f]{64}$")


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- pins / reads
def _check_pins(pins):
    if not isinstance(pins, dict):
        raise ValueError("pins must be an owner-supplied object")
    expect = {"public_task_template_sha256", "observation_source", "api_doc_sha256", "inherited_files"}
    if set(pins) != expect:
        raise ValueError("unexpected pin keys")
    for k in ("public_task_template_sha256", "api_doc_sha256"):
        if not isinstance(pins[k], str) or not _HEX.match(pins[k]):
            raise ValueError("bad pin " + k)
    obs = pins["observation_source"]
    if not isinstance(obs, dict) or set(obs) != set(EPISODE_FILES):
        raise ValueError("observation pins must name exactly the four approved files")
    inh = pins["inherited_files"]
    if not isinstance(inh, dict) or set(inh) != set(INHERITED):
        raise ValueError("inherited pins must name exactly the three public files")
    for name, p in inh.items():
        if p.get("path") != SKILL_DIR + "/" + name:
            raise ValueError("inherited pin path is fixed, not configurable")
    for p in list(obs.values()) + list(inh.values()):
        if not _HEX.match(str(p.get("sha256", ""))) or type(p.get("bytes")) is not int or not 0 < p["bytes"] <= MAX_INPUT_FILE_BYTES:
            raise ValueError("bad file pin")


def _read_pinned(path, digest, size=None):
    """Read one exact regular file without following a final symlink; verify hash."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("symlink input refused: " + path.name)
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("input is not a regular file: " + path.name)
        if st.st_size > MAX_INPUT_FILE_BYTES:
            raise ValueError("input exceeds byte cap: " + path.name)
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(MAX_INPUT_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_INPUT_FILE_BYTES or (size is not None and len(data) != size):
        raise ValueError("input size mismatch: " + path.name)
    if sha(data) != digest:
        raise ValueError("pinned hash mismatch: " + path.name)
    return data


def _reject_constant(c):
    raise ValueError("non-finite JSON constant " + c)


def _json(b, what):
    try:
        return json.loads(b.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("malformed JSON in " + what) from e


# ---------------------------------------------------------------- validators
def _num(x, what):
    if type(x) not in (int, float) or not math.isfinite(x):
        raise ValueError("non-finite or non-numeric " + what)
    return x


def _vec(x, n, what):
    if not isinstance(x, list) or len(x) != n:
        raise ValueError("bad shape " + what)
    return [_num(v, what) for v in x]


def _mat(x, r, c, what):
    if not isinstance(x, list) or len(x) != r:
        raise ValueError("bad shape " + what)
    return [_vec(row, c, what) for row in x]


def _project_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("instruction"), str) or not spec["instruction"].strip():
        raise ValueError("task spec instruction")
    roles = spec.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES) or not all(isinstance(v, str) and v for v in roles.values()):
        raise ValueError("task spec roles must be exactly phone/stand -> category")
    # criterion_source and every other field are dropped deliberately.
    return {"task": TASK, "instruction": spec["instruction"], "roles": {r: roles[r] for r in ROLES}}


def _project_proprio(p):
    if not isinstance(p, dict):
        raise ValueError("proprioception type")
    out = {}
    for arm in ("left", "right"):
        a = p.get(arm)
        if not isinstance(a, dict) or not isinstance(a.get("gripper"), dict):
            raise ValueError("proprioception arm " + arm)
        g = a["gripper"]
        measured = g.get("measured")
        if measured is not None:
            _num(measured, "gripper.measured")
        if not isinstance(g.get("open"), bool):
            raise ValueError("gripper.open must be boolean")
        out[arm] = {"ee_pose": _vec(a.get("ee_pose"), 7, arm + ".ee_pose"),
                    "gripper": {"commanded": _num(g.get("commanded"), "gripper.commanded"),
                                "measured": measured, "open": g["open"]}}
    return out


def _project_calibration(c):
    if not isinstance(c, dict):
        raise ValueError("calibration type")
    return {"intrinsic_cv": _mat(c.get("intrinsic_cv"), 3, 3, "intrinsic_cv"),
            "extrinsic_cv": _mat(c.get("extrinsic_cv"), 3, 4, "extrinsic_cv"),
            "cam2world_gl": _mat(c.get("cam2world_gl"), 4, 4, "cam2world_gl")}


def _project_first_observe(calls_bytes):
    try:
        text = calls_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("calls.jsonl encoding") from e
    first = text.split("\n", 1)[0]  # FIRST ROW ONLY; later actions never parsed
    row = _json(first.encode("utf-8"), "calls.jsonl first row")
    if not isinstance(row, dict):
        raise ValueError("first row type")
    if type(row.get("i")) is not int or row["i"] != 0 or row.get("method") != "observe" \
            or type(row.get("sim_steps")) is not int or row["sim_steps"] != 0 or row.get("args") != {}:
        raise ValueError("first row must be i=0 observe, sim_steps=0, args={}")
    res = row.get("result")
    if not isinstance(res, dict) or res.get("ok") is not True:
        raise ValueError("first observe result.ok must be true")
    roles = res.get("roles")
    if not isinstance(roles, dict) or not set(ROLES) <= set(roles):
        raise ValueError("first observe must report phone and stand roles")
    proj = {}
    for r in ROLES:
        o = roles[r]
        if not isinstance(o, dict) or not isinstance(o.get("category"), str):
            raise ValueError("role entry " + r)
        pc = o.get("point_count")
        if type(pc) is not int or pc < 0:
            raise ValueError("point_count " + r)
        proj[r] = {"category": o["category"], "position_world": _vec(o.get("position_world"), 3, r + ".position_world"),
                   "xyxy": _vec(o.get("xyxy"), 4, r + ".xyxy"), "point_count": pc}
    out = {"ok": True, "roles": proj}
    if "table_z_estimate" in res and res["table_z_estimate"] is not None:
        out["table_z_estimate"] = _num(res["table_z_estimate"], "table_z_estimate")
    return out


def _extract_contract(template):
    try:
        text = template.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("TASK.md encoding") from e
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("TASK.md section markers missing or ambiguous")
    s, e = text.index(START), text.index(END)
    if e <= s:
        raise ValueError("TASK.md markers out of order")
    return text[s:e].replace("{{task}}", TASK)  # only {{task}} is substituted


def _dumps(x):
    return json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


SYSTEM = (
    "You are an offline skill author for the robot task place_phone_stand. You have NO filesystem, "
    "shell, network, tool, simulator, scorer or image access, and nothing you write is executed during "
    "this exchange. Use only the text resources in the user message. They include an EXTRACTED excerpt "
    "of the official author task file, not the full native author privileges. Sensor values are "
    "camera/proprioception ESTIMATES at the initial state, not object ground truth and not a trajectory. "
    "Reply with exactly one JSON object whose keys are exactly SKILL.md, skills.py, perception.py and "
    "rationale.md, each a string holding the complete file. No Markdown fence, no prose outside the "
    "JSON, no tool calls. There is one response and no retry or partial repair.")

RESPONSE_CONTRACT = {
    "format": "single JSON object, no Markdown envelope, no surrounding text",
    "keys_exact": list(OUTPUT_FILES),
    "values": "complete file contents as strings (complete artifact, not a diff)",
    "tools": "none available", "execution": "none during authoring",
    "responses": 1, "retries": 0, "partial_repair": False,
}


def _user_message(common, condition, initial):
    parts = [
        "# Resource 1: extracted official author contract (TASK.md excerpt)\n\n" + common["task_contract.md"],
        "# Resource 2: public author API (docs/skill-rsi-author-api-v1.md, exact)\n\n" + common["api_doc.md"],
        "# Resource 3: public task spec (instruction and roles only)\n\n" + common["task_public_spec.json"],
        "# Resource 4: approved initial sensor packet (estimates; initial state only; text, no images)\n\n"
        + common["sensor_packet.json"],
        "# Resource 5: response contract\n\n" + common["response_contract.json"],
        "# Condition: %s\nInitial files (verbatim; an empty string means the file is empty):\n\n" % condition
        + _dumps(initial),
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------- main entry
def prepare(repo, runtime, durable_episode, destination, pins):
    _check_pins(pins)
    dest = Path(destination)
    if os.path.lexists(dest):
        raise FileExistsError(str(dest))
    repo, runtime, ep = Path(repo), Path(runtime), Path(durable_episode)
    src, prov, total = {}, {}, 0

    def take(logical, path, digest, size=None):
        nonlocal total
        b = _read_pinned(path, digest, size)
        total += len(b)
        if total > MAX_TOTAL_INPUT_BYTES:
            raise ValueError("total input byte cap")
        src[logical] = b
        prov[logical] = {"bytes": len(b), "sha256": sha(b)}
        return b

    for name in EPISODE_FILES:
        p = pins["observation_source"][name]
        take("episode/" + name, ep / name, p["sha256"], p["bytes"])
    take(API_DOC, repo / API_DOC, pins["api_doc_sha256"])
    take(TASK_TEMPLATE, runtime / TASK_TEMPLATE, pins["public_task_template_sha256"])
    for name in INHERITED:
        p = pins["inherited_files"][name]
        take(VENDOR + "/frozen_skills/" + p["path"], runtime / VENDOR / "frozen_skills" / p["path"], p["sha256"], p["bytes"])

    spec = _project_spec(_json(src["episode/task-spec.json"], "task-spec.json"))
    sensor = {
        "kind": "approved_initial_sensor_packet",
        "notes": ["values are sensor/perception estimates, not object truth",
                  "initial state only; no continuous trajectory, later actions or outcomes",
                  "text only; no images attached"],
        "initial_proprioception": _project_proprio(_json(src["episode/initial-proprioception.json"], "proprioception")),
        "camera_calibration_observation_00": _project_calibration(
            _json(src["episode/observation_00/calibration.json"], "calibration")),
        "first_observe": _project_first_observe(src["episode/calls.jsonl"]),
    }
    try:
        api_text = src[API_DOC].decode("utf-8")
        inherited_text = {n: src[VENDOR + "/frozen_skills/" + SKILL_DIR + "/" + n].decode("utf-8") for n in INHERITED}
    except UnicodeDecodeError as e:
        raise ValueError("public text encoding") from e
    common = {
        "task_contract.md": _extract_contract(src[TASK_TEMPLATE]),
        "api_doc.md": api_text,
        "task_public_spec.json": _dumps(spec),
        "sensor_packet.json": _dumps(sensor),
        "response_contract.json": _dumps(RESPONSE_CONTRACT),
    }
    initials = {
        "from_scratch": {n: "" for n in OUTPUT_FILES},
        "inheritance": dict(inherited_text, **{"rationale.md": ""}),
    }
    files = {}
    for k, v in common.items():
        files["common/" + k] = v
    for cond, init in initials.items():
        base = "conditions/%s/" % cond
        for n in OUTPUT_FILES:
            files[base + "initial/" + n] = init[n]
        for k, v in common.items():
            files[base + "resources/" + k] = v
        msgs = {"condition": cond, "image_attachments": 0, "tools": [],
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": _user_message(common, cond, init)}]}
        files[base + "messages.json"] = _dumps(msgs)
    encoded = {k: v.encode("utf-8") for k, v in files.items()}
    manifest = {
        "stage": "PREPARED_INPUTS_NOT_RUNNABLE", "task": TASK,
        "conditions": ["from_scratch", "inheritance"],
        "condition_difference": ("intended treatment: inheritance receives the three published public "
                                 "skill files (which may contain public author priors); from_scratch "
                                 "receives empty files. Information is NOT identical across conditions."),
        "model_calls": 0, "download_authorized": False, "load_authorized": False,
        "rollout_authorized": False, "image_attachments": 0, "limits": LIMITS,
        "source_provenance": prov,
        "not_read": ["episode.json", "scorer", "layout", "other observations", "calls.jsonl rows after the first are hashed but not parsed or exposed"],
        "outputs": {k: {"bytes": len(b), "sha256": sha(b)} for k, b in sorted(encoded.items())},
        "limitations": ["prepared input projection is not a perception quality evaluation",
                        "tokenizer check pending", "no author/model call made",
                        "builder is not an execution sandbox"],
    }
    # All checks passed: create destination exclusively, then write each file exclusively.
    os.mkdir(dest)
    for rel, b in sorted(encoded.items()) + [("manifest.json", _dumps(manifest).encode("utf-8"))]:
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(b)
            f.flush()
            os.fsync(f.fileno())
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    for a in ("--repo", "--runtime", "--episode", "--out", "--pins"):
        ap.add_argument(a, required=True)
    a = ap.parse_args()
    with open(a.pins, "rb") as f:
        owner_pins = _json(f.read(), "pins")
    print(_dumps(prepare(a.repo, a.runtime, a.episode, a.out, owner_pins)))
