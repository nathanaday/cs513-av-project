import unittest

from pyotter import World
from pyotter.core import WorldRoadGraph

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
        self.assertEqual(axes.get_xlabel(), "x (m)")
        self.assertTrue(axes.yaxis_inverted())
        self.assertEqual(_labels(axes), [])

    def test_labels_are_off_by_default_and_cover_every_segment_when_on(self):
        graph = WorldRoadGraph.from_template("town10")
        axes = World.view_topology(graph, label_segments=True).axes[0]
        self.assertEqual(sorted(_labels(axes)), sorted(graph.segments))


def _labels(axes):
    return [text.get_text() for text in axes.texts if text.get_text()]


if __name__ == "__main__":
    unittest.main()
