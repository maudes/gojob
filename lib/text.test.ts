/**
 * Tests for the helpers the screens use. Run with `npm run test:web` (Node's built-in test runner,
 * no extra packages). The same rules are tested for the backend in backend/tests/test_core.py.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { applyToText, diffOps, tier, trackerTSV, TRACKER_COLUMNS, type DiffOp } from "./text.ts";

const shown = (ops: DiffOp[], hide: DiffOp["type"]) => ops.filter((o) => o.type !== hide).map((o) => o.text).join("");

const PAIRS: [string, string][] = [
  ["Aligned firmware teams", "Managed stakeholders across firmware teams"],
  ["Owned roadmap", "Owned the roadmap"],
  ["Led a team of 5 engineers to ship BLE firmware", "Led a cross-functional team of 5 engineers to ship BLE connectivity firmware, cutting defects by [X%]"],
  ["Product Manager, IoT", "Senior Product Manager | IoT, Hardware"],
  ["", "A brand new line"],
  ["Remove this line", ""],
];

test("tracked changes: hiding the deletions always gives the new text", () => {
  for (const [before, after] of PAIRS) assert.equal(shown(diffOps(before, after), "del"), after);
});

test("tracked changes: hiding the insertions always gives the old text", () => {
  for (const [before, after] of PAIRS) assert.equal(shown(diffOps(before, after), "ins"), before);
});

test("tracked changes: removed and added words are both marked", () => {
  const ops = diffOps("Aligned firmware teams", "Managed stakeholders across firmware teams");
  assert.ok(ops.some((o) => o.type === "del" && o.text.includes("Aligned")));
  assert.ok(ops.some((o) => o.type === "ins" && o.text.includes("Managed")));
  assert.ok(ops.some((o) => o.type === "same" && o.text.includes("firmware teams")));
});

test("tracked changes: identical text has no marks", () => {
  assert.deepEqual(diffOps("Owned the roadmap", "Owned the roadmap"), [{ type: "same", text: "Owned the roadmap" }]);
});

test("tracked changes: a spacing-only edit has no marks and shows the new spacing", () => {
  assert.deepEqual(diffOps("a  b", "a b"), [{ type: "same", text: "a b" }]);
});

test("tracked changes: neighbouring pieces of the same kind are merged", () => {
  const ops = diffOps("one two three", "one 2 3 three");
  for (let i = 1; i < ops.length; i++) assert.notEqual(ops[i].type, ops[i - 1].type);
});

test("JD tiers: average 80 with minimum 70 is apply, average 60 is tune, below is risky", () => {
  assert.equal(tier(80, 70), "apply");
  assert.equal(tier(79.9, 75), "tune");
  assert.equal(tier(85, 69), "tune");
  assert.equal(tier(60, 40), "tune");
  assert.equal(tier(59.9, 50), "risky");
});

test("tracker row: columns come out in sheet order, tab separated", () => {
  const row = Object.fromEntries(TRACKER_COLUMNS.map((c) => [c, c.toUpperCase()])) as Record<(typeof TRACKER_COLUMNS)[number], string>;
  assert.equal(trackerTSV(row), TRACKER_COLUMNS.map((c) => c.toUpperCase()).join("\t"));
});

test("tracker row: tabs and line breaks inside a cell cannot break the paste", () => {
  const row = Object.fromEntries(TRACKER_COLUMNS.map((c) => [c, ""])) as Record<(typeof TRACKER_COLUMNS)[number], string>;
  const line = trackerTSV({ ...row, company: "Acme\tCorp", notes: "line one\nline two\r\nline three" });
  assert.equal(line.split("\t").length, TRACKER_COLUMNS.length);
  assert.ok(!/[\n\r]/.test(line));
  assert.ok(line.startsWith("Acme Corp\t") && line.endsWith("line one line two line three"));
});

test("accepted changes: applied in place, and a change that is not found is reported", () => {
  const { text, missed } = applyToText("A\nOwned roadmap\nB", [
    { find: "Owned roadmap", replace: "Owned the roadmap" },
    { find: "Not in the resume", replace: "x" },
  ]);
  assert.equal(text, "A\nOwned the roadmap\nB");
  assert.deepEqual(missed, ["Not in the resume"]);
});

test("accepted changes: a dollar sign in the new text is kept as typed", () => {
  assert.equal(applyToText("Saved money", [{ find: "Saved money", replace: "Saved [$X] in year one" }]).text, "Saved [$X] in year one");
});
