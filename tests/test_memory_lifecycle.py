import inspect
import math
import sqlite3
from dataclasses import asdict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from research.lifecycle_fixture import build_stream
from research.memory_lifecycle import Archive, Config, LifecycleError, MemorySession, similarity


def session(policy="decay_replay", **kwargs):
    archive = Archive(":memory:")
    return archive, MemorySession(archive, Config(policy=policy, **kwargs))


def test_forgetting_preserves_originals_and_can_recover_them(tmp_path):
    path = tmp_path / "memories.sqlite"
    archive = Archive(path)
    controller = MemorySession(archive, Config(capacity=1, recovery_rows=1, maintenance_rows=0))
    controller.remember("old", "first", "red blue green", 1)
    controller.remember("new", "second", "violet orange", 2)
    assert controller.active_ids == ("new",)
    assert archive.get("old").text == "red blue green"
    result = controller.query("red blue green", 3)
    assert result.hits[0].memory.identifier == "old"
    assert result.reactivated == ("old",)
    assert controller.active_ids == ("old",)
    assert archive.get("new").text == "violet orange"
    archive.close()
    reopened = Archive(path)
    assert reopened.get("old").text == "red blue green"
    assert reopened.get("new").text == "violet orange"
    cold = MemorySession(reopened, Config(capacity=1))
    assert cold.active_ids == ("new",)
    assert cold.queries == cold.cursor == 0
    reopened.close()


def test_corrections_append_and_superseded_archive_hits_never_return():
    archive, controller = session(capacity=1, recovery_rows=2, maintenance_rows=0)
    old = controller.remember("old", "release", "amber record rare", 1)
    new = controller.remember("new", "release", "violet successor", 2)
    assert new.previous == old.identifier
    assert archive.count == 2
    assert archive.get("old") == old
    result = controller.query("amber record rare", 3)
    assert not result.hits
    assert result.work.recovery_rows == 2
    assert controller.query("violet successor", 4).hits[0].memory.identifier == "new"
    archive.close()


def test_archive_originals_reject_update_and_delete():
    archive = Archive(":memory:")
    archive.put("one", "key", "original source", 1)
    for sql in ("UPDATE records SET text='modified'", "DELETE FROM records"):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            archive.connection.execute(sql)
    assert archive.get("one").text == "original source"
    archive.close()


def test_failed_head_replacement_rolls_back_entire_append(tmp_path):
    archive = Archive(tmp_path / "memory.sqlite")
    old = archive.put("old", "key", "original source", 1)
    archive.connection.executescript("""
        CREATE TRIGGER reject_head BEFORE UPDATE ON heads
        BEGIN SELECT RAISE(ABORT, 'injected failure'); END;
    """)
    with pytest.raises(LifecycleError, match="transaction rejected"):
        archive.put("new", "key", "new source", 2)
    assert archive.count == 1 and archive.current(old)
    with pytest.raises(LifecycleError, match="unknown record"):
        archive.get("new")
    archive.connection.execute("DROP TRIGGER reject_head")
    assert archive.put("new", "key", "new source", 2).previous == "old"
    archive.close()


def test_duplicate_identifier_does_not_change_other_head():
    archive = Archive(":memory:")
    first = archive.put("one", "alpha", "red blue", 1)
    second = archive.put("two", "beta", "green violet", 2)
    with pytest.raises(LifecycleError, match="transaction rejected"):
        archive.put("one", "beta", "wrong replacement", 3)
    assert archive.count == 2 and archive.current(first) and archive.current(second)
    archive.close()


@pytest.mark.parametrize("rows", [0, 1, 2, 3, 10])
@pytest.mark.parametrize("cursor", [0, 1, 2, 3, 99])
def test_cyclic_scan_respects_physical_budget_and_has_no_duplicates(rows, cursor):
    archive = Archive(":memory:")
    for index in range(3):
        archive.put(str(index), "same-key", f"original text {index}", index)
    found, new_cursor = archive.scan(cursor, rows)
    assert len(found) == min(rows, 3)
    assert len({record.identifier for record in found}) == len(found)
    assert new_cursor == (found[-1].sequence if found else cursor)
    archive.close()


def test_recovery_budget_includes_already_hot_and_superseded_rows():
    archive, controller = session(capacity=1, recovery_rows=1, maintenance_rows=0)
    controller.remember("stale", "key", "amber original", 1)
    controller.remember("hot", "key", "violet current", 2)
    controller.remember("dormant", "other", "target rare", 3)
    controller.remember("latest", "latest-key", "unrelated noise", 4)
    first = controller.query("target rare", 5)
    assert not first.hits
    assert first.work.recovery_rows == 1 and first.work.recovery_scores == 0
    second = controller.query("target rare", 6)
    assert not second.hits and second.work.recovery_rows == 1
    third = controller.query("target rare", 7)
    assert third.hits[0].memory.identifier == "dormant"
    assert third.work.recovery_rows == 1
    archive.close()


def test_coverage_replay_breaks_confident_wrong_hot_feedback_without_fake_usage():
    archive, controller = session(
        capacity=1, recovery_rows=0, maintenance_rows=1, maintenance_every=1, threshold=0.45
    )
    controller.remember("target", "first", "red blue green", 1)
    controller.remember("distractor", "second", "red blue", 2)
    first = controller.query("red blue green", 3)
    assert first.hits[0].memory.identifier == "distractor"
    assert first.work.recovery_rows == 0
    assert first.replay_promoted == ("target",)
    assert first.work.replay_rows == first.work.replay_scores == 1
    assert controller.active["target"].hits == 0
    assert controller.query("red blue green", 4).hits[0].memory.identifier == "target"
    archive.close()
    control_archive, control = session(
        policy="decay", capacity=1, recovery_rows=0, maintenance_rows=1, maintenance_every=1
    )
    control.remember("target", "first", "red blue green", 1)
    control.remember("distractor", "second", "red blue", 2)
    assert control.query("red blue green", 3).hits[0].memory.identifier == "distractor"
    assert control.query("red blue green", 4).hits[0].memory.identifier == "distractor"
    control_archive.close()


def test_probe_ablation_gets_same_scheduled_row_allowance():
    archive, controller = session(
        policy="decay_probe", capacity=1, recovery_rows=0, maintenance_rows=1, maintenance_every=1
    )
    controller.remember("target", "first", "red blue green", 1)
    controller.remember("distractor", "second", "red blue", 2)
    result = controller.query("red blue green", 3)
    assert result.hits[0].memory.identifier == "target"
    assert result.work.recovery_rows == 1 and result.work.replay_rows == 0
    assert result.work.replay_scores == 0
    archive.close()


def test_shared_ranker_matches_independent_binary_vector_formula():
    archive, controller = session(policy="full")
    documents = {"first": "red blue", "second": "red blue green", "third": "violet yellow"}
    for tick, (identifier, text) in enumerate(documents.items(), 1):
        controller.remember(identifier, identifier, text, tick)
    cue = {"red", "green"}
    vocabulary = sorted(cue | set(" ".join(documents.values()).split()))
    q = [int(word in cue) for word in vocabulary]
    expected = []
    for identifier, text in documents.items():
        v = [int(word in text.split()) for word in vocabulary]
        score = math.fsum(a * b for a, b in zip(q, v, strict=True)) / math.sqrt(sum(q) * sum(v))
        if score > 0:
            expected.append((identifier, score))
    expected.sort(key=lambda item: -item[1])
    hits = controller.query("red green", 4, top_k=3).hits
    assert [hit.memory.identifier for hit in hits] == [identifier for identifier, _ in expected]
    assert [hit.score for hit in hits] == pytest.approx([score for _, score in expected])
    assert similarity(frozenset(), frozenset({"red"})) == 0
    archive.close()


def test_query_failure_does_not_commit_session_state(monkeypatch):
    archive, controller = session(maintenance_every=1)
    controller.remember("one", "key", "red blue", 1)
    before = (
        controller.tick,
        controller.queries,
        controller.cursor,
        tuple(controller.history),
        dict(controller.active),
    )

    def fail(*args):
        raise RuntimeError("injected read failure")

    monkeypatch.setattr(archive, "scan", fail)
    with pytest.raises(RuntimeError, match="injected read failure"):
        controller.query("violet", 2)
    assert (
        controller.tick,
        controller.queries,
        controller.cursor,
        tuple(controller.history),
        controller.active,
    ) == before
    archive.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capacity": 0},
        {"capacity": True},
        {"recovery_rows": -1},
        {"maintenance_every": 0},
        {"history_queries": 0},
        {"half_life": float("nan")},
        {"half_life": True},
        {"threshold": 0.0},
        {"threshold": "bad"},
        {"policy": "unknown"},
    ],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(LifecycleError):
        Config(**kwargs)


@pytest.mark.parametrize("text", ["", "the and", "!", "x" * 513, None])
def test_invalid_query_does_not_advance_clock(text):
    archive, controller = session()
    with pytest.raises(LifecycleError):
        controller.query(text, 5)
    assert controller.tick == controller.queries == 0
    archive.close()


def test_future_replay_and_backwards_time_rejected_before_mutation():
    archive, controller = session()
    controller.remember("future", "key", "red blue", 10)
    with pytest.raises(LifecycleError, match="backwards"):
        controller.query("red", 9)
    with pytest.raises(LifecycleError, match="backwards"):
        controller.remember("earlier", "other", "violet", 8)
    assert archive.count == 1 and controller.queries == 0
    archive.close()


def test_storage_limit_and_unknown_format_fail_explicitly(tmp_path):
    path = tmp_path / "memory.sqlite"
    archive = Archive(path, max_records=1)
    archive.put("one", "first", "red blue", 1)
    with pytest.raises(LifecycleError, match="exhausted"):
        archive.put("two", "second", "green violet", 2)
    archive.connection.execute("UPDATE format SET version='unknown'")
    archive.connection.commit()
    archive.close()
    with pytest.raises(LifecycleError, match="unknown archive version"):
        Archive(path)


def test_checksum_corruption_is_detected_on_reopen(tmp_path):
    path = tmp_path / "memory.sqlite"
    archive = Archive(path)
    archive.put("one", "first", "red blue", 1)
    archive.connection.execute("DROP TRIGGER immutable_update")
    archive.connection.execute("UPDATE records SET text='tampered source'")
    archive.connection.commit()
    archive.close()
    with pytest.raises(LifecycleError, match="checksum"):
        Archive(path)


def test_no_answer_labels_or_scenario_metadata_enter_controller_api():
    assert set(inspect.signature(MemorySession.query).parameters) == {
        "self",
        "text",
        "tick",
        "top_k",
    }
    assert set(inspect.signature(MemorySession.remember).parameters) == {
        "self",
        "identifier",
        "key",
        "text",
        "tick",
    }
    first = build_stream(7)
    assert first == build_stream(7) and first != build_stream(23)
    seen = set()
    for event in first:
        if event["kind"] == "remember":
            seen.add(event["identifier"])
        else:
            assert event["expected"] in seen


@settings(max_examples=30, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 5), st.booleans()), min_size=1, max_size=45))
def test_generated_sequences_preserve_capacity_versions_sources_and_budgets(operations):
    archive, controller = session(
        capacity=3, recovery_rows=2, maintenance_rows=3, maintenance_every=2
    )
    originals = {}
    heads = {}
    queries = 0
    for tick, (key, write) in enumerate(operations, start=1):
        if write:
            identifier = f"record-{tick}"
            text = f"project{key} release{tick}"
            controller.remember(identifier, f"key{key}", text, tick)
            originals[identifier] = text
            heads[f"key{key}"] = identifier
        else:
            result = controller.query(f"project{key}", tick)
            queries += 1
            assert result.work.recovery_rows <= 2
            assert result.work.replay_rows <= (3 if queries % 2 == 0 else 0)
            assert result.work.replay_scores <= result.work.replay_rows * 8
            for hit in result.hits:
                assert heads[hit.memory.key] == hit.memory.identifier
                assert hit.memory.tick <= tick
            assert all(value >= 0 for value in asdict(result.work).values())
        assert len(controller.active) <= 3
        assert archive.count == len(originals)
        for identifier, text in originals.items():
            assert archive.get(identifier).text == text
    archive.close()


def test_invalid_utf8_and_oversized_clock_fail_without_archive_write():
    archive, controller = session()
    with pytest.raises(LifecycleError, match="UTF-8"):
        controller.remember("one", "key", "red \ud800", 1)
    with pytest.raises(LifecycleError, match="integer"):
        controller.remember("one", "key", "red blue", 2**63)
    with pytest.raises(LifecycleError, match="UTF-8"):
        controller.query("red \ud800", 1)
    assert archive.count == 0 and controller.tick == controller.queries == 0
    archive.close()


def test_console_round_trip_rejects_labels_and_keeps_corrections(tmp_path):
    import io
    import json

    from research.memory_console import serve

    path = tmp_path / "console.sqlite"
    archive = Archive(path)
    controller = MemorySession(archive, Config(capacity=1))
    commands = [
        {
            "operation": "remember",
            "identifier": "old",
            "key": "release",
            "text": "red blue",
            "tick": 1,
        },
        {
            "operation": "remember",
            "identifier": "new",
            "key": "release",
            "text": "green violet",
            "tick": 2,
        },
        {"operation": "query", "text": "green violet", "tick": 3, "expected": "new"},
        {"operation": "query", "text": "green violet", "tick": 3},
        {"operation": "status"},
    ]
    output = io.StringIO()
    assert serve(controller, io.StringIO("\n".join(map(json.dumps, commands)) + "\n"), output) == 0
    rows = list(map(json.loads, output.getvalue().splitlines()))
    assert [row["ok"] for row in rows] == [True, True, False, True, True]
    assert rows[3]["hits"][0]["memory"]["identifier"] == "new"
    assert rows[4]["original_records"] == 2 and rows[4]["queries_this_session"] == 1
    archive.close()
    reopened = Archive(path)
    assert reopened.get("old").text == "red blue"
    assert reopened.get("new").previous == "old"
    reopened.close()


def test_console_oversized_line_stops_without_partial_command_execution():
    import io
    import json

    from research.memory_console import serve

    archive, controller = session()
    output = io.StringIO()
    assert serve(controller, io.StringIO("x" * 65537 + "\n"), output) == 2
    assert not json.loads(output.getvalue())["ok"]
    assert controller.tick == archive.count == 0
    archive.close()
