"""Tests for graph path generation (src/ulv/outputs/html/paths.py).

The frontend recomputes these paths client-side (asv.js:graph_to_path,
mirrored by sanitize_filename at asv.js:236-247), so `graph_path` must
stay byte-compatible with asv's Python side. Every expected value below
was computed by executing the verbatim logic of asv/util.py:1084-1126
(sanitize_filename) and asv/graph.py:110-131 (Graph.get_file_path) from
the vendored checkout at commit 7032df701a969fa61f4c819ce9f71fb2e66f5a62.
"""

import pytest

from ulv.outputs.html.paths import graph_path, sanitize_filename


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("CON", "CON_"),
            ("con", "con_"),
            ("COM1", "COM1_"),
            # asv's character class escapes the caret, so '^' is replaced
            # while a backslash passes through unchanged.
            ("a\\b", "a\\b"),
            ("a^b", "a_b"),
            ("a:b", "a_b"),
            ("time_units.time_unit_parse", "time_units.time_unit_parse"),
        ],
    )
    def test_matches_asv_sanitize_filename(self, raw, expected):
        assert sanitize_filename(raw) == expected


class TestGraphPath:
    @pytest.mark.parametrize(
        ("params", "benchmark", "expected"),
        [
            (
                {"summary": ""},
                "time_units.time_unit_parse",
                "graphs/summary/time_units.time_unit_parse",
            ),
            (
                {
                    "arch": "x86_64",
                    "branch": "master",
                    "cpu": "Intel(R) Core(TM) i5-2520M CPU @ 2.50GHz (4 cores)",
                    "machine": "cheetah",
                    "numpy": "1.8",
                    "os": "Linux (Fedora 20)",
                    "python": "2.7",
                    "ram": "8.2G",
                },
                "params_examples.mem_param",
                "graphs/arch-x86_64/branch-master"
                "/cpu-Intel(R) Core(TM) i5-2520M CPU @ 2.50GHz (4 cores)"
                "/machine-cheetah/numpy-1.8/os-Linux (Fedora 20)"
                "/python-2.7/ram-8.2G/params_examples.mem_param",
            ),
            (
                {"machine": "box", "opts": None},
                "bench",
                "graphs/machine-box/opts-null/bench",
            ),
            (
                {"weird": 'a/b\\c<d>e:f"g|h?i*j^k'},
                "bench",
                "graphs/weird-a_b\\c_d_e_f_g_h_i_j_k/bench",
            ),
            (
                {"name": "CON", "aux": "AUX"},
                "NUL",
                "graphs/aux-AUX/name-CON/NUL_",
            ),
            ({"empty": ""}, "b", "graphs/empty/b"),
        ],
    )
    def test_matches_asv_get_file_path(self, params, benchmark, expected):
        assert graph_path(params, benchmark) == expected

    def test_parts_sorted_lexicographically_regardless_of_input_order(self):
        forward = graph_path({"a": "1", "b": "2"}, "x")
        backward = graph_path({"b": "2", "a": "1"}, "x")
        assert forward == backward == "graphs/a-1/b-2/x"
