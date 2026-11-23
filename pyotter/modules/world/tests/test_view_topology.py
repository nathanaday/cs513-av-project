import unittest

from pyotter import World
from pyotter.core import RoadGraphError, WorldHazardLibrary, WorldRoadGraph

try:
    import matplotlib
    matplotlib.use("Agg")
except ImportError:
    matplotlib = None


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class ViewTopology(unittest.TestCase):
    def test_draws_every_segment_in_meters(self):
        graph = WorldRoadGraph.from_template("town10")
        axes = World.view_topology(graph).axes[0]
        drawn = [line for line in axes.lines if len(line.get_xdata()) > 0]
        self.assertEqual(len(drawn), len(graph.segments))
        self.assertEqual(len(axes.patches), len(graph.junctions))
        self.assertEqual(axes.get_xlabel(), "x (m)")
        self.assertTrue(axes.yaxis_inverted())
        self.assertEqual(_labels(axes), [f"junction {j.id}" for j in graph.get_junctions()])

    def test_labels_are_off_by_default_and_cover_every_segment_when_on(self):
        graph = WorldRoadGraph.from_template("town10")
        axes = World.view_topology(graph, label_segments=True, show_junctions=False).axes[0]
        self.assertEqual(len(axes.patches), 0)
        self.assertEqual(sorted(_labels(axes)), sorted(graph.segments))


@unittest.skipIf(matplotlib is None, "matplotlib is not installed")
class ViewHazards(unittest.TestCase):
    def setUp(self):
        self.graph = WorldRoadGraph.from_template("town10")
        self.hazards = WorldHazardLibrary()

    def test_needs_assigned_hazards_from_the_library(self):
        with self.assertRaises(RoadGraphError):
            World.view_hazards(self.graph, self.hazards)
        self.graph.get_segment("r296.s0.l-1").assign_hazard_probability([("meteor", 0.1)])
        with self.assertRaises(RoadGraphError):
            World.view_hazards(self.graph, self.hazards)

    def test_draws_one_map_per_assigned_hazard_in_library_order(self):
        for segment in self.graph.segments_in_junction(189):
            segment.assign_hazard_probability([(self.hazards.pedestrian, 0.03)])
        self.graph.get_segment("r20.s0.l-1").assign_hazard_probability([(self.hazards.wet_road, 0.6)])
        figure = World.view_hazards(self.graph, self.hazards)
        maps = [axes for axes in figure.axes if axes.get_xlabel() == "x (m)"]
        self.assertEqual([axes.get_title(loc="left") for axes in maps], ["pedestrian", "wet_road"])
        for axes in maps:
            self.assertEqual(len(axes.lines), len(self.graph.segments))
            self.assertTrue(axes.yaxis_inverted())
        scales = [axes.get_xlabel() for axes in figure.axes if axes.get_xlabel() != "x (m)"]
        self.assertEqual(scales, ["chance per second that one starts", "chance that it holds for the run"])


def _labels(axes):
    return [text.get_text() for text in axes.texts if text.get_text()]


if __name__ == "__main__":
    unittest.main()
