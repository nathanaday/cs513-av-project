# Example: create a world using the world module
from pathlib import Path

from pyotter import World
from pyotter.core import WorldHazardLibrary, WorldRoadGraph

OUTPUT = Path(__file__).parent / "runs"


def main():
    hazards = WorldHazardLibrary()

    wrg = WorldRoadGraph.from_template("town10")

    # view the road graph with dimensions (meters)
    # the result is a matplotlib Figure: save it, or call matplotlib.pyplot.show() to open a window
    OUTPUT.mkdir(exist_ok=True)
    figure = World.view_topology(wrg)
    figure.savefig(OUTPUT / "town10-topology.png", dpi=150)

    # API (getters)
    segments = wrg.get_segments()  # returns all navigable road segments
    print(f"{wrg.map_name}: {len(segments)} segments, {len(wrg.spawn_points)} spawn points")

    segment = wrg.get_segment("r296.s0.l-1")  # returns the particular segment by id
    print(f"{segment.id}: {segment.length_m:.1f} m, limit {segment.speed_limit_kmh:g} km/h, "
          f"leads to {', '.join(segment.successors)}")

    # assign hazard probabilities by segment: one value per hazard, and assigning again replaces it
    segment.assign_hazard_probability([
        (hazards.pedestrian, 0.03),  # event: chance per second that one starts
        (hazards.wet_road, 0.4),     # condition: chance that it holds for the run
    ])

    # save the world road graph from this session
    path = OUTPUT / "town10-world.json.gz"
    wrg.save(path)

    # load a world road graph
    wrg = WorldRoadGraph.load(path)
    for item in wrg.get_segment("r296.s0.l-1").hazard_probabilities:
        print(f"  {item.hazard_id} ({hazards.get(item.hazard_id).kind.value}): {item.probability}")


if __name__ == "__main__":
    main()
