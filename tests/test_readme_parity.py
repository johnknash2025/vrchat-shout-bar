#!/usr/bin/env python3
"""Parity checks for README.md (English) and README.ja.md (Japanese).

Run with pytest:  python3 -m pytest
Run as a script:  python3 tests/test_readme_parity.py

Checks, for both README files:
  1. the language-switch line sits directly under the title, exactly once
  2. README.md is written in English and README.ja.md in Japanese, in the title,
     the headings and the body text (not in the title alone)
  3. headings match in number and order (same level sequence, same numbered steps)
  4. matching sections carry the same content shape: the same counts of text lines,
     list items, block quotes, table rows, images, links, inline code and version
     numbers, and the same relative link targets
   5. every relative link / image target resolves inside this repository. A target that is
       not there is a broken link, whoever it points at — except the repository's own
       documentation files (the demo media, AGENTS.md, the licence): those are committed
       repository files that no README edit creates, so a checkout that strips one out (a
       partial checkout, a source archive that left it out) has a packaging gap, and that
       gap is reported as a note naming the file instead of failing the READMEs
   6. both files point at the same set of relative link targets
   7. both files use the same external links, every one of them is well formed and sits
       in the pinned known-good set. Those two checks are what this suite can decide on its
       own; whether a link answers over HTTPS depends on where the suite happens to run, so
       the live answer never decides a normal run: a host that does not resolve from here, a
       connection nothing answered, and an HTTP answer that says the page is gone are all
       recorded as notes naming the link, and only SHOUTBAR_README_REQUIRE_LIVE_LINKS — the
       way a job that has egress demands the live proof — turns one of those into a problem.
       A machine that cannot leave the house at all (no DNS, no egress, a runner that filters
       every request) skips the live check and says so out loud, with or without that
       variable: it can prove nothing about a link in either direction, so it is not allowed
       to fail the READMEs for it either. Answers that only prove the site blocks robots are
       notes in every mode.
   8. the Customising table has the same number of rows, and the "another language" row
       appears once in both, at the same position, carrying the same example, and names the
       language the repository ships in (so an English reader is not left guessing which
       text the row is about). The shipped default names are read from ShoutManager.cs, in
       whichever way shoutNames is initialised there. A script that is missing, unreadable,
       has no shoutNames, or has a shoutNames default this reader cannot resolve is a
       packaging gap of this checkout, not a README problem: the example is compared with
       the shipped names when they can be read, and skipped with a note naming the reason
       when they cannot. The example must list exactly as many names as the scripts ship,
       and when those names are written in a non-Latin script the example must not repeat
       them; a romanised default list only produces a note, because a name match then says
       nothing about language.
  9. the two READMEs say the same things: every claim in CLAIMS (the answers, the numbers,
      the defaults, the cautions) is present in both files, each in its own language's
      wording. This is what catches a translation that drifts in meaning while keeping the
      same line counts, headings and examples.
 10. matching sections use the same inline code spans (identifiers, paths, component names),
      not merely the same number of them.
  11. no build cache (Python __pycache__, .pyc/.pyo, .pytest_cache) is committed, and
      .gitignore keeps them out. The committed-file scan needs git: a checkout with no .git
      directory, one that has a .git but no git command to run, and one whose git ls-files
      fails are all notes, while the .gitignore rule check still runs.

Temporary scratch (the cases that need a stripped copy of the repository) is made under
./.agent-tmp/; a checkout where that cannot be created reports the problem and skips the
case instead of erroring.

Works on Python 3.7 and later.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {"en": ROOT / "README.md", "ja": ROOT / "README.ja.md"}
SWITCH = {
    "en": "English | [日本語](README.ja.md)",
    "ja": "[English](README.md) | 日本語",
}
TABLE_HEADING = {"en": "Customising", "ja": "カスタマイズ"}
LANG_CELL = {"en": "language", "ja": "言語"}
DEFAULT_LANGUAGE_CELL = {"en": "Japanese", "ja": "日本語"}
MANAGER = ROOT / "Assets" / "Scripts" / "ShoutManager.cs"
README_NAMES = {"README.md", "README.ja.md"}
# Ordinary repository files both READMEs link to. They are committed repository files, so a
# checkout that leaves one out has a packaging gap, not a README full of dead links: the gap
# is noted, and only a link to something the repository never promises is a broken link.
REPO_LINKS = ("docs/demo.gif", "docs/demo.mp4", "AGENTS.md", "LICENSE")

EXTERNAL_LINKS = {"https://vrchat.com/home/download"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
UNVERIFIABLE = {401, 403, 405, 406, 408, 425, 429, 500, 502, 503, 504}
# Hosts that exist whatever this repository does. They are looked up, connected to *and*
# fetched from, to tell "this machine cannot leave the house" apart from "the linked host is
# the problem": a sandbox with a working resolver, or one that can open a socket but refuses
# every request, must not be blamed for a link it was never allowed to ask for.
CONTROL_HOSTS = ("example.com", "example.org")
CONTROL_URLS = {host: f"https://{host}/" for host in CONTROL_HOSTS}
CONTROL_PORT = 443
PROBE_TIMEOUT = 4.0
CONTROL_FETCH_TIMEOUT = 6.0
FETCH_TIMEOUT = 15
MAX_INITIALISER = 4000
JA_HEADINGS_SHARE = 0.75
JA_BODY_SHARE = 0.8
JA_SECTION_SHARE = 0.5
# A machine that cannot reach the network at all gets its live check skipped, and the skip
# is said out loud as a note. Setting this turns that skip into a problem, for a job that
# does have egress and wants the links proven.
REQUIRE_LIVE_LINKS = "SHOUTBAR_README_REQUIRE_LIVE_LINKS"
SKIP_MARK = "live external link check skipped"
IGNORE_RULES = ("__pycache__/", "*.py[cod]", ".pytest_cache/")
COMMITTED_CACHE = re.compile(r"(^|/)(__pycache__/|\.pytest_cache/|.*\.py[co]$)")
# What both READMEs must actually say, each in its own language's wording. Every claim has
# to match in both files: a translation that changes the meaning (an answer flipped, a
# default number swapped, a caution dropped) fails here even when the layout still matches.
CLAIMS = (
    ("is world-creator-only", r"\*\*No\.", r"\*\*いいえ。"),
    ("only the world author can edit", r"only the author of a world can change", r"ワールドの中身を変えられるのはそのワールドの作者だけ"),
    ("avatar-side route for any world", r"avatar-side gimmick", r"アバター側のギミック"),
    ("counts shown as totals and percentages", r"totals and percentages", r"累計と割合"),
    ("late joiners see the counts", r"join later see them too|late joiners see the totals", r"後から入ってきた人にも見えます|途中から入った人にも累計が見えます"),
    ("intended use: watch parties and event bars", r"anime watch parties and event bars", r"アニメの上映会やイベントバー"),
    ("status date", r"2026-10-21", r"2026-10-21"),
    ("tested Unity version", r"2022\.3\.22f1", r"2022\.3\.22f1"),
    ("tested Worlds SDK version", r"3\.10\.5", r"3\.10\.5"),
    ("multi-user syncing unconfirmed", r"Multi-user syncing has \*\*not been confirmed yet\*\*", r"複数人での同期は\*\*まだ確認していません\*\*"),
    ("mash limit while playing", r"one press per 0\.5 seconds", r"0\.5 秒に 1 回まで"),
    ("minimum Worlds SDK", r"3\.8\.1 or later", r"3\.8\.1 以降"),
    ("needs parameterised network events", r"parameterised network events", r"パラメータ付きのネットワークイベント"),
    ("needs a Japanese-capable TMP font", r"font that can render Japanese", r"日本語を表示できる TextMeshPro 用のフォント"),
    ("three button cubes", r"three button Cubes", r"ボタン用の Cube を 3 つ"),
    ("button indices", r"0 / 1 / 2", r"0 / 1 / 2"),
    ("two clients when testing", r"\*\*two\*\* clients", r"クライアントを \*\*2 つ\*\*"),
    ("test rejoining mid-session", r"arriving mid-session", r"途中から入った人にもカウントが正しく見える"),
    ("publish Private first", r"Private first", r"Private で公開"),
    ("reset button is staff-only", r"staff-only", r"スタッフ用"),
    ("up to eight shouts", r"up to 8", r"最大 8 個"),
    ("cooldown default", r"cooldownSeconds` \(default 0\.5 s", r"`cooldownSeconds`（既定 0\.5 秒"),
    ("popup default", r"popupSeconds` \(default 2 s", r"`popupSeconds`（既定 2 秒"),
    ("reset permission switch", r"onlyMasterCanReset` off", r"onlyMasterCanReset` をオフ"),
    ("names the language it ships in", r"the text here is Japanese by default", r"ここは既定で日本語"),
    ("Latin text needs no extra font", r"no Japanese font is needed", r"日本語フォントの準備はいらない"),
    ("ownership is handed over", r"hands ownership to someone else", r"オーナーを引き継ぎ"),
    ("portraits: public domain or own work", r"public-domain photos or your own artwork", r"パブリックドメインの写真か、自作のイラスト"),
    ("video in a world can be a copyright problem", r"copyright problems", r"著作権の問題"),
    ("everyone watches on their own subscription", r"everyone watches on their own subscription", r"各自が自分のサブスクで視聴"),
    ("follow the ToS and guidelines", r"Terms of Service and Community Guidelines", r"利用規約とコミュニティガイドライン"),
    ("no warranty", r"no warranty", r"無保証"),
    ("MIT licence", r"MIT License", r"MIT License"),
    ("particles have no material yet", r"material has not been set up yet", r"をまだ設定していないため"),
    ("recorded in ClientSim", r"Recorded in Unity's ClientSim", r"Unity の ClientSim（"),
)

KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3005]")
JA_MARKS = re.compile(r"[「」『』、。：・（）]")
CJK = re.compile(r"[\u3000-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
IMAGE = re.compile(r"^\s*!\[[^\]]*\]\([^)\s]+\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
NUMBERED = re.compile(r"^(\d+)\.")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
QUOTE = re.compile(r"^\s*>")
TABLE_SEP = re.compile(r"\|[\s\-:|]+\|")
CODE_SPAN = re.compile(r"`[^`]+`")
BOLD = re.compile(r"\*\*(.+?)\*\*")
VERSION = re.compile(r"\d+\.\d+(?:\.\d+)*")
PARENS = re.compile(r"[（(]([^）)]*)[）)]")
EXAMPLE_LABEL = re.compile(r"^(e\.g\.|例\s*[:：])", re.I)
SHOUT_NAMES_DECL = re.compile(r"\bshoutNames\b")
SHOUT_NAMES_ASSIGN = re.compile(r"\bshoutNames\s*=")
STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
NON_LATIN = re.compile(r"[^\x00-\x7f]")
URL_SHAPE = re.compile(
    r"https://[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])+)+"
    r"(?::\d{1,5})?(?:/[^\s\"'<>|]*)?"
)

CATEGORIES = ("switch", "language", "headings", "sections", "links", "external", "table", "meaning", "repo")
CACHED = {}
NET_STATE = {}


def analyze():
    if not CACHED:
        CACHED.update(run_checks())
    return CACHED


def problems(category):
    return analyze()["problems"][category]


def notes():
    return analyze()["notes"]


def scratch_dir():
    """A temporary directory inside this checkout's own .agent-tmp area, or None if it cannot be made.

    Tests that need a stripped copy of the repository build it under ./.agent-tmp/, which is
    what the repository itself treats as scratch. The directory is created when it is absent,
    so the suite also runs from a copy that was made there (a copy has no .agent-tmp of its
    own). Where the scratch area cannot be created the answer is None: the caller says so out
    loud and skips its case, because this scratch area is this suite's own tool and nothing a
    README can get wrong. Nothing is ever written outside ./.agent-tmp/.
    """
    base = ROOT / ".agent-tmp"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=str(base))
    except OSError:
        return None


def run_checks():
    issues = {name: [] for name in CATEGORIES}
    notes_list = []
    verified = {}

    def fail(category, message):
        issues[category].append(message)

    def note(message):
        notes_list.append(message)

    docs = {name: read_doc(path, fail) for name, path in FILES.items()}
    headings = {name: headings_of(lines) for name, lines in docs.items()}

    for name, file_headings in headings.items():
        if docs[name]:
            check_switch(name, docs[name], fail)
            check_language(name, docs[name], file_headings, fail)

    check_heading_parity(headings, fail)
    check_section_content(docs, fail)
    targets = {name: relative_targets(lines, name, fail, note) for name, lines in docs.items()}
    check_link_parity(targets, fail)
    pinned = check_external(docs, fail, note, verified)
    check_table(docs, headings, fail)
    check_language_row(docs, default_names(note), fail, note)
    check_meaning(docs, fail)
    check_repo_hygiene(fail, note)

    return {"problems": issues, "notes": notes_list, "verified_external": verified, "pinned_external": pinned}


def read_doc(path, fail):
    if not path.is_file():
        fail("links", f"{path.name}: file not found")
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        fail("links", f"{path.name}: cannot be read ({error})")
        return []
    lines, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


def headings_of(lines):
    return [(len(m.group(1)), m.group(2).strip()) for m in map(HEADING.match, lines) if m]


def check_switch(name, lines, fail):
    hits = [i for i, line in enumerate(lines) if line.strip() == SWITCH[name]]
    if not hits:
        fail("switch", f"{name}: switch line '{SWITCH[name]}' not found")
    elif len(hits) > 1:
        fail("switch", f"{name}: switch line appears {len(hits)} times, expected once")
    elif hits[0] > 3:
        fail("switch", f"{name}: switch line on line {hits[0] + 1}, expected directly under the title")


def is_japanese(text):
    return bool(KANA.search(text) or JA_MARKS.search(text))


def text_lines(body):
    return [line.strip() for line in body if line.strip() and not TABLE_SEP.fullmatch(line.strip())]


def check_language(name, lines, file_headings, fail):
    title = next((t for level, t in file_headings if level == 1), "")
    if name == "en":
        if CJK.search(title):
            fail("language", "en: README.md title is written in Japanese")
        for level, heading in file_headings:
            if CJK.search(heading):
                fail("language", f"en: heading '{heading}' contains Japanese characters")
        found = [line.strip() for line in lines if line.strip() != SWITCH["en"] and CJK.search(line)]
        if found:
            shown = "; ".join(f"line: {line[:60]}" for line in found[:3])
            fail("language", f"en: README.md body is not written in English ({len(found)} line(s) with Japanese: {shown})")
    else:
        if not is_japanese(title):
            fail("language", "ja: README.ja.md title is not written in Japanese")
        if file_headings:
            japanese = sum(1 for _, heading in file_headings if is_japanese(heading))
            if japanese / len(file_headings) < JA_HEADINGS_SHARE:
                fail(
                    "language",
                    f"ja: README.ja.md headings are not written in Japanese "
                    f"({japanese} of {len(file_headings)} contain Japanese characters)",
                )
        counted = text_lines(lines)
        if counted:
            share = sum(1 for line in counted if is_japanese(line)) / len(counted)
            if share < JA_BODY_SHARE:
                fail(
                    "language",
                    f"ja: README.ja.md body is not written in Japanese "
                    f"({round(share * 100)}% of {len(counted)} text lines contain Japanese characters)",
                )
        for _, section_title, body in split_sections(lines):
            section_lines = text_lines(body)
            if len(section_lines) < 2:
                continue
            share = sum(1 for line in section_lines if is_japanese(line)) / len(section_lines)
            if share < JA_SECTION_SHARE:
                label = f"'{section_title}'" if section_title else "the part above the first heading"
                fail(
                    "language",
                    f"ja: the {label} section of README.ja.md is not written in Japanese "
                    f"({round(share * 100)}% of {len(section_lines)} text lines contain Japanese characters)",
                )
    if not any(level == 2 and title == TABLE_HEADING[name] for level, title in file_headings):
        fail("table", f"{name}: '{TABLE_HEADING[name]}' section not found")


def numbered_steps(file_headings):
    steps = []
    for _, title in file_headings:
        matched = NUMBERED.match(title)
        if matched:
            steps.append(int(matched.group(1)))
    return steps


def check_heading_parity(headings, fail):
    en_heads, ja_heads = headings["en"], headings["ja"]
    for name, items in headings.items():
        if not items:
            fail("headings", f"{name}: no title found")
        elif sum(1 for level, _ in items if level == 1) != 1:
            fail("headings", f"{name}: expected exactly one H1 title")
    if not en_heads or not ja_heads:
        return
    if len(en_heads) != len(ja_heads):
        fail("headings", f"heading count differs: README.md {len(en_heads)} vs README.ja.md {len(ja_heads)}")
    elif [level for level, _ in en_heads] != [level for level, _ in ja_heads]:
        fail("headings", f"heading order differs: {[level for level, _ in en_heads]} vs {[level for level, _ in ja_heads]}")
    if numbered_steps(en_heads) != numbered_steps(ja_heads):
        fail("headings", f"numbered steps differ: {numbered_steps(en_heads)} vs {numbered_steps(ja_heads)}")


def split_sections(lines):
    sections = [(0, "", [])]
    for line in lines:
        matched = HEADING.match(line)
        if matched:
            sections.append((len(matched.group(1)), matched.group(2).strip(), []))
        else:
            sections[-1][2].append(line)
    return sections


def section_signature(body):
    texts = [line.strip() for line in body if line.strip()]
    joined = " ".join(texts)
    links = [target for line in texts for target in LINK.findall(line)]
    relative = {
        target.split("#", 1)[0]
        for target in links
        if not target.startswith(("http://", "https://", "mailto:")) and not target.startswith("#")
    } - README_NAMES
    return {
        "text lines": len(texts),
        "list items": sum(1 for line in texts if LIST_ITEM.match(line)),
        "block quotes": sum(1 for line in texts if QUOTE.match(line)),
        "table rows": sum(1 for line in texts if line.startswith("|")),
        "images": sum(1 for line in texts if IMAGE.match(line)),
        "links": len(links),
        "inline code": len(CODE_SPAN.findall(joined)),
        "inline code spans": sorted(CODE_SPAN.findall(joined)),
        "bold spans": len(BOLD.findall(joined)),
        "version numbers": Counter(VERSION.findall(joined)),
        "relative targets": relative,
    }


def check_section_content(docs, fail):
    en_sections = split_sections(docs["en"])
    ja_sections = split_sections(docs["ja"])
    if len(en_sections) != len(ja_sections):
        fail("sections", f"section count differs: README.md {len(en_sections)} vs README.ja.md {len(ja_sections)}")
        return
    for (level, en_title, en_body), (_, ja_title, ja_body) in zip(en_sections, ja_sections):
        en_sig, ja_sig = section_signature(en_body), section_signature(ja_body)
        if en_sig == ja_sig:
            continue
        label = f"'{en_title}' / '{ja_title}'" if en_title else "the part above the first heading"
        differs = [
            f"{key}: README.md {en_sig[key]} vs README.ja.md {ja_sig[key]}"
            for key in en_sig
            if en_sig[key] != ja_sig[key]
        ]
        fail("sections", f"content differs in section {label} -> " + "; ".join(differs))


def table_rows(lines, section):
    rows, inside = [], False
    for line in lines:
        matched = HEADING.match(line)
        if matched:
            inside = matched.group(2).strip() == section
            continue
        stripped = line.strip()
        if inside and stripped.startswith("|") and not TABLE_SEP.fullmatch(stripped):
            rows.append(stripped)
    return rows


def language_row(rows, name):
    found = [(i, row) for i, row in enumerate(rows) if LANG_CELL[name] in row.split("|")[1]]
    if len(found) != 1:
        return None
    return found[0]


def example_names(row):
    """The names inside the labelled example bracket (e.g. ... / 例：...), if there is one."""
    for matched in PARENS.finditer(row):
        inner = matched.group(1)
        if not EXAMPLE_LABEL.match(inner.strip()):
            continue
        names = {n.strip().strip("！!").lower() for n in EXAMPLE_LABEL.sub("", inner).split("/") if n.strip()}
        if names:
            return names
    return None


def initialiser_segment(text, start):
    """The text from a shoutNames '=' up to the statement's own ';', or None."""
    depth = 0
    for i in range(start, min(len(text), start + MAX_INITIALISER)):
        char = text[i]
        if char in "{([":
            depth += 1
        elif char in "})]":
            depth -= 1
        elif char == ";" and depth <= 0:
            return text[start:i]
    return None


def parse_shipped_names(text):
    """Read the default shout names out of a ShoutManager source text.

    Returns (names, reason); names is None when nothing readable was found, and the reason
    then says what was looked for. Every common way of writing the defaults is accepted:
    a brace list, new string[] { ... }, new[] { ... }, a List<string> initialiser, spread
    over any number of lines.
    """
    if not SHOUT_NAMES_DECL.search(text):
        return None, "no shoutNames field: the script the READMEs describe is not this script"
    for matched in SHOUT_NAMES_ASSIGN.finditer(text):
        segment = initialiser_segment(text, matched.end())
        if segment is None:
            continue
        names = {
            name.strip().strip("！!").lower()
            for name in STRING_LITERAL.findall(segment)
            if name.strip()
        }
        if names:
            return names, ""
    return None, "no quoted name list in any shoutNames initialiser"


def default_names(note):
    """The names the scripts ship by default, or None with the reason said out loud.

    The READMEs document these names (the Customising table tells the reader to rewrite
    them), so the example is compared with them whenever this checkout can produce them. A
    script that is missing or unreadable is a packaging gap of the checkout — the READMEs
    did not lose it — so it skips the comparison and names the reason as a note.
    """
    if not MANAGER.is_file():
        note(f"{MANAGER.name} is not in this checkout: the shipped default names could not be read, so the example was not compared with them")
        return None
    try:
        text = MANAGER.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        note(f"{MANAGER.name} cannot be read ({error}): the shipped default names could not be read, so the example was not compared with them")
        return None
    names, reason = parse_shipped_names(text)
    if names is None:
        note(f"{MANAGER.name}: {reason}: the shipped default names could not be read, so the example was not compared with them")
    return names


def relative_target(target):
    return target.split("#", 1)[0]


def relative_targets(lines, name, fail, note):
    """Every relative link target in the file; existence is checked here.

    A target that is not in this checkout is a broken link in this checkout, whoever it
    points at — except the repository's own documentation files (REPO_LINKS: the demo media,
    AGENTS.md, the licence). No README edit creates those; they are committed repository
    files, so a checkout that leaves one out has a packaging gap rather than a dead link,
    and the gap is reported as a note naming the file instead of failing the READMEs.
    """
    targets = set()
    for line in lines:
        for target in LINK.findall(line):
            if target.startswith(("http://", "https://", "mailto:")) or target.startswith("#"):
                continue
            path = relative_target(target)
            if not path:
                continue
            if not (ROOT / path).exists():
                if path in REPO_LINKS:
                    note(f"{name}: {path} is not in this checkout, so the link to it was not verified here")
                else:
                    fail("links", f"{name}: broken link {target} ({path} is not in this checkout)")
            targets.add(target)
    return targets


def shared_targets(targets):
    """The same targets minus the two README names, which the switch line links on purpose."""
    return {
        name: {t for t in items if Path(relative_target(t)).name not in README_NAMES}
        for name, items in targets.items()
    }


def external_targets(lines):
    return {t for line in lines for t in LINK.findall(line) if t.startswith(("http://", "https://"))}


def check_link_parity(targets, fail):
    shared = shared_targets(targets)
    if shared["en"] != shared["ja"]:
        fail(
            "links",
            "link targets differ: "
            f"only in README.md {sorted(shared['en'] - shared['ja'])}, "
            f"only in README.ja.md {sorted(shared['ja'] - shared['en'])}",
        )
    for name, other in (("en", "README.ja.md"), ("ja", "README.md")):
        if not any(relative_target(t) == other for t in targets[name]):
            fail("links", f"{name}: no link to {other}")


def resolve(host):
    try:
        socket.getaddrinfo(host, CONTROL_PORT, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return True


def probe(host, results):
    """Can this machine name the control host, open a connection to it, and fetch from it?

    DNS-only success is not enough: a runner with a working resolver and no egress looks
    "online" to getaddrinfo and would then be blamed for a link it never got to reach. A TCP
    connection is not enough either, because a filtering runner can accept the socket and then
    refuse the request; the control page has to come back with any HTTP status at all.
    """
    if not resolve(host):
        results[host] = False
        return
    try:
        with socket.create_connection((host, CONTROL_PORT), timeout=PROBE_TIMEOUT):
            pass
    except OSError:
        results[host] = False
        return
    status, _ = fetch_status(CONTROL_URLS[host], timeout=CONTROL_FETCH_TIMEOUT)
    results[host] = status is not None


def network_available():
    """True when this machine can look up a name and actually fetch something with it.

    CONTROL_HOSTS are hosts that exist regardless of what this repository links to, so
    fetching one tells an offline or egress-blocked machine (CI sandbox, no DNS, a firewalled
    or proxy-filtering runner) apart from a bad link. The probe runs in a daemon thread because
    a blocked resolver or a black-holed connection can hang, and a hang counts as "no network".
    """
    if not NET_STATE:
        reachable = False
        for host in CONTROL_HOSTS:
            results = {}
            thread = threading.Thread(target=probe, args=(host, results), daemon=True)
            thread.start()
            thread.join(PROBE_TIMEOUT)
            if host not in results:
                # the DNS and socket stages passed and the answer is still pending, which can
                # only be the fetch; give it its own budget, then count a hang as "no network"
                thread.join(CONTROL_FETCH_TIMEOUT)
            if results.get(host):
                reachable = True
                break
        NET_STATE["available"] = reachable
    return NET_STATE["available"]


def fetch_status(url, timeout: float = FETCH_TIMEOUT):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, ""
    except urllib.error.HTTPError as error:
        return error.code, f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return None, f"no connection ({error.reason})"
    except OSError as error:
        return None, f"no connection ({error})"
    except Exception as error:
        return None, f"no connection ({error})"


def require_live_links():
    return os.environ.get(REQUIRE_LIVE_LINKS, "").strip().lower() in {"1", "true", "yes"}


def offline_verdict(urls):
    """What to do with the live external check when this machine cannot leave the house.

    A machine that cannot fetch anything over the network cannot prove anything about a link,
    in any direction, so it skips the live check and says so out loud: a normal test run on an
    offline laptop or a CI runner with no egress still passes. The skip is a note even when
    SHOUTBAR_README_REQUIRE_LIVE_LINKS is set — that variable asks for a proof this machine is
    not able to produce, and an environment that cannot fetch is not a README fault. The note
    names the demand it could not meet, so a job that meant to have egress can see that it
    does not.
    """
    listed = ", ".join(urls)
    cannot = "this machine cannot fetch anything over the network (no working DNS, no egress, or a runner that filters every request)"
    demanded = (
        f" {REQUIRE_LIVE_LINKS} demands the live check, and this environment cannot produce it: "
        f"fix the network or unset {REQUIRE_LIVE_LINKS}"
        if require_live_links()
        else f". Set {REQUIRE_LIVE_LINKS}=1 to make an unanswered link a problem instead of a note"
    )
    return "note", (
        f"{SKIP_MARK} for {listed}: {cannot}, so the external "
        f"links are unverified here and a broken link could not be seen{demanded}"
    )


def link_verdict(url, host, resolved, status, detail, strict=False):
    """Judge one live fetch. Pure: takes the outcome, decides fail / note / ok.

    Whether a link answers is a fact about the machine running this suite as much as about the
    link: a filtered DNS, a blocked connection and a 4xx from a CDN in front of the site all
    happen on ordinary checkouts. So an answer this machine could not get is a note that names
    the link, and only a job that demands the live proof (strict, which is how
    SHOUTBAR_README_REQUIRE_LIVE_LINKS reaches here) makes it a problem. An answer that only
    proves the site blocks robots is a note whatever the mode.
    """
    if status is not None and status in UNVERIFIABLE:
        return "note", f"external link {url}: {detail or f'HTTP {status}'} cannot tell a live page from a blocked robot"
    if not resolved:
        message = f"external link {url}: host {host} does not resolve from this machine"
    elif status is None:
        message = f"external link {url}: host {host} resolves but nothing answered ({detail})"
    elif status >= 400:
        message = f"external link {url}: {detail or f'HTTP {status}'}"
    else:
        return "ok", ""
    if strict:
        return "fail", message
    return "note", f"{message}: this machine may be the problem rather than the link; set {REQUIRE_LIVE_LINKS}=1 to treat it as one"


def check_external(docs, fail, note, verified):
    links = {name: external_targets(lines) for name, lines in docs.items()}
    if links["en"] != links["ja"]:
        fail(
            "external",
            "external link parity differs: "
            f"README.md {sorted(links['en'])} vs README.ja.md {sorted(links['ja'])}",
        )
    every = links["en"] | links["ja"]
    for url in sorted(every - EXTERNAL_LINKS):
        host = urllib.parse.urlsplit(url).netloc
        fail("external", f"unknown external link {url} (host {host or 'missing'}); add it to EXTERNAL_LINKS only after checking it works")
    pinned = {url for url in every & EXTERNAL_LINKS if URL_SHAPE.fullmatch(url)}
    for url in sorted((every & EXTERNAL_LINKS) - pinned):
        fail("external", f"malformed external link {url}")
    if not pinned:
        return pinned
    if not network_available():
        kind, message = offline_verdict(sorted(pinned))
        if kind == "fail":
            fail("external", message)
        else:
            note(message)
        return pinned
    strict = require_live_links()
    for url in sorted(pinned):
        host = urllib.parse.urlsplit(url).netloc.split(":")[0]
        resolved = resolve(host)
        status, detail = (None, "no connection attempt: the host does not resolve")
        if resolved:
            status, detail = fetch_status(url)
        kind, message = link_verdict(url, host, resolved, status, detail, strict=strict)
        if kind == "fail":
            fail("external", message)
        elif kind == "note":
            note(message)
        else:
            verified[url] = status
    return pinned


def check_table(docs, headings, fail):
    en_rows = table_rows(docs["en"], TABLE_HEADING["en"])
    ja_rows = table_rows(docs["ja"], TABLE_HEADING["ja"])
    if not en_rows or not ja_rows:
        fail("table", "Customising table has no rows in at least one README")
    elif len(en_rows) != len(ja_rows):
        fail("table", f"Customising row count differs: README.md {len(en_rows)} vs README.ja.md {len(ja_rows)}")
    else:
        found_en = language_row(en_rows, "en")
        found_ja = language_row(ja_rows, "ja")
        if not found_en or not found_ja:
            fail("table", "expected one 'another language' row in each README")
            return
        en_index, en_row = found_en
        ja_index, ja_row = found_ja
        if en_index != ja_index:
            fail(
                "table",
                "'another language' row position differs: "
                f"README.md row {en_index + 1} vs README.ja.md row {ja_index + 1}",
            )
        language_row_is_clear(en_rows, "en", fail)
        language_row_is_clear(ja_rows, "ja", fail)


def check_language_row(docs, defaults, fail, note):
    en_row = language_row(table_rows(docs["en"], TABLE_HEADING["en"]), "en")
    ja_row = language_row(table_rows(docs["ja"], TABLE_HEADING["ja"]), "ja")
    if not en_row or not ja_row:
        return
    en_example, ja_example = example_names(en_row[1]), example_names(ja_row[1])
    if not en_example or not ja_example:
        fail("table", "the 'another language' row has no (...) example in both READMEs")
        return
    if en_example != ja_example:
        fail(
            "table",
            f"'another language' example differs: README.md {sorted(en_example)} vs README.ja.md {sorted(ja_example)}",
        )
    if defaults is None:
        return
    if len(defaults) != len(en_example) or len(defaults) != len(ja_example):
        fail(
            "table",
            "the 'another language' example does not match the shipped default names in count: "
            f"the scripts ship {sorted(defaults)} ({len(defaults)}), README.md gives {sorted(en_example)} "
            f"({len(en_example)}) and README.ja.md gives {sorted(ja_example)} ({len(ja_example)})",
        )
    clashing = (en_example | ja_example) & defaults
    if not clashing:
        return
    if not any(NON_LATIN.search(name) for name in defaults):
        note(
            "'another language' row example check skipped: the shipped default names "
            f"{sorted(clashing)} are already written in Latin letters, so repeating them "
            "says nothing about changing the language"
        )
        return
    for name, example in (("en", en_example), ("ja", ja_example)):
        if example & clashing:
            fail("table", f"{name}: the 'another language' row advertises the shipped default names {sorted(clashing)}")


def language_row_is_clear(rows, name, fail):
    """The row must say which language the repository ships in, in its own language."""
    found = language_row(rows, name)
    if not found:
        return
    marker = DEFAULT_LANGUAGE_CELL[name]
    if marker not in found[1].split("|")[1]:
        fail(
            "table",
            f"{name}: the 'another language' row does not name the language the repository ships in "
            f"({marker}) in its first column, so a reader cannot tell which text the row is about",
        )


def check_meaning(docs, fail):
    """Every claim must be made in both files, each in its own language's wording."""
    bodies = {name: "\n".join(lines) for name, lines in docs.items()}
    names = {"en": "README.md", "ja": "README.ja.md"}
    for claim in CLAIMS:
        label, patterns = claim[0], dict(zip(("en", "ja"), claim[1:]))
        missing = [names[name] for name, pattern in patterns.items() if not re.search(pattern, bodies[name])]
        if missing:
            fail("meaning", f"claim '{label}' is missing from {', '.join(sorted(missing))}: the two READMEs no longer say the same thing")


def check_repo_hygiene(fail, note):
    try:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        fail("repo", f".gitignore cannot be read ({error}): build cache files are not kept out of the repository")
    else:
        missing = [rule for rule in IGNORE_RULES if rule not in ignore.splitlines()]
        if missing:
            fail("repo", f".gitignore does not ignore {', '.join(missing)}: a build cache can end up committed again")
    files = committed_files(note)
    if files is None:
        return
    offenders = sorted(path for path in files if COMMITTED_CACHE.search(path))
    if offenders:
        fail("repo", "build cache committed to the repository: " + ", ".join(offenders))


def committed_files(note):
    """The paths git says are tracked, or None when this checkout cannot tell us.

    None is always a note, never a problem: whether a git binary happens to be on PATH says
    nothing about the READMEs, and a tarball checkout that kept a .git directory but has no
    git to run is a packaging detail, not a broken document.
    """
    if not (ROOT / ".git").exists():
        note("no git metadata in this checkout: the committed build-cache check does not apply")
        return None
    try:
        done = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True)
    except OSError as error:
        note(f"git cannot be run ({error}) although this checkout has a .git: the committed build-cache check was skipped")
        return None
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip()
        note(f"git ls-files failed ({detail or 'no output'}): the committed build-cache check was skipped")
        return None
    return [path.decode("utf-8") for path in done.stdout.split(b"\0") if path]


def test_readme_files_exist():
    assert all(path.is_file() for path in FILES.values()), "both README.md and README.ja.md must exist"


def test_switch_line_directly_under_the_title():
    assert problems("switch") == [], "\n".join(problems("switch"))


def test_each_readme_is_written_in_its_language():
    assert problems("language") == [], "\n".join(problems("language"))


def test_headings_match_in_number_and_order():
    assert problems("headings") == [], "\n".join(problems("headings"))


def test_sections_match_in_content():
    assert problems("sections") == [], "\n".join(problems("sections"))


def test_relative_links_resolve_and_match():
    assert problems("links") == [], "\n".join(problems("links"))


def test_external_links_are_known_good_and_reachable():
    assert problems("external") == [], "\n".join(problems("external"))


def test_customising_table_matches():
    assert problems("table") == [], "\n".join(problems("table"))


def test_readmes_say_the_same_things():
    assert problems("meaning") == [], "\n".join(problems("meaning"))


def test_no_build_cache_is_committed():
    assert problems("repo") == [], "\n".join(problems("repo"))


def test_external_links_are_verified_live_or_declared_skipped():
    """Every pinned link is answered live, or the run says out loud why it could not be tried."""
    result = analyze()
    unverified = sorted(set(result["pinned_external"]) - set(result["verified_external"]))
    if not unverified:
        return
    unexplained = [url for url in unverified if not any(url in message for message in result["notes"])]
    assert not unexplained, (
        f"external links went unanswered with no note saying why: {', '.join(unexplained)}; "
        "a link this machine could have reached is a broken link, not a gap"
    )
    if not network_available():
        assert any(SKIP_MARK in message for message in result["notes"]), (
            "a machine that cannot leave the house must name the skipped live check in its notes"
        )
        assert not result["verified_external"], "a run that skipped the live check can have verified nothing"


def test_unanswered_external_links_are_notes_unless_the_job_demands_the_proof():
    """A link this machine could not get an answer from is a named gap, not a failed README."""
    url = "https://vrchat.com/home/download"
    unreachable = (
        (False, None, ""),
        (True, None, "no connection (timed out)"),
        (True, 400, "HTTP 400"),
        (True, 404, "HTTP 404"),
        (True, 410, "HTTP 410"),
    )
    for resolved, status, detail in unreachable:
        kind, message = link_verdict(url, "vrchat.com", resolved, status, detail)
        assert kind == "note", f"a normal run must not depend on this machine's network ({resolved}, {status})"
        assert url in message, f"the note must name the link it could not verify: {message}"
        strict, message = link_verdict(url, "vrchat.com", resolved, status, detail, strict=True)
        assert strict == "fail", f"a job that demands the live proof must fail on {detail or 'no connection'}: {message}"
    for status in (403, 429, 503):
        for strict in (False, True):
            assert link_verdict(url, "vrchat.com", True, status, f"HTTP {status}", strict=strict)[0] == "note"
    assert link_verdict(url, "vrchat.com", True, 200, "")[0] == "ok"
    kind, message = offline_verdict([url])
    assert kind == "note", "a machine with no network skips the live check instead of failing a normal run"
    assert SKIP_MARK in message, "the skip must be named, not implied"
    os.environ[REQUIRE_LIVE_LINKS] = "1"
    try:
        kind, message = offline_verdict([url])
        assert kind == "note", "an environment that cannot fetch cannot be asked to prove anything about a link"
        assert REQUIRE_LIVE_LINKS in message and SKIP_MARK in message, (
            f"the note must say which demand it could not meet: {message}"
        )
    finally:
        del os.environ[REQUIRE_LIVE_LINKS]


def test_offline_external_check_is_a_note_a_normal_run_can_tolerate():
    docs = {name: read_doc(path, lambda category, message: None) for name, path in FILES.items()}
    original = network_available
    globals()["network_available"] = lambda: False
    try:
        recorded, noted = [], []
        pinned = check_external(
            docs,
            lambda category, message: recorded.append((category, message)),
            lambda message: noted.append(message),
            {},
        )
        assert pinned, "the pinned external links must still be listed when the network is down"
        assert not recorded, "an offline laptop or an egress-blocked CI runner must not fail a normal test run"
        assert any(SKIP_MARK in message for message in noted), "the skipped live check must be said out loud"
        os.environ[REQUIRE_LIVE_LINKS] = "1"
        try:
            demanded, demanded_notes = [], []
            check_external(
                docs,
                lambda category, message: demanded.append((category, message)),
                lambda message: demanded_notes.append(message),
                {},
            )
            assert not demanded, (
                f"{REQUIRE_LIVE_LINKS} on a machine with no egress asks for a proof the environment cannot "
                f"produce, so it must not fail the READMEs: {demanded}"
            )
            assert any(
                REQUIRE_LIVE_LINKS in message and SKIP_MARK in message for message in demanded_notes
            ), f"the note must name the demand it could not meet: {demanded_notes}"
        finally:
            del os.environ[REQUIRE_LIVE_LINKS]
    finally:
        globals()["network_available"] = original


def test_files_the_readmes_link_to_are_in_this_checkout():
    """Each repository file the READMEs link to is here, or its absence is a named gap."""
    result = analyze()
    reported, noted = result["problems"]["links"], result["notes"]
    for target in REPO_LINKS:
        if (ROOT / target).is_file():
            continue
        assert not any(target in message for message in reported), (
            f"{target} is not in this checkout: a checkout that strips out a committed repository file has "
            f"a packaging gap, and that must not be reported as a broken README link: {reported}"
        )
        assert any(target in message for message in noted), (
            f"{target} is not in this checkout and no note says so, so the link to it passed unverified"
        )


def test_a_checkout_without_a_linked_file_reports_a_broken_link():
    """A link to something this checkout does not have is still a broken link and is reported."""
    scratch = scratch_dir()
    if scratch is None:
        print("note: .agent-tmp could not be created in this checkout, so the stripped-checkout case was skipped")
        return
    with scratch as tmp:
        stripped_root = Path(tmp)
        for target in REPO_LINKS:
            here = stripped_root / target
            here.parent.mkdir(parents=True, exist_ok=True)
            here.write_text("placeholder for a committed repository file\n", encoding="utf-8")
        lines = [f"[demo]({target})" for target in sorted(REPO_LINKS)] + ["[missing media](docs/absent.png)"]
        original = ROOT
        globals()["ROOT"] = stripped_root
        try:
            reported, noted = [], []
            targets = relative_targets(
                lines, "en", lambda category, message: reported.append((category, message)), lambda message: noted.append(message)
            )
            assert targets == {target for target in REPO_LINKS} | {"docs/absent.png"}, (
                f"every linked target must be collected: {sorted(targets)}"
            )
            assert [category for category, _ in reported] == ["links"], (
                f"a link to a target that is not here must be reported as broken: {reported}"
            )
            assert all("broken link" in message for _, message in reported), f"not a broken-link report: {reported}"
            assert not noted, f"nothing else may be reported while the linked repository files are present: {noted}"

            (stripped_root / "LICENSE").unlink()
            gap_reported, gap_noted = [], []
            relative_targets(
                [f"[demo]({target})" for target in sorted(REPO_LINKS)],
                "en",
                lambda category, message: gap_reported.append((category, message)),
                lambda message: gap_noted.append(message),
            )
            assert not gap_reported, (
                f"a checkout that leaves out a committed repository file has a packaging gap, not a broken link: {gap_reported}"
            )
            assert any("LICENSE" in message for message in gap_noted), (
                f"the packaging gap must be named so the link is not counted as verified: {gap_noted}"
            )
        finally:
            globals()["ROOT"] = original


def test_a_checkout_with_no_git_metadata_still_runs_the_gitignore_rules():
    """Both git-less shapes — no .git directory, and a .git with no git to run — are notes."""
    scratch = scratch_dir()
    if scratch is None:
        print("note: .agent-tmp could not be created in this checkout, so the git-less checkout cases were skipped")
        return

    class NoGit:
        def run(self, *args, **kwargs):
            raise FileNotFoundError(2, "git: command not found")

    with scratch as tmp:
        stripped_root = Path(tmp)
        (stripped_root / ".gitignore").write_text("\n".join(IGNORE_RULES) + "\n", encoding="utf-8")
        original_root, original_subprocess = ROOT, subprocess

        def run_case(with_git_metadata, git):
            if with_git_metadata:
                (stripped_root / ".git").mkdir(exist_ok=True)
            else:
                shutil.rmtree(str(stripped_root / ".git"), ignore_errors=True)
            globals()["ROOT"] = stripped_root
            globals()["subprocess"] = original_subprocess if git is None else git
            reported, noted = [], []
            try:
                check_repo_hygiene(
                    lambda category, message: reported.append((category, message)),
                    lambda message: noted.append(message),
                )
            finally:
                globals()["ROOT"] = original_root
                globals()["subprocess"] = original_subprocess
            return reported, noted

        for with_git_metadata, git, label in ((False, None, "no .git directory"), (True, NoGit(), "a .git but no git binary")):
            reported, noted = run_case(with_git_metadata, git)
            assert not reported, f"a checkout with {label} must not fail the README checks: {reported}"
            assert any("git" in message for message in noted), (
                f"the skipped committed-file scan for a checkout with {label} must be said out loud: {noted}"
            )

        (stripped_root / ".gitignore").write_text("Library/\n", encoding="utf-8")
        reported, _ = run_case(False, None)
        assert any(category == "repo" for category, _ in reported), (
            f"the .gitignore rule check must run even where git metadata is missing: {reported}"
        )
        shutil.rmtree(str(stripped_root / ".gitignore"), ignore_errors=True)
        reported, noted = run_case(False, None)
        assert any(category == "repo" for category, _ in reported), (
            f"a checkout with no .gitignore must be told the cache rules cannot be checked: {reported}"
        )


def test_the_committed_file_scan_runs_when_git_answers():
    """git answers: the tracked list; git missing or answering badly: a note and no problem."""
    noted = []
    files = committed_files(lambda message: noted.append(message))
    if files is None:
        assert any("git" in message for message in noted), (
            f"a checkout this tool cannot scan must say why the scan was skipped: {noted}"
        )
        return
    assert "README.md" in files and "tests/test_readme_parity.py" in files, f"tracked files look wrong: {files[:5]}"

    real_subprocess = subprocess

    class FailingGit:
        def run(self, *args, **kwargs):
            return real_subprocess.CompletedProcess(args, 128, b"", b"git ls-files: not a git repository")

    scratch = scratch_dir()
    if scratch is None:
        print("note: .agent-tmp could not be created in this checkout, so the failing-git case was skipped")
        return
    with scratch as tmp:
        stripped_root = Path(tmp)
        (stripped_root / ".git").mkdir(exist_ok=True)
        original_root, original_subprocess = ROOT, subprocess
        globals()["ROOT"] = stripped_root
        globals()["subprocess"] = FailingGit()
        failed_notes = []
        try:
            files = committed_files(lambda message: failed_notes.append(message))
        finally:
            globals()["ROOT"] = original_root
            globals()["subprocess"] = original_subprocess
    assert files is None, "a checkout whose git ls-files fails must fall back to a note, not a file list"
    assert any("git ls-files" in message for message in failed_notes), (
        f"the failed committed-file scan must be said out loud: {failed_notes}"
    )


def test_shipped_names_are_read_from_every_common_initialiser_form():
    forms = (
        'public class ShoutManager { public string[] shoutNames = { "マルクス", "ニーチェ", "フロイト" }; }',
        'shoutNames = new string[] { "マルクス", "ニーチェ", "フロイト" };',
        'public string[] shoutNames = new[] {\n    "マルクス",\n    "ニーチェ",\n    "フロイト"\n};',
        'shoutNames = new List<string> { "マルクス", "ニーチェ", "フロイト" };',
        'shoutNames = new string[] {\n    "マルクス！",\n    "ニーチェ！",\n    "フロイト！"\n};\nprivate int unrelated = 3;',
    )
    expected = {"マルクス", "ニーチェ", "フロイト"}
    for source in forms:
        names, reason = parse_shipped_names(source)
        assert names == expected, f"the defaults could not be read from {source!r} ({reason})"


def test_shipped_names_that_cannot_be_read_are_a_named_skip():
    assert parse_shipped_names("public class ShoutManager { int shoutCount = 3; }")[0] is None
    assert parse_shipped_names("public string[] shoutNames = new string[MaxShouts];")[0] is None
    assert parse_shipped_names('public string[] shoutNames = { };')[0] is None

    scratch = scratch_dir()
    if scratch is None:
        print("note: .agent-tmp could not be created, so the missing-script case was not run")
        return
    with scratch as tmp:
        original = MANAGER
        try:
            written = Path(tmp) / "present" / "ShoutManager.cs"
            written.parent.mkdir(parents=True, exist_ok=True)
            written.write_text(
                'public string[] shoutNames = { "マルクス", "ニーチェ", "フロイト" };\n', encoding="utf-8"
            )
            globals()["MANAGER"] = written
            reported = []
            assert default_names(reported.append) == {"マルクス", "ニーチェ", "フロイト"}
            assert not reported, f"a script that can be read needs no note: {reported}"

            globals()["MANAGER"] = Path(tmp) / "absent" / "ShoutManager.cs"
            reported = []
            assert default_names(reported.append) is None
            assert any("ShoutManager.cs" in message and "could not be read" in message for message in reported), (
                f"a checkout without the script must say the defaults cannot be read: {reported}"
            )
        finally:
            globals()["MANAGER"] = original


def test_a_script_that_is_there_but_says_nothing_is_also_a_named_skip():
    scratch = scratch_dir()
    if scratch is None:
        print("note: .agent-tmp could not be created, so the unreadable-script case was not run")
        return
    with scratch as tmp:
        original = MANAGER
        try:
            silent = Path(tmp) / "ShoutManager.cs"
            silent.write_text("public class ShoutManager { int shoutCount = 3; }\n", encoding="utf-8")
            globals()["MANAGER"] = silent
            reported = []
            assert default_names(reported.append) is None
            assert any("ShoutManager.cs" in message and "shoutNames" in message for message in reported), (
                f"a script without a readable name list must say so: {reported}"
            )
        finally:
            globals()["MANAGER"] = original


def test_the_example_is_compared_with_the_names_the_scripts_ship():
    docs = {
        "en": [
            "## Customising",
            "| What you want | How |",
            "|---|---|",
            "| Use it in another language (the text here is Japanese by default) | "
            "Rewrite `shoutNames` (e.g. Marx / Nietzsche / Freud) |",
        ],
        "ja": [
            "## カスタマイズ",
            "| やりたいこと | 方法 |",
            "|---|---|",
            "| 英語など他の言語にする（ここは既定で日本語） | `shoutNames` を書き換える（例：Marx / Nietzsche / Freud） |",
        ],
    }
    defaults = {"マルクス", "ニーチェ", "フロイト"}

    def keep(category, message):
        raise AssertionError(f"the shipped example must pass: {category}: {message}")

    def silent(message):
        return None

    check_language_row(docs, defaults, keep, silent)

    for name in ("en", "ja"):
        longer = [
            line.replace("Marx / Nietzsche / Freud", "Marx / Nietzsche / Freud / Kierkegaard")
            if name == "en"
            else line.replace("Marx / Nietzsche / Freud", "Marx / Nietzsche / Freud / Kierkegaard")
            for line in docs[name]
        ]
        reported = []
        check_language_row(
            {**docs, name: longer}, defaults, lambda category, message: reported.append(message), silent
        )
        assert any("in count" in message for message in reported), (
            f"{name}: an example listing {len(defaults) + 1} names against {len(defaults)} shipped names "
            f"must be reported: {reported}"
        )

    clashed = {
        "en": [line.replace("Marx / Nietzsche / Freud", "マルクス / ニーチェ / フロイト") for line in docs["en"]],
        "ja": list(docs["ja"]),
    }
    reported = []
    check_language_row(clashed, defaults, lambda category, message: reported.append((category, message)), silent)
    assert any(
        category == "table" and "advertises the shipped default names" in message for category, message in reported
    ), f"an example that repeats the shipped defaults must be reported: {reported}"


def test_committed_cache_detector_names_cache_files_and_nothing_else():
    committed = [
        "tests/__pycache__/test_readme_parity.cpython-310-pytest-8.4.2.pyc",
        "tests/test_readme_parity.pyc",
        "tests/test_readme_parity.pyo",
        ".pytest_cache/README",
        "sub/.pytest_cache/v/cache/lastfailed",
    ]
    ordinary = [
        "README.md",
        "README.ja.md",
        "tests/test_readme_parity.py",
        "Assets/Scripts/ShoutManager.cs",
        "docs/pytest_cache_notes.md",
    ]
    assert all(COMMITTED_CACHE.search(path) for path in committed), "committed build cache must be named"
    assert not [path for path in ordinary if COMMITTED_CACHE.search(path)], "source files must not be reported as cache"


def main():
    result = analyze()
    failures = [message for category in CATEGORIES for message in result["problems"][category]]
    if failures:
        for message in failures:
            print(f"FAIL {message}")
        print(f"{len(failures)} problem(s)")
        return 1
    for note in result["notes"]:
        print(f"note: {note}")
    verified = result["verified_external"]
    print(
        "README parity: OK (switch line, language of each file, heading count/order, "
        "section content and inline code, relative links, "
        f"external links {sorted(verified) if verified else 'declared skipped'}, "
        "Customising language row, same claims in both languages, no committed build cache)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
