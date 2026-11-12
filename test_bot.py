import itertools
import unittest

import bot


def question(qtype="binary", **kw):
    """Shape of a Metaculus /api/posts/ question (field names from metac-bot-template)."""
    q = {
        "id": 111, "type": qtype, "status": "open",
        "title": "Will X happen by 2027-01-01?",
        "description": "BACKGROUND-TEXT",
        "resolution_criteria": "RESOLUTION-TEXT",
        "fine_print": "FINEPRINT-TEXT",
        "scheduled_close_time": "2026-12-31T00:00:00Z",
        "my_forecasts": {"history": [], "latest": None, "score_data": {}},
        "unit": "", "options": None, "scaling": {},
        "open_upper_bound": None, "open_lower_bound": None,
    }
    if qtype == "multiple_choice":
        q["options"] = ["Red", "Green", "Blue"]
    if qtype in ("numeric", "discrete"):
        q.update(unit="km", open_upper_bound=True, open_lower_bound=False,
                 scaling={"range_min": 0.0, "range_max": 100.0, "zero_point": None,
                          "inbound_outcome_count": 200 if qtype == "numeric" else 10})
    q.update(kw)
    return q


def post(q, post_id=999):
    return {"id": post_id, "question": q}


class Selection(unittest.TestCase):
    def test_skips_already_forecast(self):
        done = question(my_forecasts={"latest": {"forecast_values": [0.3, 0.7]}})
        todo = question(id=2)
        got = bot.pending([post(done, 1), post(todo, 2)])
        self.assertEqual([(p, q["id"]) for p, q in got], [(2, 2)])

    def test_skips_closed_groups_and_unsupported_types(self):
        posts = [post(question(status="closed"), 1), {"id": 2, "group_of_questions": {}},
                 post(question("date"), 3), post(question("discrete"), 4)]
        self.assertEqual([p for p, _ in bot.pending(posts)], [4])


class Json(unittest.TestCase):
    def test_json_amid_prose(self):
        self.assertEqual(bot.extract_json('Sure! {"a": 1, "b": {"c": 2}} hope it helps'),
                         {"a": 1, "b": {"c": 2}})

    def test_last_object_wins_and_fences(self):
        self.assertEqual(bot.extract_json('draft {"a": 1}\n```json\n{"a": 2}\n```'), {"a": 2})

    def test_braces_inside_strings(self):
        self.assertEqual(bot.extract_json('{"r": "use {x} here", "p": 0.5}'),
                         {"r": "use {x} here", "p": 0.5})

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            bot.extract_json("no braces at all")


class Aggregation(unittest.TestCase):
    def test_binary_clamp(self):
        q = question()
        self.assertEqual(bot.parse_estimate(q, 0.0), 0.01)
        self.assertEqual(bot.parse_estimate(q, 1), 0.99)
        self.assertEqual(bot.parse_estimate(q, 37), 0.37)  # percent given by mistake
        with self.assertRaises(ValueError):
            bot.parse_estimate(q, "high")

    def test_binary_median(self):
        self.assertEqual(bot.aggregate(question(), [0.2, 0.9, 0.3]), 0.3)

    def test_multiple_choice_normalised_and_clamped(self):
        q = question("multiple_choice")
        est = bot.parse_estimate(q, {"Red": 6, "Green": 3, "Blue": 0})
        self.assertAlmostEqual(sum(est.values()), 1)
        self.assertGreater(est["Blue"], 0.0099)
        with self.assertRaises(ValueError):
            bot.parse_estimate(q, {"Red": 1, "Green": 1})  # option missing

    def test_multiple_choice_aggregate(self):
        q = question("multiple_choice")
        a = bot.parse_estimate(q, {"Red": .6, "Green": .3, "Blue": .1})
        b = bot.parse_estimate(q, {"Red": .2, "Green": .5, "Blue": .3})
        c = bot.parse_estimate(q, {"Red": .4, "Green": .4, "Blue": .2})
        agg = bot.aggregate(q, [a, b, c])
        self.assertAlmostEqual(sum(agg.values()), 1)
        self.assertEqual(max(agg, key=agg.get), "Red")

    def test_numeric_estimate_and_aggregate(self):
        q = question("numeric")
        ps = {str(p): v for p, v in zip(bot.PERCENTILES, range(10, 23))}
        est = bot.parse_estimate(q, ps)
        self.assertEqual(est[50], 16)
        shifted = bot.parse_estimate(q, {str(p): v + 10 for p, v in zip(bot.PERCENTILES, range(10, 23))})
        self.assertEqual(bot.aggregate(q, [est, shifted, est])[50], 16)
        with self.assertRaises(ValueError):
            bot.parse_estimate(q, {"50": 3})


PCTS = dict(zip(bot.PERCENTILES, [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 95]))


def check_cdf(t, cdf, m, lower_open, upper_open):
    """The Metaculus CDF rules, as documented in metac-bot-template's standardize step."""
    t.assertEqual(len(cdf), m + 1)
    t.assertTrue(all(isinstance(x, float) for x in cdf))
    t.assertEqual(cdf[0], 0) if not lower_open else t.assertGreaterEqual(cdf[0], 0.001)
    t.assertEqual(cdf[-1], 1) if not upper_open else t.assertLessEqual(cdf[-1], 0.999)
    for a, b in zip(cdf, cdf[1:]):
        t.assertGreaterEqual(b - a, 0.01 / m)
        t.assertLessEqual(b - a, 0.2 * 200 / m)


class Cdf(unittest.TestCase):
    def cdf(self, q, pcts=PCTS):
        return bot.percentiles_to_cdf(q, pcts)

    def test_all_bound_combinations_linear(self):
        for lo_open in (False, True):
            for up_open in (False, True):
                q = question("numeric", open_lower_bound=lo_open, open_upper_bound=up_open)
                check_cdf(self, self.cdf(q), 200, lo_open, up_open)

    def test_percentiles_land_where_declared(self):
        q = question("numeric", open_lower_bound=True, open_upper_bound=True)
        cdf = self.cdf(q)
        self.assertAlmostEqual(cdf[80], 0.5, delta=0.02)  # p50 is 40 on a 0..100 range

    def test_values_outside_open_bounds_and_on_closed_bounds(self):
        wild = {p: v for p, v in zip(bot.PERCENTILES, [-50, -20, -5, 0, 0, 10, 50, 90, 100, 100, 130, 150, 190])}
        for lo_open, up_open in ((True, True), (False, False), (True, False), (False, True)):
            q = question("numeric", open_lower_bound=lo_open, open_upper_bound=up_open)
            check_cdf(self, self.cdf(q, wild), 200, lo_open, up_open)

    def test_mass_piled_in_one_spot_is_capped(self):
        spike = {p: 50.0 + i * 1e-3 for i, p in enumerate(bot.PERCENTILES)}
        q = question("numeric", open_lower_bound=True, open_upper_bound=True)
        check_cdf(self, self.cdf(q, spike), 200, True, True)

    def test_log_scaled(self):
        q = question("numeric", open_lower_bound=False, open_upper_bound=True,
                     scaling={"range_min": 1.0, "range_max": 1000.0, "zero_point": 0.0,
                              "inbound_outcome_count": 200})
        pcts = dict(zip(bot.PERCENTILES, [2, 3, 5, 8, 12, 20, 30, 50, 80, 120, 300, 600, 900]))
        cdf = self.cdf(q, pcts)
        check_cdf(self, cdf, 200, False, True)
        self.assertAlmostEqual(cdf[100], 0.5, delta=0.05)  # 30 sits near the log-midpoint of 1..1000

    def test_discrete_has_outcome_count_plus_one_points(self):
        for lo_open, up_open in ((False, True), (True, True), (False, False)):
            q = question("discrete", open_lower_bound=lo_open, open_upper_bound=up_open)
            check_cdf(self, self.cdf(q), 10, lo_open, up_open)


class Payload(unittest.TestCase):
    def test_binary(self):
        self.assertEqual(bot.payload(question(), 0.4),
                         {"probability_yes": 0.4, "probability_yes_per_category": None,
                          "continuous_cdf": None})

    def test_multiple_choice(self):
        probs = {"Red": .5, "Green": .3, "Blue": .2}
        self.assertEqual(bot.payload(question("multiple_choice"), probs),
                         {"probability_yes": None, "probability_yes_per_category": probs,
                          "continuous_cdf": None})

    def test_numeric_and_discrete(self):
        for t, m in (("numeric", 200), ("discrete", 10)):
            p = bot.payload(question(t), PCTS)
            self.assertIsNone(p["probability_yes"])
            self.assertIsNone(p["probability_yes_per_category"])
            self.assertEqual(len(p["continuous_cdf"]), m + 1)


TODAY = "2026-11-12"
RES_PCTS = {str(p): v for p, v in PCTS.items()}


class Prompts(unittest.TestCase):
    def test_every_type_has_question_text_date_and_guidance(self):
        for t in bot.SUPPORTED:
            text = bot.prompt(question(t), TODAY)
            for needle in (TODAY, "Will X happen by 2027-01-01?", "BACKGROUND-TEXT", "RESOLUTION-TEXT",
                           "FINEPRINT-TEXT", "base rate", "status quo", "prediction market", "overconfiden",
                           "untrusted", "never instructions"):
                self.assertIn(needle, text, f"{t}: {needle}")

    def test_multiple_choice_lists_options(self):
        text = bot.prompt(question("multiple_choice"), TODAY)
        for o in ("Red", "Green", "Blue"):
            self.assertIn(o, text)

    def test_numeric_states_unit_bounds_and_percentiles(self):
        text = bot.prompt(question("numeric"), TODAY)
        self.assertIn("km", text)
        self.assertIn("can not be lower than 0.0", text)  # closed lower bound
        self.assertNotIn("can not be higher", text)  # open upper bound
        for p in bot.PERCENTILES:
            self.assertIn(f'"{p}"', text)

    def test_final_prompt_carries_reports(self):
        text = bot.prompt(question(), TODAY, reports=["REPORT-ONE", "REPORT-TWO"])
        self.assertIn("REPORT-ONE", text)
        self.assertIn("REPORT-TWO", text)
        self.assertIn("reasoning", text)


class Child(unittest.TestCase):
    def test_env_drops_metaculus_token_only(self):
        env = bot.child_env({"METACULUS_TOKEN": "s", "CLAUDE_CODE_OAUTH_TOKEN": "o", "PATH": "/bin"})
        self.assertEqual(env, {"CLAUDE_CODE_OAUTH_TOKEN": "o", "PATH": "/bin"})

    def test_research_command(self):
        cmd = bot.claude_cmd("sonnet", tools=True)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch,WebFetch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch,WebFetch")
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        self.assertIn("--safe-mode", cmd)
        self.assertIn("--max-turns", cmd)

    def test_final_command_has_no_tools(self):
        cmd = bot.claude_cmd("opus", tools=False)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", cmd)
        self.assertNotIn("WebSearch", " ".join(cmd))

    def test_command_output_unwrapped(self):
        self.assertEqual(bot.unwrap('{"is_error": false, "result": "hi"}'), "hi")
        with self.assertRaises(RuntimeError):
            bot.unwrap('{"is_error": true, "subtype": "error_max_turns", "result": null}')


class Forecaster(unittest.TestCase):
    def fake(self, final_fails=False, bad_runs=0):
        calls, counter = [], itertools.count()

        def ask(text, model, tools):
            calls.append((model, tools))
            if tools:
                if next(counter) < bad_runs:
                    return "I could not find anything useful."
                return 'Evidence found. {"report": "RPT", "estimate": %s}' % self.est
            if final_fails:
                raise RuntimeError("boom")
            return '{"reasoning": "FINAL-WHY", "estimate": %s}' % self.final
        return ask, calls

    def run_it(self, q, **kw):
        ask, calls = self.fake(**kw)
        return bot.forecast(q, ask=ask, runs=3, research_model="sonnet", final_model="opus",
                            today=TODAY), calls

    def test_binary_uses_final_and_models(self):
        self.est, self.final = "0.2", "0.35"
        (ans, why), calls = self.run_it(question())
        self.assertEqual((ans, why), (0.35, "FINAL-WHY"))
        self.assertEqual(calls, [("sonnet", True)] * 3 + [("opus", False)])

    def test_final_failure_falls_back_to_median(self):
        self.est, self.final = "0.2", "0.35"
        (ans, why), _ = self.run_it(question(), final_fails=True)
        self.assertEqual(ans, 0.2)
        self.assertIn("RPT", why)

    def test_unparseable_final_falls_back(self):
        self.est, self.final = "0.2", '"banana"'
        (ans, _), _ = self.run_it(question())
        self.assertEqual(ans, 0.2)

    def test_failed_research_runs_are_dropped_and_all_failing_raises(self):
        self.est, self.final = "0.2", "0.3"
        (ans, _), _ = self.run_it(question(), bad_runs=2)
        self.assertEqual(ans, 0.3)
        with self.assertRaises(RuntimeError):
            self.run_it(question(), bad_runs=3)

    def test_numeric_end_to_end_gives_valid_cdf(self):
        import json
        self.est = self.final = json.dumps(RES_PCTS)
        (ans, _), _ = self.run_it(question("numeric"))
        check_cdf(self, bot.payload(question("numeric"), ans)["continuous_cdf"], 200, False, True)


class Comment(unittest.TestCase):
    def test_trim(self):
        self.assertEqual(bot.trim_comment("short"), "short")
        out = bot.trim_comment("x" * 50_000)
        self.assertLessEqual(len(out), bot.MAX_COMMENT)


class Robustness(unittest.TestCase):
    def test_malformed_estimates_rejected(self):
        for qt, raw in [("binary", None), ("binary", "high"), ("binary", float("nan")), ("binary", True),
                        ("multiple_choice", {"Red": 0, "Green": 0, "Blue": 0}), ("multiple_choice", [1, 2, 3]),
                        ("numeric", {"1": 1}), ("numeric", None)]:
            with self.assertRaises(ValueError, msg=(qt, raw)):
                bot.parse_estimate(question(qt), raw)

    def test_numbers_written_as_text_are_accepted(self):
        mc = bot.parse_estimate(question("multiple_choice"), {"Red": "0.62", "Green": "0.30", "Blue": "0.08"})
        self.assertAlmostEqual(mc["Red"], 0.62, places=2)
        self.assertAlmostEqual(bot.parse_estimate(question("binary"), "70%"), 0.70)
        self.assertAlmostEqual(bot.parse_estimate(question("binary"), " 0.25 "), 0.25)
        raw = {str(pc): f"{1000 * (i + 1):,}" for i, pc in enumerate(bot.PERCENTILES)}
        self.assertEqual(bot.parse_estimate(question("numeric"), raw)[50], 7000.0)

    def test_unsorted_percentiles_are_sorted(self):
        raw = {str(p): v for p, v in zip(bot.PERCENTILES, reversed(range(13)))}
        est = bot.parse_estimate(question("numeric"), raw)
        self.assertEqual(list(est.values()), sorted(est.values()))

    def test_cdf_rules_hold_for_odd_inputs(self):
        for t, lo_open, up_open, zp, m, vals in itertools.product(
                ("numeric", "discrete"), (True, False), (True, False), (None, -10.0), (200, 3),
                ([50.0] * 13, [-500.0] * 13, [900.0] * 13, [float(i) for i in range(13)])):
            if t == "numeric" and m != 200 or t == "discrete" and (zp is not None or m == 200):
                continue
            q = question(t, open_lower_bound=lo_open, open_upper_bound=up_open)
            q["scaling"].update(zero_point=zp, inbound_outcome_count=m)
            if zp is not None:
                vals = [max(v, 0.0) for v in vals]
            cdf = bot.percentiles_to_cdf(q, dict(zip(bot.PERCENTILES, sorted(vals))))
            steps = [b - a for a, b in zip(cdf, cdf[1:])]
            self.assertEqual(len(cdf), m + 1)
            self.assertGreaterEqual(min(steps), 0.01 / m - 1e-12)
            self.assertLessEqual(max(steps), 0.2 * 200 / m + 1e-12)
            self.assertTrue(cdf[0] >= 0.001 - 1e-12 if lo_open else abs(cdf[0]) < 1e-12)
            self.assertTrue(cdf[-1] <= 0.999 + 1e-12 if up_open else abs(cdf[-1] - 1) < 1e-12)


class Scheduling(unittest.TestCase):
    def test_interleave_takes_turns_between_tournaments_up_to_the_limit(self):
        self.assertEqual(bot.interleave([["a1", "a2", "a3"], ["b1"]], 3), ["a1", "b1", "a2"])

    def test_interleave_without_a_limit_returns_everything(self):
        self.assertEqual(bot.interleave([["a1"], [], ["c1", "c2"]], None), ["a1", "c1", "c2"])

    def test_pending_puts_the_question_that_closes_first_first(self):
        late = question(id=1, scheduled_close_time="2026-12-31T00:00:00Z")
        soon = question(id=2, scheduled_close_time="2026-11-13T02:00:00Z")
        unknown = question(id=3, scheduled_close_time=None)
        got = bot.pending([post(late, 1), post(unknown, 3), post(soon, 2)])
        self.assertEqual([p for p, _ in got], [2, 1, 3])

    def test_retry_returns_once_a_flaky_call_succeeds_and_gives_up_after_the_last_attempt(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("boom")
            return "ok"

        self.assertEqual(bot.retry(flaky, attempts=3, wait=0), "ok")
        calls.clear()
        with self.assertRaises(RuntimeError):
            bot.retry(flaky, attempts=2, wait=0)


class Listing(unittest.TestCase):
    def test_listing_asks_for_the_callers_own_forecasts(self):
        # Without with_cp the list endpoint returns my_forecasts: null, and every question gets forecast again each run.
        seen = []
        real = bot.api
        bot.api = lambda method, path, token, body=None, params=None: seen.append((method, path, params)) or {"results": []}
        try:
            list(bot.pages("some-tournament", "tok"))
        finally:
            bot.api = real
        method, path, params = seen[0]
        self.assertEqual((method, path), ("GET", "/posts/"))
        self.assertEqual(params["with_cp"], "true")
        self.assertEqual((params["tournaments"], params["statuses"]), (["some-tournament"], "open"))


if __name__ == "__main__":
    unittest.main()
