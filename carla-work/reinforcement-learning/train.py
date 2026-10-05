"""Train the DQN agent to steer from the front camera, after part 5 of the
pythonprogramming.net tutorial.

Run from carla-work, with the server rendering (scripts/carla-server --offscreen or --window):
    scripts/carla-python reinforcement-learning/train.py [--episodes N] [--model cnn|xception]
"""

import argparse
import csv
import datetime
import os
import sys
import time

import numpy as np

from car_env import ACTIONS, CarEnv, add_env_args, env_config
from dqn_agent import DEFAULT_SIZE, MODELS, DQNAgent, DQNConfig

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
FIELDS = ("episode", "steps", "reward", "epsilon", "loss", "sim_s", "wall_s", "end",
          "actions_left", "actions_straight", "actions_right", "avg_reward", "min_reward", "max_reward")


def parse_args():
    d = DQNConfig()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--model", choices=MODELS, default="cnn")
    parser.add_argument("--width", type=int, help="camera width; default 160 for cnn, 640 for xception")
    parser.add_argument("--height", type=int, help="camera height; default 120 for cnn, 480 for xception")
    parser.add_argument("--seed", type=int, default=0, help="seed for spawn points, exploration, and the networks")
    parser.add_argument("--out", default=MODELS_DIR, help="folder for the run folder with stats.csv and models")
    group = parser.add_argument_group("agent")
    group.add_argument("--epsilon", type=float, default=1.0, help="exploration rate at the start")
    group.add_argument("--epsilon-decay", type=float, default=0.95, help="factor on epsilon after each episode")
    group.add_argument("--min-epsilon", type=float, default=0.001)
    group.add_argument("--aggregate-stats-every", type=int, default=10, help="episodes in the rolling statistics")
    group.add_argument("--min-reward", type=float, default=-200.0,
                       help="save a model when the rolling minimum reward reaches this")
    group.add_argument("--replay-memory-size", type=int, default=d.replay_memory_size)
    group.add_argument("--min-replay-memory-size", type=int, default=d.min_replay_memory_size,
                       help="transitions in memory before training starts")
    group.add_argument("--minibatch-size", type=int, default=d.minibatch_size)
    group.add_argument("--training-batch-size", type=int, default=d.training_batch_size)
    group.add_argument("--update-target-every", type=int, default=d.update_target_every, help="episodes")
    group.add_argument("--discount", type=float, default=d.discount)
    group.add_argument("--learning-rate", type=float, default=d.learning_rate)
    add_env_args(parser)
    return parser.parse_args()


def run_episode(env, agent, epsilon):
    state = env.reset()
    reward_sum, losses, counts = 0.0, [], [0, 0, 0]
    while True:
        action, _ = agent.act(state, epsilon)
        counts[action] += 1
        new_state, reward, terminated, truncated, info = env.step(action)
        reward_sum += reward
        agent.update_replay_memory((state, action, reward, new_state, terminated))
        loss = agent.train()
        if loss is not None:
            losses.append(loss)
        state = new_state
        if terminated or truncated:
            end = f"collision {info['collision']}" if terminated else "time"
            return {"steps": sum(counts), "reward": reward_sum, "sim_s": info["sim_s"], "end": end,
                    "loss": float(np.mean(losses)) if losses else None, "actions": counts}


def main():
    args = parse_args()
    width, height = DEFAULT_SIZE[args.model]
    width, height = args.width or width, args.height or height
    config = DQNConfig(replay_memory_size=args.replay_memory_size,
                       min_replay_memory_size=args.min_replay_memory_size, minibatch_size=args.minibatch_size,
                       training_batch_size=args.training_batch_size, update_target_every=args.update_target_every,
                       discount=args.discount, learning_rate=args.learning_rate)
    run_dir = os.path.join(args.out, f"{args.model}-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(run_dir, exist_ok=True)
    agent = DQNAgent(args.model, width, height, config, seed=args.seed)
    epsilon = args.epsilon
    rewards = []
    status = 0
    print(f"run {run_dir}")
    print(f"model {args.model} {width}x{height}  episodes {args.episodes}  seed {args.seed}")
    print(f"{'episode':>7} {'steps':>5} {'reward':>7} {'epsilon':>7} {'loss':>8} {'sim_s':>6} {'wall_s':>6}  end")

    with open(os.path.join(run_dir, "stats.csv"), "w", newline="") as stats_file, \
            CarEnv(env_config(args, width, height, args.seed)) as env:
        stats = csv.DictWriter(stats_file, FIELDS)
        stats.writeheader()
        try:
            for episode in range(1, args.episodes + 1):
                wall = time.monotonic()
                result = run_episode(env, agent, epsilon)
                wall = time.monotonic() - wall
                agent.end_episode()
                rewards.append(result["reward"])
                recent = rewards[-args.aggregate_stats_every:]
                avg, low, high = float(np.mean(recent)), min(recent), max(recent)
                loss = "-" if result["loss"] is None else f"{result['loss']:.3f}"
                print(f"{episode:7d} {result['steps']:5d} {result['reward']:7.0f} {epsilon:7.3f} {loss:>8} "
                      f"{result['sim_s']:6.1f} {wall:6.1f}  {result['end']}")
                stats.writerow({"episode": episode, "steps": result["steps"], "reward": result["reward"],
                                "epsilon": round(epsilon, 5),
                                "loss": None if result["loss"] is None else round(result["loss"], 4),
                                "sim_s": round(result["sim_s"], 2), "wall_s": round(wall, 2), "end": result["end"],
                                **{f"actions_{name}": n for name, n in zip(ACTIONS, result["actions"])},
                                "avg_reward": round(avg, 2), "min_reward": low, "max_reward": high})
                stats_file.flush()

                if episode % args.aggregate_stats_every == 0 and low >= args.min_reward:
                    name = f"{args.model}__{high:_>7.2f}max_{avg:_>7.2f}avg_{low:_>7.2f}min__ep{episode}.pt"
                    agent.save(os.path.join(run_dir, name), episode=episode, avg_reward=avg)
                    print(f"saved {name}")
                epsilon = max(args.min_epsilon, epsilon * args.epsilon_decay)
        except KeyboardInterrupt:
            print("interrupted")
            status = 130
        finally:
            final = os.path.join(run_dir, "final.pt")
            agent.save(final, episode=len(rewards), argv=sys.argv[1:])
            print(f"saved {final}")
    return status


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        # The carla module raises RuntimeError for timeouts and refused spawns.
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
