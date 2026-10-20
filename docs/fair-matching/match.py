import argparse
import itertools
import json
import random
import sys
from pathlib import Path

DEFAULT_PREFERENCES = Path(__file__).with_name("preferences.json")


def load(path):
    try:
        data = json.loads(Path(path).read_text())
        teams = data["teams"]
        preferences = data["preferences"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        sys.exit(f"{path}: cannot read teams and preferences ({error})")

    problems = []
    for team, size in teams.items():
        if not isinstance(size, int) or size < 1:
            problems.append(f"team '{team}' must have a size of 1 or more")
    places = sum(size for size in teams.values() if isinstance(size, int))
    if places != len(preferences):
        problems.append(f"the teams have {places} places, but there are {len(preferences)} members")
    for person, ranking in preferences.items():
        if not isinstance(ranking, list) or sorted(ranking) != sorted(teams):
            problems.append(f"{person} must rank each team once: {', '.join(teams)}")
    if problems:
        sys.exit(f"{path}:\n  " + "\n  ".join(problems))
    return teams, preferences


def assignments(teams, people):
    slots = [team for team, size in teams.items() for _ in range(size)]
    for order in sorted(set(itertools.permutations(slots))):
        yield dict(zip(people, order))


def ranks(assignment, preferences):
    return {person: preferences[person].index(team) + 1 for person, team in assignment.items()}


def score(assignment, preferences, teams):
    values = ranks(assignment, preferences).values()
    return list(values).count(len(teams)), sum(values)


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def describe(assignment, preferences, teams):
    person_ranks = ranks(assignment, preferences)
    width = max(map(len, teams))
    lines = []
    for team in teams:
        members = [f"{p} ({ordinal(person_ranks[p])})" for p, r in assignment.items() if r == team]
        lines.append(f"  {team:<{width}}  {', '.join(members)}")
    last, total = score(assignment, preferences, teams)
    lines.append(f"  Last choices: {last}   Total rank: {total}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Assign members to teams: fewest last choices first, then lowest total rank, then a random pick among ties."
    )
    parser.add_argument("preferences", nargs="?", default=DEFAULT_PREFERENCES, help="JSON file with teams and rankings")
    parser.add_argument("--seed", type=int, help="seed for the random pick among tied assignments")
    args = parser.parse_args()

    teams, preferences = load(args.preferences)
    candidates = list(assignments(teams, list(preferences)))
    best = min(score(a, preferences, teams) for a in candidates)
    tied = [a for a in candidates if score(a, preferences, teams) == best]

    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    chosen = random.Random(seed).choice(tied)

    print(f"Checked {len(candidates)} possible assignments.\n")
    print("Chosen assignment:")
    print(describe(chosen, preferences, teams))

    if len(tied) == 1:
        print("\nNo ties: this is the only best assignment.")
        return
    print(f"\nPicked at random from {len(tied)} tied assignments with seed {seed}.")
    print(f"Run again with --seed {seed} to get the same pick.\n")
    print("All tied assignments:")
    for number, assignment in enumerate(tied, 1):
        print(f"\n{number}.")
        print(describe(assignment, preferences, teams))


if __name__ == "__main__":
    main()
