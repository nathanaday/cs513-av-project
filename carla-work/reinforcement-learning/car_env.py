"""A CARLA driving environment for reinforcement learning, after part 3 of the
pythonprogramming.net tutorial, in synchronous mode.

    with CarEnv(EnvConfig(seed=0)) as env:
        observation = env.reset()
        observation, reward, terminated, truncated, info = env.step(1)

The server must render (scripts/carla-server --offscreen or --window): the observation is
a camera frame, and a camera crashes the no-rendering server. See docs/reinforcement-learning.md.
"""

import dataclasses
import queue
import random
import sys
from typing import Optional

import carla
import numpy as np

DELTA = 0.05
SETTLE_SECONDS = 1.0
FRAME_TIMEOUT = 30.0
CAMERA_AT = carla.Location(x=2.5, z=0.7)
FOLLOW_BACK, FOLLOW_UP, FOLLOW_PITCH = 8.0, 3.0, -12.0
ACTIONS = ("left", "straight", "right")


@dataclasses.dataclass
class EnvConfig:
    """The tutorial's values are the defaults, except that time is simulated seconds."""
    host: str = "localhost"
    port: int = 2000
    timeout: float = 60.0
    width: int = 640
    height: int = 480
    fov: float = 110.0
    steer_amt: float = 1.0
    seconds_per_episode: float = 10.0
    ticks_per_step: int = 1
    min_kmh: float = 50.0
    collision_reward: float = -200.0
    slow_reward: float = -1.0
    fast_reward: float = 1.0
    follow: bool = True
    seed: Optional[int] = None


def wine_path(path):
    """Wine maps the macOS file system to drive Z:; a bare /Users/... would land on C:."""
    if sys.platform == "win32" and path.startswith("/"):
        return "Z:" + path.replace("/", "\\")
    return path


def add_env_args(parser):
    """Add the EnvConfig options to an argparse parser."""
    d = EnvConfig()
    group = parser.add_argument_group("environment")
    group.add_argument("--host", default=d.host)
    group.add_argument("--port", type=int, default=d.port)
    group.add_argument("--timeout", type=float, default=d.timeout, help="client timeout in seconds")
    group.add_argument("--seconds-per-episode", type=float, default=d.seconds_per_episode,
                       help="simulated seconds before an episode is truncated")
    group.add_argument("--ticks-per-step", type=int, default=d.ticks_per_step,
                       help="ticks of 0.05 s that one action lasts")
    group.add_argument("--steer-amt", type=float, default=d.steer_amt, help="steer of the left and right actions")
    group.add_argument("--min-kmh", type=float, default=d.min_kmh, help="speed below which a step earns the slow reward")
    group.add_argument("--collision-reward", type=float, default=d.collision_reward)
    group.add_argument("--slow-reward", type=float, default=d.slow_reward)
    group.add_argument("--fast-reward", type=float, default=d.fast_reward)
    group.add_argument("--no-follow", action="store_true",
                       help="leave the spectator free; by default it follows behind the car")
    return group


def env_config(args, width, height, seed):
    return EnvConfig(host=args.host, port=args.port, timeout=args.timeout, width=width, height=height,
                     steer_amt=args.steer_amt, seconds_per_episode=args.seconds_per_episode,
                     ticks_per_step=args.ticks_per_step, min_kmh=args.min_kmh,
                     collision_reward=args.collision_reward, slow_reward=args.slow_reward,
                     fast_reward=args.fast_reward, follow=not args.no_follow, seed=seed)


class CarEnv:
    """One Tesla Model 3 with a front camera and a collision sensor.

    Actions: 0 steers left, 1 drives straight, 2 steers right, each at full throttle.
    The observation is the camera frame as an H x W x 3 RGB uint8 array.
    on_tick, when set, is called with the world snapshot after every tick.
    """

    def __init__(self, config: EnvConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.client = carla.Client(config.host, config.port)
        self.client.set_timeout(config.timeout)
        self.world = self.client.get_world()
        client_version, server_version = self.client.get_client_version(), self.client.get_server_version()
        if client_version != server_version:
            print(f"warning: client {client_version} != server {server_version}", file=sys.stderr)

        library = self.world.get_blueprint_library()
        self.vehicle_bp = library.find("vehicle.tesla.model3")
        self.vehicle_bp.set_attribute("role_name", "hero")
        self.camera_bp = library.find("sensor.camera.rgb")
        self.camera_bp.set_attribute("image_size_x", str(config.width))
        self.camera_bp.set_attribute("image_size_y", str(config.height))
        self.camera_bp.set_attribute("fov", str(config.fov))
        self.collision_bp = library.find("sensor.other.collision")
        self.spectator = self.world.get_spectator() if config.follow else None

        self.actors = []
        self.vehicle = None
        self.frames = queue.Queue()
        self.collisions = []
        self.frame = None
        self.start_s = 0.0
        self.sim_s = 0.0
        self.on_tick = None

        # Last, so that no step of __init__ can fail with the world left in synchronous mode.
        self.original = self.world.get_settings()
        settings = self.world.get_settings()
        if settings.no_rendering_mode:
            raise RuntimeError("the world does not render; a camera needs scripts/carla-server --offscreen or --window")
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = DELTA
        self.world.apply_settings(settings)

    def reset(self):
        """Start an episode at a random free spawn point and return the first frame."""
        self._destroy()
        spawns = self.world.get_map().get_spawn_points()
        self.rng.shuffle(spawns)
        for transform in spawns:
            self.vehicle = self.world.try_spawn_actor(self.vehicle_bp, transform)
            if self.vehicle is not None:
                break
        else:
            raise RuntimeError("every spawn point is occupied")
        self.actors.append(self.vehicle)

        self.frames = queue.Queue()
        camera = self.world.spawn_actor(self.camera_bp, carla.Transform(CAMERA_AT), attach_to=self.vehicle)
        self.actors.append(camera)
        camera.listen(self.frames.put)

        # The car drops onto the road at spawn. The tutorial slept 4 s of wall time;
        # here it stands braked for a simulated second, before the collision sensor exists.
        self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
        for _ in range(round(SETTLE_SECONDS / DELTA)):
            self._tick()

        self.collisions = []
        collision = self.world.spawn_actor(self.collision_bp, carla.Transform(), attach_to=self.vehicle)
        self.actors.append(collision)
        collision.listen(self.collisions.append)

        self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=0.0))
        frame = self._tick()
        self.start_s = self.sim_s
        return self.frame_at(frame)

    def step(self, action):
        steer = (-self.config.steer_amt, 0.0, self.config.steer_amt)[action]
        self.vehicle.apply_control(carla.VehicleControl(throttle=1.0, steer=steer))
        for _ in range(self.config.ticks_per_step):
            frame = self._tick()
        observation = self.frame_at(frame)

        kmh = 3.6 * self.vehicle.get_velocity().length()
        collided = bool(self.collisions)
        if collided:
            reward = self.config.collision_reward
        elif kmh < self.config.min_kmh:
            reward = self.config.slow_reward
        else:
            reward = self.config.fast_reward
        elapsed = self.sim_s - self.start_s
        truncated = not collided and elapsed + 1e-9 >= self.config.seconds_per_episode
        info = {"kmh": kmh, "sim_s": elapsed, "frame": frame,
                "collision": self.collisions[0].other_actor.type_id if collided else None}
        return observation, reward, collided, truncated, info

    def frame_at(self, frame):
        """The camera image of a world frame, as RGB. Older images in the queue are dropped."""
        while True:
            try:
                image = self.frames.get(timeout=FRAME_TIMEOUT)
            except queue.Empty:
                raise RuntimeError(f"no camera image for frame {frame} after {FRAME_TIMEOUT:.0f} s") from None
            if image.frame >= frame:
                break
        bgra = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)
        self.frame = np.ascontiguousarray(bgra[:, :, 2::-1])
        return self.frame

    def close(self):
        """Destroy the episode's actors and restore the world settings."""
        try:
            self._destroy()
        finally:
            self.world.apply_settings(self.original)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _tick(self):
        frame = self.world.tick()
        snapshot = self.world.get_snapshot()
        self.sim_s = snapshot.timestamp.elapsed_seconds
        if self.on_tick:
            self.on_tick(snapshot)
        if self.spectator and self.vehicle:
            transform = self.vehicle.get_transform()
            forward, location = transform.get_forward_vector(), transform.location
            self.spectator.set_transform(carla.Transform(
                carla.Location(x=location.x - FOLLOW_BACK * forward.x, y=location.y - FOLLOW_BACK * forward.y,
                               z=location.z + FOLLOW_UP),
                carla.Rotation(pitch=FOLLOW_PITCH, yaw=transform.rotation.yaw)))
        return frame

    def _destroy(self):
        for actor in self.actors:
            if actor.type_id.startswith("sensor."):
                actor.stop()
        if self.actors:
            self.client.apply_batch_sync([carla.command.DestroyActor(a) for a in self.actors])
        self.actors = []
        self.vehicle = None
