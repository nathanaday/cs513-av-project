"""A DQN agent in PyTorch, after part 4 of the pythonprogramming.net tutorial: a main
network, a target network, and experience replay. See docs/reinforcement-learning.md."""

import collections
import dataclasses
import random
from typing import Optional

import numpy as np
import torch
from torch import nn

MODELS = ("cnn", "xception")
DEFAULT_SIZE = {"cnn": (160, 120), "xception": (640, 480)}


@dataclasses.dataclass
class DQNConfig:
    """The tutorial's values are the defaults."""
    replay_memory_size: int = 5_000
    min_replay_memory_size: int = 1_000
    minibatch_size: int = 16
    training_batch_size: int = 4
    update_target_every: int = 5
    discount: float = 0.99
    learning_rate: float = 0.001


class SmallCNN(nn.Module):
    """Three convolutions and two dense layers, the size the tutorial's author suggests
    in place of Xception."""

    def __init__(self, width, height, actions=3):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 5, stride=2), nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2), nn.ReLU(),
            nn.Conv2d(64, 64, 3, stride=2), nn.ReLU(),
            nn.Flatten())
        with torch.no_grad():
            flat = self.features(torch.zeros(1, 3, height, width)).shape[1]
        self.head = nn.Sequential(nn.Linear(flat, 256), nn.ReLU(), nn.Linear(256, actions))

    def forward(self, x):
        return self.head(self.features(x))


def build(model, width, height, actions=3):
    if model == "cnn":
        return SmallCNN(width, height, actions)
    if model == "xception":
        import timm
        # Untrained, with global average pooling and a linear head, as in the tutorial.
        return timm.create_model("legacy_xception", pretrained=False, num_classes=actions)
    raise ValueError(f"unknown model {model!r}; choose from {', '.join(MODELS)}")


def to_tensor(frames):
    """H x W x 3 uint8 frames to an N x 3 x H x W float tensor in [0, 1]."""
    batch = torch.from_numpy(np.stack(frames))
    return batch.permute(0, 3, 1, 2).float().div_(255.0)


class DQNAgent:
    def __init__(self, model="cnn", width=None, height=None, config: Optional[DQNConfig] = None,
                 seed: Optional[int] = None):
        self.kind = model
        self.width, self.height = (width, height) if width and height else DEFAULT_SIZE[model]
        self.config = config or DQNConfig()
        self.rng = random.Random(seed)
        if seed is not None:
            torch.manual_seed(seed)
        self.model = build(model, self.width, self.height)
        self.target_model = build(model, self.width, self.height)
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.learning_rate)
        self.loss_fn = nn.MSELoss()
        self.replay_memory = collections.deque(maxlen=self.config.replay_memory_size)
        self.target_update_counter = 0

    def q_values(self, state):
        self.model.eval()
        with torch.no_grad():
            return self.model(to_tensor([state]))[0].numpy()

    def act(self, state, epsilon):
        """Epsilon-greedy: a random action with probability epsilon, else the best one.
        Returns the action and the Q-values, or None for a random action."""
        if self.rng.random() < epsilon:
            return self.rng.randrange(3), None
        qs = self.q_values(state)
        return int(np.argmax(qs)), qs

    def update_replay_memory(self, transition):
        """transition = (state, action, reward, new_state, terminated)"""
        self.replay_memory.append(transition)

    def train(self):
        """Fit the main network on one minibatch from replay memory. Returns the mean
        loss, or None while the memory is smaller than min_replay_memory_size."""
        c = self.config
        if len(self.replay_memory) < c.min_replay_memory_size:
            return None
        minibatch = self.rng.sample(self.replay_memory, c.minibatch_size)
        states = to_tensor([t[0] for t in minibatch])
        new_states = to_tensor([t[3] for t in minibatch])
        actions = torch.tensor([t[1] for t in minibatch])
        rewards = torch.tensor([t[2] for t in minibatch], dtype=torch.float32)
        terminated = torch.tensor([t[4] for t in minibatch], dtype=torch.float32)

        # Targets for the whole minibatch come first, as in the tutorial; a truncated
        # episode still bootstraps from the next state, only a collision ends the return.
        self.model.eval()
        with torch.no_grad():
            targets = self.model(states)
            future = self.target_model(new_states).max(dim=1).values
            targets[torch.arange(len(minibatch)), actions] = rewards + c.discount * future * (1.0 - terminated)

        self.model.train()
        losses = []
        for start in range(0, len(minibatch), c.training_batch_size):
            part = slice(start, start + c.training_batch_size)
            loss = self.loss_fn(self.model(states[part]), targets[part])
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            losses.append(loss.item())
        return float(np.mean(losses))

    def end_episode(self):
        """Copy the main network to the target network every update_target_every episodes."""
        self.target_update_counter += 1
        if self.target_update_counter >= self.config.update_target_every:
            self.target_model.load_state_dict(self.model.state_dict())
            self.target_update_counter = 0

    def save(self, path, **meta):
        torch.save({"model": self.kind, "width": self.width, "height": self.height,
                    "state_dict": self.model.state_dict(), "meta": meta}, path)

    @classmethod
    def load(cls, path):
        saved = torch.load(path, map_location="cpu", weights_only=True)
        agent = cls(saved["model"], saved["width"], saved["height"])
        agent.model.load_state_dict(saved["state_dict"])
        agent.target_model.load_state_dict(saved["state_dict"])
        agent.meta = saved.get("meta", {})
        return agent
