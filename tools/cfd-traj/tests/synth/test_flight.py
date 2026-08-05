"""The synthetic flight model.

These assert *qualitative* properties only -- monotonicities, uniqueness of the
apogee, orders of magnitude, reproducibility. The model represents no real
vehicle, so pinning numeric values would only lock in arbitrary choices.
"""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.synth.flight import Guidance, Vehicle, drag_coefficient, integrate


class TestMassAndThrust:
    def test_mass_falls_during_the_burn_then_holds(self):
        vehicle = Vehicle()
        traj = integrate(vehicle=vehicle, dt=0.01, dt_out=0.1)

        burning = traj.time_s < vehicle.burn_time_s
        coasting = traj.time_s > vehicle.burn_time_s + 1.0
        assert np.all(np.diff(traj.mass_kg[burning]) < 0.0)
        assert np.allclose(traj.mass_kg[coasting], traj.mass_kg[coasting][0], rtol=1e-9)

    def test_mass_never_falls_below_the_empty_mass(self):
        vehicle = Vehicle()
        traj = integrate(vehicle=vehicle, dt=0.01, dt_out=0.1)

        assert float(traj.mass_kg.min()) >= vehicle.mass_empty_kg - 1e-6

    def test_the_propellant_is_fully_burned(self):
        vehicle = Vehicle()
        traj = integrate(vehicle=vehicle, dt=0.01, dt_out=0.1)

        assert float(traj.mass_kg[-1]) == pytest.approx(vehicle.mass_empty_kg, rel=1e-3)


class TestTrajectoryShape:
    def test_the_mach_number_rises_during_the_burn_then_falls(self):
        vehicle = Vehicle()
        traj = integrate(vehicle=vehicle, dt=0.01, dt_out=0.1)

        peak = int(np.argmax(traj.mach))
        assert traj.time_s[peak] == pytest.approx(vehicle.burn_time_s, abs=1.0)
        assert traj.mach[peak] > traj.mach[0]
        assert traj.mach[-1] < traj.mach[peak]

    def test_the_flight_climbs_all_the_way_to_its_end(self):
        traj = integrate(dt=0.01, dt_out=0.1)

        assert traj.apogee_m == pytest.approx(float(traj.altitude_m[-1]), rel=1e-3)
        assert traj.apogee_m > traj.altitude_m[0]

    def test_the_apogee_is_reached_once(self):
        traj = integrate(dt=0.01, dt_out=0.1)

        assert int(np.argmax(traj.altitude_m)) == traj.n_rows - 1

    def test_the_flight_stays_supersonic_at_burnout(self):
        traj = integrate(dt=0.01, dt_out=0.1)

        assert traj.mach_max > 1.5

    def test_everything_stays_finite(self):
        traj = integrate(dt=0.01, dt_out=0.1)

        for values in (traj.mach, traj.altitude_m, traj.alpha_deg, traj.beta_deg, traj.speed_ms):
            assert np.all(np.isfinite(values))

    def test_time_is_strictly_increasing_and_evenly_sampled(self):
        traj = integrate(dt=0.01, dt_out=0.2)

        steps = np.diff(traj.time_s)
        assert np.all(steps > 0.0)
        assert np.allclose(steps, 0.2)

    def test_the_gust_driven_sideslip_decays_as_the_vehicle_climbs(self):
        # Sideslip here comes from the gust alone, so it must fade with
        # altitude. Incidence does not: past burnout the autopilot fights
        # gravity turning the vehicle over, and its demand grows towards apogee.
        traj = integrate(dt=0.01, dt_out=0.1)

        low = np.abs(traj.beta_deg[traj.altitude_m < 5_000.0]).mean()
        high = np.abs(traj.beta_deg[traj.altitude_m > 25_000.0]).mean()
        assert high < low

    def test_the_commanded_incidence_stays_within_the_autopilot_authority(self):
        guidance = Guidance()
        traj = integrate(guidance=guidance, dt=0.01, dt_out=0.1)

        # Command limit plus whatever the gust adds on top of it.
        assert np.abs(traj.alpha_deg).max() < guidance.alpha_max_deg + 20.0


class TestNumerics:
    def test_the_integrator_has_converged_at_the_working_step(self):
        coarse = integrate(dt=0.04, dt_out=0.5)
        fine = integrate(dt=0.01, dt_out=0.5)

        assert coarse.apogee_m == pytest.approx(fine.apogee_m, rel=5e-3)

    def test_the_same_settings_give_the_same_trajectory(self):
        first = integrate(dt=0.02, dt_out=0.25)
        second = integrate(dt=0.02, dt_out=0.25)

        assert np.array_equal(first.altitude_m, second.altitude_m)
        assert np.array_equal(first.mach, second.mach)

    def test_a_stronger_motor_flies_higher(self):
        weak = integrate(thrust_scale=0.9, dt=0.02, dt_out=0.25)
        strong = integrate(thrust_scale=1.1, dt=0.02, dt_out=0.25)

        assert strong.apogee_m > weak.apogee_m

    def test_more_drag_flies_lower(self):
        clean = integrate(drag_scale=0.8, dt=0.02, dt_out=0.25)
        dirty = integrate(drag_scale=1.2, dt=0.02, dt_out=0.25)

        assert dirty.apogee_m < clean.apogee_m

    def test_an_unpowered_shot_does_not_blow_up(self):
        traj = integrate(thrust_scale=0.0, dt=0.02, dt_out=0.25, t_max=60.0)

        assert np.all(np.isfinite(traj.altitude_m))
        assert traj.n_rows > 1

    @pytest.mark.parametrize(("dt", "dt_out"), [(0.0, 0.1), (0.1, 0.0), (0.5, 0.1)])
    def test_invalid_time_steps_are_refused(self, dt, dt_out):
        with pytest.raises(ValueError):
            integrate(dt=dt, dt_out=dt_out)


class TestDragLaw:
    def test_the_transonic_peak_sits_just_above_mach_one(self):
        vehicle = Vehicle()
        mach = np.linspace(0.2, 4.0, 400)
        cd = np.array([drag_coefficient(float(m), 0.0, vehicle) for m in mach])

        peak = float(mach[int(np.argmax(cd))])
        assert 1.0 <= peak <= 1.2

    def test_incidence_adds_drag(self):
        vehicle = Vehicle()

        assert drag_coefficient(2.0, 0.1, vehicle) > drag_coefficient(2.0, 0.0, vehicle)

    def test_subsonic_drag_is_below_the_transonic_peak(self):
        vehicle = Vehicle()

        assert drag_coefficient(0.5, 0.0, vehicle) < drag_coefficient(1.1, 0.0, vehicle)


class TestVehicleValidation:
    def test_more_propellant_than_launch_mass_is_refused(self):
        with pytest.raises(ValueError, match="propellant"):
            Vehicle(mass_launch_kg=100.0, mass_propellant_kg=150.0)

    @pytest.mark.parametrize("field", ["mass_launch_kg", "thrust_n", "burn_time_s"])
    def test_non_positive_characteristics_are_refused(self, field):
        with pytest.raises(ValueError, match=field):
            Vehicle(**{field: 0.0})


class TestGuidance:
    def test_the_pitch_programme_runs_from_launch_to_final_elevation(self):
        guidance = Guidance()

        assert np.rad2deg(guidance.gamma_command_rad(0.0)) == pytest.approx(guidance.gamma0_deg)
        assert np.rad2deg(guidance.gamma_command_rad(1e6)) == pytest.approx(guidance.gamma_end_deg)

    def test_the_gust_dies_out_with_altitude(self):
        guidance = Guidance()

        low = np.hypot(*guidance.gust(3.0, 0.0))
        high = np.hypot(*guidance.gust(3.0, 40_000.0))
        assert high < low
