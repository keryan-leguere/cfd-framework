"""Control-surface deflections."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.synth.autopilot import AutopilotSpec, deflections

TIME = np.linspace(0.0, 60.0, 600)


def _angles(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    phase = TIME / TIME[-1]
    alpha = 6.0 * np.exp(-2.0 * phase) * np.cos(5.0 * TIME) + rng.normal(0, 0.2, TIME.size)
    beta = 4.0 * np.exp(-2.0 * phase) * np.sin(4.0 * TIME) + rng.normal(0, 0.2, TIME.size)
    return alpha, beta


class TestDeflections:
    def test_every_channel_stays_within_the_mechanical_stops(self):
        alpha, beta = _angles()
        spec = AutopilotSpec()

        out = deflections(TIME, alpha, beta, spec=spec)

        for values in out.values():
            assert np.all(np.abs(values) <= spec.limit_deg + 1e-9)

    def test_pitch_opposes_incidence(self):
        alpha, beta = _angles()

        out = deflections(TIME, alpha, beta)

        assert np.corrcoef(out["dm"], alpha)[0, 1] < -0.5

    def test_yaw_opposes_sideslip(self):
        alpha, beta = _angles()

        out = deflections(TIME, alpha, beta)

        assert np.corrcoef(out["dn"], beta)[0, 1] < -0.5

    def test_roll_follows_its_own_slow_programme(self):
        alpha, beta = _angles()

        out = deflections(TIME, alpha, beta)

        assert np.std(out["dl"]) > 0.0
        assert abs(np.corrcoef(out["dl"], alpha)[0, 1]) < 0.5

    def test_the_roll_phase_shifts_the_programme(self):
        alpha, beta = _angles()

        first = deflections(TIME, alpha, beta, roll_phase=0.0)
        second = deflections(TIME, alpha, beta, roll_phase=1.5)

        assert not np.allclose(first["dl"], second["dl"])

    def test_the_rate_limit_is_respected(self):
        spec = AutopilotSpec(rate_limit_deg_s=5.0)
        alpha = 15.0 * np.sign(np.sin(20.0 * TIME))
        beta = np.zeros_like(TIME)

        out = deflections(TIME, alpha, beta, spec=spec)

        step = spec.rate_limit_deg_s * float(np.diff(TIME)[0])
        assert np.all(np.abs(np.diff(out["dm"])) <= step + 1e-9)

    def test_a_trimmed_flight_needs_no_pitch_or_yaw_deflection(self):
        zeros = np.zeros_like(TIME)

        out = deflections(TIME, zeros, zeros)

        assert np.allclose(out["dm"], 0.0)
        assert np.allclose(out["dn"], 0.0)

    def test_nan_angles_do_not_leak_into_the_deflections(self):
        alpha, beta = _angles()
        alpha[10:20] = np.nan

        out = deflections(TIME, alpha, beta)

        assert np.all(np.isfinite(out["dm"]))

    def test_the_same_inputs_give_the_same_deflections(self):
        alpha, beta = _angles()

        assert np.array_equal(
            deflections(TIME, alpha, beta)["dm"], deflections(TIME, alpha, beta)["dm"]
        )

    @pytest.mark.parametrize("field", ["limit_deg", "rate_limit_deg_s"])
    def test_non_positive_limits_are_refused(self, field):
        with pytest.raises(ValueError, match=field):
            AutopilotSpec(**{field: 0.0})
