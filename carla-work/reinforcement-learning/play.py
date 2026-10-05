"""Drive a trained DQN model with its greedy action and print its Q-values, after the
play script of part 5 of the pythonprogramming.net tutorial.

Run from carla-work, with the server rendering (scripts/carla-server --offscreen or --window):
    scripts/carla-python reinforcement-learning/play.py MODEL [--episodes N] [--record]

MODEL is a .pt file that train.py saved, or a run folder, which plays its final.pt.
"""

import argparse
import datetime
import os
import sys
import time

import numpy as np

from car_env import ACTIONS, CarEnv, add_env_args, env_config, wine_path
from dqn_agent import DQNAgent
from runlog import RunLog

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("model", help="a .pt file, or a run folder (plays its final.pt)")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--every", type=float, default=0.5, help="simulated seconds between lines")
    parser.add_argument("--seed", type=int, default=1, help="seed for the spawn points")
    parser.add_argument("--record", action="store_true",
                        help="write each episode to runs/ as a run file for scripts/carla-replay")
    add_env_args(parser)
    return parser.parse_args()


def run_path(episode):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.normpath(os.path.join(RUNS, f"rl-play-{stamp}-ep{episode}.jsonl.gz"))


def play_episode(args, env, agent, episode):
    state = env.reset()
    log = None
    if args.record:
        log = RunLog(run_path(episode), env.client, env.world, ego=env.vehicle, argv=sys.argv,
                     scenario="rl-play", settings={"model": os.path.basename(args.model),
                                                   "seed": args.seed, "episode": episode})
        env.on_tick = log.tick
        print(f"recording to {log.path}")
    print(f"{'sim_s':>6} {'km/h':>6} {'q_left':>8} {'q_str':>8} {'q_right':>8}  {'action':<8} {'reward':>7} {'fps':>5}")
    steps, reward_sum, next_print = 0, 0.0, 0.0
    wall_start = time.perf_counter()
    reason = "error"
    try:
        while True:
            wall = time.perf_counter()
            qs = agent.q_values(state)
            action = int(np.argmax(qs))
            state, reward, terminated, truncated, info = env.step(action)
            fps = 1.0 / max(time.perf_counter() - wall, 1e-6)
            steps += 1
            reward_sum += reward
            if info["sim_s"] + 1e-9 >= next_print or terminated or truncated:
                print(f"{info['sim_s']:6.2f} {info['kmh']:6.1f} {qs[0]:8.2f} {qs[1]:8.2f} {qs[2]:8.2f}  "
                      f"{ACTIONS[action]:<8} {reward_sum:7.0f} {fps:5.1f}")
                next_print += args.every
            if terminated:
                event = env.collisions[0]
                print(f"{info['sim_s']:6.2f} EVENT collision: {event.other_actor.type_id}")
                if log:
                    log.event("collision", event.timestamp, other_id=event.other_actor.id,
                              other_type=event.other_actor.type_id)
                reason = "collision"
                break
            if truncated:
                reason = "time"
                break
    except KeyboardInterrupt:
        reason = "interrupted"
        raise
    finally:
        wall = time.perf_counter() - wall_start
        env.on_tick = None
        if log:
            log.close(reason, wall)
    print(f"episode {episode}  steps {steps}  reward {reward_sum:.0f}  sim {info['sim_s']:.1f} s  "
          f"wall {wall:.1f} s  {reason}")


def main():
    args = parse_args()
    path = wine_path(args.model)
    path = os.path.join(path, "final.pt") if os.path.isdir(path) else path
    agent = DQNAgent.load(path)
    print(f"model {path}  {agent.kind} {agent.width}x{agent.height}  trained episodes {agent.meta.get('episode', '?')}")
    with CarEnv(env_config(args, agent.width, agent.height, args.seed)) as env:
        try:
            for episode in range(1, args.episodes + 1):
                play_episode(args, env, agent, episode)
        except KeyboardInterrupt:
            print("interrupted")
            return 130
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        # The carla module raises RuntimeError for timeouts and refused spawns.
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
