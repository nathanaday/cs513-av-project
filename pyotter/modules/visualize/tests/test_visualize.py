import unittest

from pyotter import Planner, Visualize, World
from pyotter.core import RoadGraphError, WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.driver import NO_GAP_M, DriverModel, DrivingScenarioTelemetry, Signal
from pyotter.modules.planner import PlanningError

try:
    import matplotlib
    matplotlib.use("Agg")
except ImportError:
    matplotlib = None


def forecast_world():
    hazards = WorldHazardLibrary()
    graph = WorldRoadGraph.from_template("town10")
    for segment in graph.segments_in_junction(189):
        segment.assign_hazard_probability([(hazards.pedestrian, 0.05)])
    graph.set_condition(hazards.wet_road, probability=0.9, severity="high", variability=0.1)
    graph.set_condition(hazards.low_visibility, probability=0.5, severity="mid", variability=0.4)
    graph.set_time_of_day(17.5)
    return hazards, graph


def steady_run(name, samples=40):
    """An uneventful drive at 8 m/s with no other road user in sight."""
    record = DrivingScenarioTelemetry(name, "g", "Town10HD_Opt", 1, "naive", 0.0, DriverModel(), 0.05, outcome="arrived")
    for tick in range(samples):
        sample = {signal.value: 0.0 for signal in Signal}
        sample.update(time_s=tick * 0.05, speed_mps=8.0, speed_limit_mps=8.33, target_speed_mps=8.0,
                      allowed_speed_mps=8.0, progress_m=tick * 0.4, gap_m=NO_GAP_M, detection_range_m=60.0)
        record.add_sample(**sample)
    return record


def maps(figure):
    return [axes for axes in figure.axes if axes.get_xlabel() == "x (m)"]


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class Topology(unittest.TestCase):
    def test_draws_every_segment_in_meters(self):
        graph = WorldRoadGraph.from_template("town10")
        axes = Visualize.topology(graph).axes[0]
        drawn = [line for line in axes.lines if len(line.get_xdata()) > 0]
        self.assertEqual(len(drawn), len(graph.segments))
        self.assertEqual(len(axes.patches), len(graph.junctions))
        self.assertEqual(axes.get_xlabel(), "x (m)")
        self.assertTrue(axes.yaxis_inverted())
        self.assertEqual(_labels(axes), [f"junction {j.id}" for j in graph.get_junctions()])

    def test_labels_are_off_by_default_and_cover_every_segment_when_on(self):
        graph = WorldRoadGraph.from_template("town10")
        axes = Visualize.topology(graph, label_segments=True, show_junctions=False).axes[0]
        self.assertEqual(len(axes.patches), 0)
        self.assertEqual(sorted(_labels(axes)), sorted(graph.segments))


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class Hazards(unittest.TestCase):
    def setUp(self):
        self.graph = WorldRoadGraph.from_template("town10")
        self.hazards = WorldHazardLibrary()

    def test_needs_a_forecast_from_the_library(self):
        with self.assertRaises(RoadGraphError):
            Visualize.hazards(self.graph, self.hazards)
        self.graph.get_segment("r296.s0.l-1").assign_hazard_probability([("meteor", 0.1)])
        with self.assertRaises(RoadGraphError):
            Visualize.hazards(self.graph, self.hazards)

    def test_draws_one_map_per_hazard_in_library_order(self):
        for segment in self.graph.segments_in_junction(189):
            segment.assign_hazard_probability([(self.hazards.pedestrian, 0.03)])
        self.graph.set_condition(self.hazards.wet_road, probability=0.9, severity="high")
        figure = Visualize.hazards(self.graph, self.hazards)
        self.assertEqual([axes.get_title(loc="left") for axes in maps(figure)], ["pedestrian", "wet_road"])
        for axes in maps(figure):
            self.assertEqual(len(axes.lines), len(self.graph.segments))
            self.assertTrue(axes.yaxis_inverted())
        scales = [axes.get_xlabel() for axes in figure.axes if axes.get_xlabel() != "x (m)"]
        self.assertEqual(scales, ["chance per second that one starts", "expected severity (chance x severity)"])

    def test_time_of_day_alone_brings_up_the_visibility_map(self):
        self.graph.set_time_of_day(17.5)
        figure = Visualize.hazards(self.graph, self.hazards)
        self.assertEqual([axes.get_title(loc="left") for axes in maps(figure)], ["low_visibility"])


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class Spawns(unittest.TestCase):
    def test_draws_one_dot_per_event_and_rejects_spawns_from_another_world(self):
        hazards, graph = forecast_world()
        spawns = World.roll_hazards(graph, hazards, 1221, duration_s=120.0)
        figure = Visualize.spawns(graph, hazards, spawns)
        self.assertEqual([axes.get_title(loc="left") for axes in maps(figure)],
                         ["pedestrian", "low_visibility", "wet_road"])
        self.assertEqual(len(maps(figure)[0].collections[0].get_offsets()), len(spawns.events))
        graph.set_condition(hazards.wet_road, probability=0.2, severity="low")
        with self.assertRaises(RoadGraphError):
            Visualize.spawns(graph, hazards, spawns)


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class Routes(unittest.TestCase):
    def test_draws_one_map_per_route(self):
        _, graph = forecast_world()
        a, b = graph.spawn_points[18], graph.spawn_points[127]
        routes = [Planner.route(a, b, graph, mode=mode, risk_scale=2) for mode in ("naive", "cautious", "risk-aware")]
        figure = Visualize.routes(graph, routes)
        self.assertEqual([axes.get_title(loc="left") for axes in maps(figure)],
                         ["naive", "cautious", "risk-aware, risk scale 2"])
        self.assertEqual(len(Visualize.routes(graph, routes[0]).axes), 3)
        other_map = WorldRoadGraph("tiny", "synthetic", "none", "0.9.16", "hand-built", {})
        with self.assertRaises(PlanningError):
            Visualize.routes(other_map, routes)
        with self.assertRaises(PlanningError):
            Visualize.routes(graph, [])


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class Telemetry(unittest.TestCase):
    def test_draws_one_line_per_run_and_the_first_run_limits(self):
        figure = Visualize.telemetry([steady_run("first"), steady_run("second")])
        speed_axes, gap_axes, force_axes = figure.axes
        self.assertEqual([line.get_label() for line in speed_axes.lines], ["first", "second", "speed limit"])
        self.assertEqual(force_axes.get_xlabel(), "simulation time (s)")
        self.assertEqual(len(Visualize.telemetry(steady_run("alone")).axes), 3)

    def test_refuses_no_runs_and_a_run_with_no_samples(self):
        with self.assertRaises(ValueError):
            Visualize.telemetry([])
        with self.assertRaises(ValueError):
            Visualize.telemetry(steady_run("empty", samples=0))


def _labels(axes):
    return [text.get_text() for text in axes.texts if text.get_text()]


if __name__ == "__main__":
    unittest.main()
