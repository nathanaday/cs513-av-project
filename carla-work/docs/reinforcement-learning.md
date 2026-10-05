# Reinforcement learning tutorial

This folder holds a working copy of the CARLA reinforcement learning tutorial on pythonprogramming.net, parts 3 to 5:

- [Part 3, the environment](https://pythonprogramming.net/reinforcement-learning-environment-self-driving-autonomous-cars-carla-python/)
- [Part 4, the DQN agent](https://pythonprogramming.net/reinforcement-learning-agent-self-driving-autonomous-cars-carla-python/)
- [Part 5, training and play](https://pythonprogramming.net/reinforcement-learning-self-driving-autonomous-cars-carla-python/)

A deep Q-network (DQN) learns to steer a Tesla Model 3 from its front camera. At each step it picks one of three actions at full throttle: steer left, drive straight, or steer right. A collision gives -200 and ends the episode. Each other step gives -1 below 50 km/h and +1 at 50 km/h or more.

The code keeps the tutorial's method and its settings. It changes what does not run on the team's Macs (see [Differences from the tutorial](#differences-from-the-tutorial)).

**What it does not do:** drive well. The tutorial trains for 100 episodes, and its author reports that the car does not learn to drive in that time. The author estimates that a competent driver needs on the order of 100,000 episodes. This code is a pipeline to experiment with, not a trained driver.

Run every command from the `carla-work` folder.

## Server mode

The agent sees the world through a camera. A camera crashes the default no-rendering server (see [headless-carla.md](headless-carla.md)). Start the server with rendering:

```bash
scripts/carla-server --offscreen      # no window
scripts/carla-server --window         # watch the car; the spectator follows it
```

Both modes need about 15 GB of memory for the server, so a 16 GB Mac cannot run them. Do not run `train.py` or `play.py` against the default server: the camera crashes it. The scripts stop with an error when the world's no-rendering setting is on, but they cannot detect a server that runs with `-nullrhi`.

## Install

Install the CARLA client first ([headless-carla.md](headless-carla.md)). Then install PyTorch and the other pinned packages into the wrapper's Python:

```bash
scripts/carla-python -m pip install -r reinforcement-learning/requirements-rl.txt
```

The download is about 200 MB, and the install uses about 1.2 GB. It installs PyTorch 2.5.1 for the CPU, torchvision, and timm (for the optional Xception network). It does not change the packages of `requirements-carla.txt`.

Check the install:

```bash
scripts/carla-python -c "import torch, numpy; print(torch.__version__, numpy.__version__)"
```

The output must be `2.5.1+cpu 1.26.4`.

## Train

With the server up:

```bash
scripts/carla-python reinforcement-learning/train.py
```

```
run Z:\Users\...\carla-work\reinforcement-learning\models\cnn-20261004-192715
model cnn 160x120  episodes 3  seed 0
episode steps  reward epsilon     loss  sim_s wall_s  end
      1    68    -229   1.000        -    3.4    1.7  collision static.building
      2   138    -157   0.950        -    6.9    3.1  collision traffic.traffic_light
      3    60    -235   0.902        -    3.0    2.2  collision static.vegetation
saved Z:\Users\...\carla-work\reinforcement-learning\models\cnn-20261004-192715\final.pt
```

`train.py` prints one line per episode:

| Column | Meaning |
|---|---|
| `steps` | Actions in the episode. One action lasts one tick of 0.05 s, or `--ticks-per-step` ticks. |
| `reward` | The sum of the episode's rewards. |
| `epsilon` | The probability of a random action in this episode. |
| `loss` | The mean training loss of the episode. `-` until the replay memory holds `--min-replay-memory-size` transitions (1000, about 5 episodes). |
| `sim_s`, `wall_s` | Simulated and wall seconds of the episode. |
| `end` | `time` when the episode reached `--seconds-per-episode`, or `collision` and the type of the other actor. |

Each run writes a folder `reinforcement-learning/models/<model>-<local time>/`. Git ignores it. The folder holds:

- `stats.csv`: one row per episode, with the columns above, the count of each action, and the average, minimum, and maximum reward of the last 10 episodes.
- `<model>__<max>max_<avg>avg_<min>min__ep<N>.pt`: a model saved every 10 episodes when the minimum reward of those episodes is `--min-reward` (-200) or more. These are the tutorial's rule and file name.
- `final.pt`: the model at the end of the run, or when you press Ctrl+C.

Options:

| Option | Default | Effect |
|---|---|---|
| `--episodes N` | 100 | Episodes to train. |
| `--model cnn\|xception` | `cnn` | The network (see [Differences](#differences-from-the-tutorial)). |
| `--width`, `--height` | 160×120 for `cnn`, 640×480 for `xception` | Camera image size, which is also the network input. |
| `--seed N` | 0 | Seed for the spawn points, the random actions, the minibatches, and the network weights. |
| `--seconds-per-episode S` | 10 | Simulated seconds before an episode ends. |
| `--ticks-per-step N` | 1 | Ticks that one action lasts. |
| `--min-replay-memory-size N` | 1000 | Transitions before training starts. Lower it for a short test run. |
| `--epsilon`, `--epsilon-decay`, `--min-epsilon` | 1.0, 0.95, 0.001 | Exploration at the start, the factor after each episode, and the floor. |
| `--no-follow` | off | Leave the spectator free. By default it follows behind the car. |

`train.py --help` lists the other options: the reward values, the replay memory, the minibatch, the target network update, the discount, and the learning rate.

The same seed gives the same spawn points and the same random actions. The physics can still drift between runs (see [scenarios.md](scenarios.md)), so two runs with one seed are close but not equal.

## Play

Drive a trained model with its best action:

```bash
scripts/carla-python reinforcement-learning/play.py reinforcement-learning/models/cnn-20261004-181500
```

The argument is a `.pt` file, or a run folder, which plays its `final.pt`.

```
model reinforcement-learning/models/cnn-20261004-192547\final.pt  cnn 160x120  trained episodes 3
recording to Z:\Users\...\carla-work\runs\rl-play-20261005-022651-ep1.jsonl.gz
 sim_s   km/h   q_left    q_str  q_right  action    reward   fps
  0.05    0.0     0.12    -0.22    -0.26  left          -1  11.5
  0.50    4.0     0.12    -0.22    -0.26  left         -10  76.9
  1.00   16.7     0.13    -0.26    -0.27  left         -20  76.9
...
 10.00   31.9     0.18    -0.21    -0.28  left        -200  47.6
episode 1  steps 200  reward -200  sim 10.0 s  wall 3.3 s  time
```

This model trained for 3 episodes. It picks `left` at every step and drives in a circle. The tutorial's author saw the same thing: an agent with little training prefers one action.

Each line shows the Q-value of each action, the action the model picked, the sum of rewards so far, and the steps per wall second (`fps`) of the prediction and the tick.

Options:

| Option | Default | Effect |
|---|---|---|
| `--episodes N` | 1 | Episodes to drive. |
| `--every S` | 0.5 | Simulated seconds between lines. |
| `--seed N` | 1 | Seed for the spawn points. |
| `--record` | off | Write each episode to `runs/rl-play-<UTC time>-ep<N>.jsonl.gz`. Open it with `scripts/carla-replay` ([replay.md](replay.md)). |

## Speed

Measured on 2026-10-04 on a MacBook Pro M4 Pro, 48 GB, with the server in `--window` mode at `epic` quality, the default `cnn` network at 160×120, and seed 0:

| | Value |
|---|---|
| 100 episodes, the tutorial's run | 13.9 minutes wall time, 346 simulated seconds |
| Simulated seconds per wall second, before training starts | about 2.5 |
| Simulated seconds per wall second, during training | 0.4 to 0.5 |
| One training minibatch on the CPU | about 150 ms |

Training starts after about 15 episodes. Random steering crashes the car within 2 to 5 simulated seconds, so the replay memory needs that many episodes to hold 1000 transitions.

In this run every episode ended in a collision. The minimum reward of each group of 10 episodes stayed below -200, so the run saved only `final.pt`. The tutorial's author trained the same 100 episodes in 17 minutes on a Titan RTX GPU.

`--model xception` at 640×480 takes about 21 s per training minibatch. At that speed, 100 episodes would take about 40 hours.

## Differences from the tutorial

| Tutorial | Here | Why |
|---|---|---|
| TensorFlow 1 Keras (`tf.get_default_graph`, `Adam(lr=)`) | PyTorch 2.5.1 for the CPU | The tutorial's code does not run on current TensorFlow. PyTorch runs in the wrapper's Windows Python, where the `carla` client must run. |
| Wall-clock time: `time.sleep(4)` after spawn, 10 wall seconds per episode | Synchronous mode with a 0.05 s tick: 1 simulated second braked after spawn, 10 simulated seconds per episode | Episodes repeat with a seed, and the training time does not change what the car does. The repository's other runners also use synchronous mode. |
| A training thread beside the driving loop | One training minibatch after each step, in the driving loop | The thread kept the frame rate up in asynchronous mode. In synchronous mode the world waits for the client. |
| Untrained Xception at 640×480 | A three-layer CNN at 160×120 by default; `--model xception` keeps Xception | The tutorial's author reports that Xception is too large and that a 2 to 3 layer CNN does better. On the CPU, one Xception training step at 640×480 takes about 21 s. |
| `done` ends the Q-value target on a collision and on a timeout | Only a collision ends the target; a timeout still uses the next state | The timeout is not a state of the world, so the car's future rewards do not stop there. |
| `step` returns `(observation, reward, done, None)` | `step` returns `(observation, reward, terminated, truncated, info)` | The current Gym API, which separates a collision from a timeout. |
| Camera image in BGR | Camera image in RGB | The order that image libraries expect. |
| TensorBoard through `ModifiedTensorBoard` | `stats.csv` | A CSV file needs no extra package and opens anywhere. |
| An OpenCV preview window | The server window (`--window`), and `play.py --record` | The wrapper's Python has no OpenCV, and the replay viewer works with no rendering. |
| A random spawn point; spawn fails if it is taken | The next free spawn point in a seeded random order | A taken spawn point does not stop the run. |

The target network update counts episodes, as in the tutorial, and copies the main network every 5 episodes. The tutorial's code copies it after more than 5, so every 6.

## Files

| File | Purpose |
|---|---|
| `reinforcement-learning/car_env.py` | `CarEnv`: the car, its camera and collision sensor, the actions, and the reward. |
| `reinforcement-learning/dqn_agent.py` | `DQNAgent`: the networks, the replay memory, and the training step. |
| `reinforcement-learning/train.py` | The training loop. |
| `reinforcement-learning/play.py` | Drives a saved model. |
| `reinforcement-learning/requirements-rl.txt` | The pinned PyTorch packages. |
