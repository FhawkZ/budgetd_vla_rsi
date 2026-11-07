"""CPU stdlib tests with SYNTHETIC pinned resources only (no real task/solve code)."""
import copy, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_rsi_phone_author_inputs as M

SECRET = "SECRET_EVALUATOR_TOKEN"
LATER = "LATER_ACTION_TOKEN"


def h(b): return hashlib.sha256(b).hexdigest()


def observe_row(**over):
    role = lambda c: {"category": c, "position_world": [0.1, 0.2, 0.75], "xyxy": [1, 2, 30, 40],
                      "point_count": 120, "score": 0.93, "yaw": 1.2, "label": SECRET}
    row = {"i": 0, "method": "observe", "sim_steps": 0, "args": {},
           "result": {"ok": True, "roles": {"phone": role("phone"), "stand": role("stand"),
                                            "distractor": role(SECRET)},
                      "table_z_estimate": 0.74, "episode_label": SECRET}}
    row.update(over)
    return row


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.repo, self.runtime, self.ep = self.root / "repo", self.root / "runtime", self.root / "ep"
        self.files = {
            self.ep / "task-spec.json": json.dumps({"instruction": "put the phone on the stand",
                                                    "roles": {"phone": "phone", "stand": "stand"},
                                                    "criterion_source": SECRET}),
            self.ep / "initial-proprioception.json": json.dumps({a: {"ee_pose": [0, 0, 1, 1, 0, 0, 0],
                "gripper": {"commanded": 1.0, "measured": None, "open": True}} for a in ("left", "right")}),
            self.ep / "calls.jsonl": json.dumps(observe_row()) + "\n" + json.dumps(
                {"i": 1, "method": "move_pose", "args": {"note": LATER}, "result": {"score": SECRET}}) + "\n",
            self.ep / "observation_00/calibration.json": json.dumps({
                "intrinsic_cv": [[500, 0, 112], [0, 500, 112], [0, 0, 1]],
                "extrinsic_cv": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
                "cam2world_gl": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "secret": SECRET}),
            self.repo / M.API_DOC: "# Synthetic API\n- observe(): synthetic\n",
            self.runtime / M.TASK_TEMPLATE: ("# Native header with privileges " + SECRET + "\n\n" + M.START +
                                             "\nDeliver files for {{task}}; keep {{other}} raw.\n\n" + M.END +
                                             "\nAPI tail " + SECRET + "\n"),
        }
        sk = self.runtime / M.VENDOR / "frozen_skills" / M.SKILL_DIR
        for n in M.INHERITED:
            self.files[sk / n] = "synthetic inherited %s placeholder\n" % n
        # traps that must never be read or leaked
        self.files[self.ep / "episode.json"] = json.dumps({"success": True, "x": SECRET})
        self.files[self.ep / "observation_01/calibration.json"] = SECRET
        for p, t in self.files.items():
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(t)

    def write(self, path, text):
        path.write_text(text); return self

    def pins(self):
        f = lambda p: {"bytes": len(p.read_bytes()), "sha256": h(p.read_bytes())}
        sk = self.runtime / M.VENDOR / "frozen_skills" / M.SKILL_DIR
        return {"public_task_template_sha256": h((self.runtime / M.TASK_TEMPLATE).read_bytes()),
                "api_doc_sha256": h((self.repo / M.API_DOC).read_bytes()),
                "observation_source": {n: f(self.ep / n) for n in M.EPISODE_FILES},
                "inherited_files": {n: dict(f(sk / n), path=M.SKILL_DIR + "/" + n) for n in M.INHERITED}}

    def run(self, pins=None, out="out"):
        return M.prepare(self.repo, self.runtime, self.ep, self.root / out, pins or self.pins())


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.fx = Fixture(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def all_text(self, d):
        return "".join(p.read_text() for p in Path(d).rglob("*") if p.is_file())

    def test_common_equal_initial_differs_and_manifest(self):
        m = self.fx.run(); out = self.fx.root / "out"
        a, b = out / "conditions/from_scratch", out / "conditions/inheritance"
        for k in ("task_contract.md", "api_doc.md", "task_public_spec.json", "sensor_packet.json", "response_contract.json"):
            self.assertEqual((a / "resources" / k).read_bytes(), (b / "resources" / k).read_bytes())
            self.assertEqual((a / "resources" / k).read_bytes(), (out / "common" / k).read_bytes())
        for n in M.OUTPUT_FILES:
            self.assertEqual((a / "initial" / n).read_text(), "")
        for n in M.INHERITED:
            self.assertEqual((b / "initial" / n).read_bytes(), self.fx.files[self.fx.runtime / M.VENDOR / "frozen_skills" / M.SKILL_DIR / n].encode())
        self.assertEqual((b / "initial/rationale.md").read_text(), "")
        ma, mb = (json.loads((x / "messages.json").read_text()) for x in (a, b))
        self.assertEqual(ma["messages"][0], mb["messages"][0])
        ua, ub = ma["messages"][1]["content"], mb["messages"][1]["content"]
        cut = ua.index("# Condition:"); self.assertEqual(ua[:cut], ub[:ub.index("# Condition:")])
        self.assertNotEqual(ua, ub)
        contract = (out / "common/task_contract.md").read_text()
        self.assertTrue(contract.startswith(M.START)); self.assertNotIn(M.END, contract)
        self.assertIn("place_phone_stand", contract); self.assertIn("{{other}}", contract); self.assertNotIn("{{task}}", contract)
        self.assertEqual(m["stage"], "PREPARED_INPUTS_NOT_RUNNABLE"); self.assertEqual(m["model_calls"], 0)
        self.assertFalse(m["download_authorized"] or m["load_authorized"] or m["rollout_authorized"])
        self.assertEqual((m["limits"]["max_input_tokens"], m["limits"]["max_output_tokens"], m["limits"]["context_tokens"]), (24000, 8192, 32768))
        self.assertEqual(m["limits"]["token_count_status"], "TOKENIZER_CHECK_PENDING")
        for rel, info in m["outputs"].items():
            self.assertEqual(h((out / rel).read_bytes()), info["sha256"])
        # deterministic
        self.fx.run(out="out2")
        for rel in m["outputs"]:
            self.assertEqual((out / rel).read_bytes(), (self.fx.root / "out2" / rel).read_bytes())

    def test_no_leakage(self):
        self.fx.run(); text = self.all_text(self.fx.root / "out")
        for bad in (SECRET, LATER, "criterion_source", '"score"', '\\"score\\"', '"yaw"', '"label"', '"episode_label"', "distractor", "move_pose", str(self.fx.root)):
            self.assertNotIn(bad, text, bad)
        sp = json.loads((self.fx.root / "out/common/sensor_packet.json").read_text())
        self.assertEqual(set(sp["first_observe"]["roles"]), {"phone", "stand"})
        self.assertEqual(set(sp["first_observe"]["roles"]["phone"]), {"category", "position_world", "xyxy", "point_count"})
        self.assertEqual(sp["first_observe"]["table_z_estimate"], 0.74)

    def test_hash_mismatch_rejected(self):
        pins = self.fx.pins()
        self.fx.write(self.fx.repo / M.API_DOC, "# tampered API\n")
        with self.assertRaises(ValueError): self.fx.run(pins)
        self.assertFalse((self.fx.root / "out").exists())
        bad = copy.deepcopy(self.fx.pins()); bad["inherited_files"]["skills.py"]["path"] = "../other/skills.py"
        with self.assertRaises(ValueError): self.fx.run(bad)

    def test_symlink_refused(self):
        p = self.fx.ep / "task-spec.json"; real = self.fx.root / "real.json"
        os.rename(p, real); os.symlink(real, p)
        with self.assertRaises((ValueError, OSError)): self.fx.run()
        self.assertFalse((self.fx.root / "out").exists())

    def bad_case(self, path, text):
        self.fx.write(path, text)
        with self.assertRaises(ValueError): self.fx.run()
        self.assertFalse((self.fx.root / "out").exists())

    def test_malformed_first_row_rejected(self):
        c = self.fx.ep / "calls.jsonl"
        for row in (observe_row(i=1), observe_row(method="wait"), observe_row(sim_steps=3), observe_row(args={"x": 1}),
                    observe_row(result={"ok": False}), observe_row(i=True)):
            with self.subTest(row=row): self.bad_case(c, json.dumps(row) + "\n")
        r = observe_row(); r["result"]["roles"]["phone"]["position_world"] = [0, 1]
        self.bad_case(c, json.dumps(r) + "\n")
        r = observe_row(); r["result"]["roles"]["stand"]["xyxy"] = [0, 1, 2, "3"]
        self.bad_case(c, json.dumps(r) + "\n")
        self.bad_case(c, json.dumps(observe_row()).replace("0.74", "NaN") + "\n")
        self.bad_case(c, "not json\n")

    def test_type_finite_calibration_rejected(self):
        cal = self.fx.ep / "observation_00/calibration.json"
        good = json.loads(cal.read_text())
        for k, v in (("intrinsic_cv", [[1, 0], [0, 1]]), ("extrinsic_cv", [[1, 0, 0, 0]] * 4), ("cam2world_gl", [[1e999] * 4] * 4)):
            with self.subTest(k=k): self.bad_case(cal, json.dumps(dict(good, **{k: v})).replace("Infinity", "1e999"))
        self.bad_case(cal, json.dumps(dict(good, intrinsic_cv=[[True, 0, 0], [0, 1, 0], [0, 0, 1]])))
        pr = self.fx.ep / "initial-proprioception.json"
        self.bad_case(pr, json.dumps({a: {"ee_pose": [0] * 6, "gripper": {"commanded": 1, "measured": None, "open": True}} for a in ("left", "right")}))
        self.bad_case(pr, json.dumps({a: {"ee_pose": [0] * 7, "gripper": {"commanded": "1", "measured": None, "open": True}} for a in ("left", "right")}))

    def test_overwrite_refused(self):
        (self.fx.root / "out").mkdir()
        with self.assertRaises(FileExistsError): self.fx.run()
        self.assertEqual(list((self.fx.root / "out").iterdir()), [])

    def test_template_marker_absence_rejected(self):
        t = self.fx.runtime / M.TASK_TEMPLATE
        orig = t.read_text()
        for txt in (orig.replace(M.START, "## Something else"), orig.replace(M.END, "## Other"), orig + "\n" + M.START + "\n"):
            with self.subTest(): self.bad_case(t, txt)


if __name__ == "__main__":
    unittest.main()
