"""Tests over the workflow files themselves (issue #30, `docs/spec/app.md` APP-051–053).

The release key reaches GitHub Actions as repository secrets, and the release
workflow is the only place allowed to use them. These tests read every file
under `.github/workflows/` as text — the gate and its tests are standard library
only (APP-046), so there is no YAML parser — and check three things:

- no workflow a pull request can trigger references an `ANDROID_KEY*` secret
  (APP-052);
- both release jobs run the release-signature gate from a separate checkout of
  `main`, never from the tag being built (APP-051);
- the android-tests workflow runs these tests (APP-053).
"""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
WORKFLOWS = os.path.join(REPO_ROOT, ".github", "workflows")
RELEASE_PLEASE_WORKFLOW = os.path.join(WORKFLOWS, "release-please.yml")
ANDROID_TESTS_WORKFLOW = os.path.join(WORKFLOWS, "android-tests.yml")

RELEASE_JOBS = ("build-and-attach", "backfill-release-apk")
GATE_SCRIPT = ".github/scripts/verify_release_signature.py"

# `secrets.ANDROID_KEY...` or `secrets['ANDROID_KEY...']`, the two ways an
# expression can name a secret.
_KEY_SECRET = re.compile(r"secrets\s*(?:\.\s*|\[\s*['\"])ANDROID_KEY", re.IGNORECASE)
_PULL_REQUEST_EVENT = re.compile(r"(?<![\w-])pull_request(?:_target)?(?![\w-])")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _workflow_paths():
    return sorted(
        os.path.join(WORKFLOWS, name) for name in os.listdir(WORKFLOWS)
        if name.endswith((".yml", ".yaml")))


def _indent(line):
    return len(line) - len(line.lstrip())


def _strip_comment(line):
    """The line without a trailing `# comment` (workflow files quote no `#` in these blocks)."""
    return re.sub(r"(^|\s)#.*$", "", line)


def triggers_text(text):
    """The text of a workflow's top-level `on:` key: its inline value and its block."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"""^(?:on|"on"|'on')\s*:(.*)$""", line)
        if not match:
            continue
        collected = [_strip_comment(match.group(1))]
        for following in lines[index + 1:]:
            if following.strip() and _indent(following) == 0 \
                    and not following.lstrip().startswith("#"):
                break
            collected.append(_strip_comment(following))
        return "\n".join(collected)
    return ""


def is_pull_request_triggered(text):
    """Whether a pull request can start this workflow, in any of YAML's spellings of `on:`."""
    return bool(_PULL_REQUEST_EVENT.search(triggers_text(text)))


def block(text, header_pattern, end_at_same_indent_dash=False):
    """The lines of the first block whose header line matches, up to the next sibling.

    For a job (`name:` at some indent) the block ends at the next non-blank
    line indented no deeper than the header. For a step (`- name: ...`) it ends
    at the next `- ` at the header's indent, or anything shallower.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(header_pattern, line):
            continue
        indent = _indent(line)
        body = [line]
        for following in lines[index + 1:]:
            if not following.strip():
                body.append(following)
                continue
            depth = _indent(following)
            if depth < indent:
                break
            if depth == indent and (
                    not end_at_same_indent_dash or following.lstrip().startswith("- ")):
                break
            body.append(following)
        return "\n".join(body)
    return None


def job_body(text, job_name):
    return block(text, r"^  {0}:\s*$".format(re.escape(job_name)))


def step_body(text, step_name):
    return block(text, r"^\s*- name:\s*{0}\s*$".format(re.escape(step_name)),
                 end_at_same_indent_dash=True)


def steps(job_text):
    """Each step of a job, as text, in order."""
    lines = job_text.splitlines()
    starts = [index for index, line in enumerate(lines) if re.match(r"^\s*- (?:name|uses):", line)]
    if not starts:
        return []
    indent = _indent(lines[starts[0]])
    starts = [index for index in starts if _indent(lines[index]) == indent]
    bounds = starts + [len(lines)]
    return ["\n".join(lines[bounds[i]:bounds[i + 1]]) for i in range(len(starts))]


class TriggerDetectionTests(unittest.TestCase):
    """The detector APP-052 relies on must see every spelling of a pull_request trigger."""

    def test_block_form(self):
        self.assertTrue(is_pull_request_triggered("on:\n  pull_request:\n  push:\n"))

    def test_block_form_with_types(self):
        self.assertTrue(is_pull_request_triggered(
            "on:\n  pull_request_target:\n    types: [opened]\njobs: {}\n"))

    def test_scalar_form(self):
        self.assertTrue(is_pull_request_triggered("on: pull_request\njobs: {}\n"))

    def test_flow_list_form(self):
        self.assertTrue(is_pull_request_triggered("on: [push, pull_request_target]\n"))

    def test_block_list_form(self):
        self.assertTrue(is_pull_request_triggered("on:\n  - push\n  - pull_request\n"))

    def test_quoted_on_key(self):
        self.assertTrue(is_pull_request_triggered('"on":\n  pull_request:\n'))

    def test_push_and_dispatch_only_is_not_pull_request_triggered(self):
        self.assertFalse(is_pull_request_triggered(
            "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n"
            "jobs:\n  x:\n    if: github.event.issue.pull_request == null\n"))

    def test_a_comment_mentioning_pull_request_is_not_a_trigger(self):
        self.assertFalse(is_pull_request_triggered(
            "on:\n  # never pull_request: this holds secrets\n  push:\n"))

    def test_issue_comment_events_on_pull_requests_are_not_pull_request_triggers(self):
        self.assertFalse(is_pull_request_triggered("on:\n  pull_request_review:\n"))

    def test_the_secret_pattern_matches_both_expression_spellings(self):
        for text in ("${{ secrets.ANDROID_KEYSTORE_BASE64 }}",
                     "${{ secrets.ANDROID_KEY_ALIAS }}",
                     "${{ secrets['ANDROID_KEY_ALIAS_PASSWORD'] }}"):
            with self.subTest(text=text):
                self.assertTrue(_KEY_SECRET.search(text))
        self.assertFalse(_KEY_SECRET.search("${{ secrets.ROUTINE_FIRE_TOKEN }}"))


class PullRequestWorkflowsCannotReachTheKeyTests(unittest.TestCase):
    """APP-052: no workflow a pull request can trigger references an ANDROID_KEY* secret."""

    def test_the_workflows_are_found(self):
        self.assertIn(RELEASE_PLEASE_WORKFLOW, _workflow_paths())
        self.assertIn(ANDROID_TESTS_WORKFLOW, _workflow_paths())

    def test_android_tests_is_pull_request_triggered(self):
        """A sanity check that the detector sees the workflow it most needs to."""
        self.assertTrue(is_pull_request_triggered(_read(ANDROID_TESTS_WORKFLOW)))

    def test_no_pull_request_triggered_workflow_references_the_release_key(self):
        for path in _workflow_paths():
            text = _read(path)
            if not is_pull_request_triggered(text):
                continue
            with self.subTest(workflow=os.path.basename(path)):
                self.assertIsNone(
                    _KEY_SECRET.search(text),
                    "{0} can be triggered by a pull request and must never reach the "
                    "release key".format(os.path.basename(path)))

    def test_the_release_workflow_holds_the_key_and_is_not_pull_request_triggered(self):
        text = _read(RELEASE_PLEASE_WORKFLOW)
        self.assertTrue(_KEY_SECRET.search(text), "release-please.yml no longer uses the key")
        self.assertFalse(is_pull_request_triggered(text))


class GateIsSourcedFromMainTests(unittest.TestCase):
    """APP-051: both release jobs run the gate from a separate checkout of `main`.

    A tag's own tree carries whatever copy of the gate existed when it was cut,
    never a later fix to the gate itself, so a job that ran the tag's copy
    would re-enact any bug the gate had then.
    """

    def _job(self, job_name):
        body = job_body(_read(RELEASE_PLEASE_WORKFLOW), job_name)
        self.assertIsNotNone(body, "no '{0}' job in release-please.yml".format(job_name))
        return body

    def _main_checkout_path(self, job_name):
        checkouts = [step for step in steps(self._job(job_name))
                     if re.search(r"uses:\s*actions/checkout@", step)]
        on_main = [step for step in checkouts
                   if re.search(r"^\s*ref:\s*main\s*$", step, re.MULTILINE)]
        self.assertEqual(
            len(on_main), 1,
            "{0} must check out `main` exactly once, literally `ref: main`".format(job_name))
        path = re.search(r"^\s*path:\s*(\S+)\s*$", on_main[0], re.MULTILINE)
        self.assertIsNotNone(path, "{0}'s `main` checkout has no `path:`".format(job_name))
        return path.group(1)

    def test_each_job_checks_out_main_to_a_distinct_path(self):
        for job_name in RELEASE_JOBS:
            with self.subTest(job=job_name):
                path = self._main_checkout_path(job_name)
                self.assertNotIn(path.strip("'\""), ("", ".", "./"))

    def test_each_job_also_checks_out_the_tag_it_builds(self):
        for job_name in RELEASE_JOBS:
            with self.subTest(job=job_name):
                checkouts = [step for step in steps(self._job(job_name))
                             if re.search(r"uses:\s*actions/checkout@", step)]
                self.assertEqual(len(checkouts), 2)
                tag_checkouts = [step for step in checkouts
                                 if not re.search(r"^\s*ref:\s*main\s*$", step, re.MULTILINE)]
                self.assertEqual(len(tag_checkouts), 1)
                self.assertNotRegex(tag_checkouts[0], r"^\s*path:", "the tag is built at the "
                                    "workspace root, apart from the gate's checkout")

    def test_each_job_runs_the_gate_from_the_main_checkout_only(self):
        for job_name in RELEASE_JOBS:
            with self.subTest(job=job_name):
                path = self._main_checkout_path(job_name).strip("'\"").rstrip("/")
                verify = step_body(self._job(job_name), "Verify the release signature")
                self.assertIsNotNone(verify, "{0} has no verification step".format(job_name))
                self.assertIn("{0}/{1}".format(path, GATE_SCRIPT), verify)
                self.assertNotRegex(
                    verify, r"(?<![\w/.-])\.?/?\.github/scripts/verify_release_signature\.py",
                    "the gate must not run from the tag checkout's own copy")

    def test_the_gate_runs_before_anything_is_uploaded(self):
        for job_name in RELEASE_JOBS:
            with self.subTest(job=job_name):
                job_steps = steps(self._job(job_name))
                verify = [i for i, step in enumerate(job_steps)
                          if GATE_SCRIPT in step]
                upload = [i for i, step in enumerate(job_steps)
                          if "gh release upload" in step]
                self.assertEqual(len(verify), 1)
                self.assertEqual(len(upload), 1)
                self.assertLess(verify[0], upload[0])
                self.assertNotRegex(job_steps[upload[0]], r"^\s*if:\s*\$\{\{\s*always",
                                    "the upload must not run after a failed gate")


class GateTestsRunInCiTests(unittest.TestCase):
    """APP-053: android-tests runs these tests with no Android SDK and no added action."""

    COMMAND = "python3 -m unittest discover -s .github/scripts/tests"

    def _job_running_the_tests(self):
        text = _read(ANDROID_TESTS_WORKFLOW)
        jobs = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", text, re.MULTILINE)
        found = [name for name in jobs if self.COMMAND in (job_body(text, name) or "")]
        self.assertEqual(len(found), 1, "no single android-tests job runs: " + self.COMMAND)
        return job_body(text, found[0])

    def test_android_tests_runs_on_pull_requests_and_pushes_to_main(self):
        text = _read(ANDROID_TESTS_WORKFLOW)
        self.assertTrue(is_pull_request_triggered(text))
        self.assertRegex(triggers_text(text), r"push:\s*\n\s*branches:\s*\[\s*main\s*\]")

    def test_the_job_uses_only_a_checkout_action(self):
        uses = re.findall(r"uses:\s*(\S+)", self._job_running_the_tests())
        self.assertTrue(uses)
        self.assertEqual(
            [action for action in uses if not action.startswith("actions/checkout@")], [],
            "the gate's tests need only the runner's python3")

    def test_the_job_holds_no_secret(self):
        self.assertNotIn("secrets.", self._job_running_the_tests())


if __name__ == "__main__":
    unittest.main()
