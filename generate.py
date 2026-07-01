#!/usr/bin/env python3
"""
generate.py — Neural Pulse Contribution Graph

Fetches a GitHub user's contribution calendar via the GraphQL API and renders
it as an animated SVG styled like a neural network forward-pass: each day is
a "neuron" sized/colored by commit intensity, and a signal pulse sweeps left
to right across the weeks, lighting up synapse lines between active days.

Usage:
    GITHUB_TOKEN=xxx python generate.py --user divyadharshini-1306 --palette dark --out dist/neural-dark.svg
    GITHUB_TOKEN=xxx python generate.py --user divyadharshini-1306 --palette light --out dist/neural-light.svg

Requires: requests  (pip install requests)
"""

import argparse
import datetime
import os
import sys
import requests

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

# Color palettes: background, neuron base color, neuron hot color, synapse color, text color
PALETTES = {
    "dark": {
        "bg": "#0D0D1A",
        "neuron_off": "#1B1B2E",
        "neuron_low": "#4C1D95",
        "neuron_mid": "#7C3AED",
        "neuron_high": "#A78BFA",
        "neuron_peak": "#E9D5FF",
        "synapse": "#7C3AED",
        "text": "#C4B5FD",
    },
    "light": {
        "bg": "#FFFFFF",
        "neuron_off": "#EDE9FE",
        "neuron_low": "#C4B5FD",
        "neuron_mid": "#A78BFA",
        "neuron_high": "#7C3AED",
        "neuron_peak": "#4C1D95",
        "synapse": "#7C3AED",
        "text": "#4C1D95",
    },
}


def fetch_contributions(user: str, token: str):
    """Fetch the contribution calendar for a user. Falls back to synthetic
    demo data if no token is provided, so the script is testable offline."""
    if not token:
        return _demo_weeks()

    headers = {"Authorization": f"bearer {token}"}
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": QUERY, "variables": {"login": user}},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")

    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return weeks


def _demo_weeks():
    """Synthetic 53-week grid for local testing without a token."""
    import random
    random.seed(42)
    weeks = []
    start = datetime.date.today() - datetime.timedelta(weeks=52)
    cursor = start
    for w in range(53):
        days = []
        for d in range(7):
            # bias toward weekday activity, sparser on weekends
            base = random.random()
            if d in (0, 6):
                count = int(base * 3)
            else:
                count = int(base * base * 12)
            days.append({"date": str(cursor), "contributionCount": count})
            cursor += datetime.timedelta(days=1)
        weeks.append({"contributionDays": days})
    return weeks


def bucket_color(count: int, palette: dict) -> str:
    if count == 0:
        return palette["neuron_off"]
    if count <= 2:
        return palette["neuron_low"]
    if count <= 5:
        return palette["neuron_mid"]
    if count <= 9:
        return palette["neuron_high"]
    return palette["neuron_peak"]


def neuron_radius(count: int) -> float:
    # base radius 2.4, scaling up with activity, capped
    return min(2.4 + count * 0.5, 6.0)


def build_svg(weeks, palette_name: str, username: str) -> str:
    palette = PALETTES[palette_name]
    cell = 14          # spacing between neuron centers
    margin_left = 30
    margin_top = 20
    margin_bottom = 24
    num_weeks = len(weeks)

    width = margin_left + num_weeks * cell + 20
    height = margin_top + 7 * cell + margin_bottom

    svg_parts = []
    svg_parts.append(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )

    # Defs: glow filter + gradient for synapses
    svg_parts.append(f"""
    <defs>
      <filter id="glow-{palette_name}" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="2.2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <linearGradient id="synapse-grad-{palette_name}" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="{palette['synapse']}" stop-opacity="0" />
        <stop offset="50%" stop-color="{palette['synapse']}" stop-opacity="0.9" />
        <stop offset="100%" stop-color="{palette['synapse']}" stop-opacity="0" />
      </linearGradient>
    </defs>
    """)

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="{palette["bg"]}" rx="6" />')

    # Precompute neuron centers + activity for synapse + pulse logic
    centers = []  # centers[week_idx][day_idx] = (x, y, count)
    for wi, week in enumerate(weeks):
        col = []
        cx = margin_left + wi * cell
        for di, day in enumerate(week["contributionDays"]):
            cy = margin_top + di * cell
            count = day.get("contributionCount", 0)
            col.append((cx, cy, count))
        centers.append(col)

    # Synapse lines: connect active neurons to active neurons in the next column
    style_lines = []
    synapse_id = 0
    for wi in range(num_weeks - 1):
        for di, (x1, y1, c1) in enumerate(centers[wi]):
            if c1 == 0:
                continue
            for dj, (x2, y2, c2) in enumerate(centers[wi + 1]):
                if c2 == 0:
                    continue
                if abs(di - dj) > 1:
                    continue  # only connect nearby rows, keeps it readable
                synapse_id += 1
                delay = round(wi * 0.09, 2)
                svg_parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="url(#synapse-grad-{palette_name})" stroke-width="0.8" '
                    f'class="synapse" style="animation-delay:{delay}s" />'
                )

    # Neurons
    for wi, col in enumerate(centers):
        delay = round(wi * 0.09, 2)
        for (cx, cy, count) in col:
            color = bucket_color(count, palette)
            r = neuron_radius(count)
            pulse_class = "neuron active" if count > 0 else "neuron"
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" '
                f'class="{pulse_class}" filter="url(#glow-{palette_name})" '
                f'style="animation-delay:{delay}s" />'
            )

    # Sweeping pulse bar (signal moving left to right)
    sweep_width = 18
    svg_parts.append(
        f'<rect x="{margin_left - sweep_width}" y="{margin_top - 6}" '
        f'width="{sweep_width}" height="{7 * cell + 12}" '
        f'fill="{palette["neuron_peak"]}" opacity="0.12" class="sweep" />'
    )

    # Label
    svg_parts.append(
        f'<text x="{margin_left}" y="{height - 6}" font-family="JetBrains Mono, monospace" '
        f'font-size="9" fill="{palette["text"]}" opacity="0.7">'
        f'{username} · neural pulse · forward pass</text>'
    )

    total_duration = round(num_weeks * 0.09 + 1.6, 2)
    sweep_distance = num_weeks * cell + 40

    svg_parts.append(f"""
    <style>
      .neuron {{
        opacity: 0.35;
        transform-box: fill-box;
        transform-origin: center;
      }}
      .neuron.active {{
        animation: pulse {total_duration}s ease-in-out infinite;
      }}
      .synapse {{
        opacity: 0;
        animation: flow {total_duration}s ease-in-out infinite;
      }}
      .sweep {{
        animation: sweep {total_duration}s linear infinite;
      }}
      @keyframes pulse {{
        0%   {{ opacity: 0.35; transform: scale(1); }}
        8%   {{ opacity: 1;    transform: scale(1.6); }}
        20%  {{ opacity: 0.55; transform: scale(1); }}
        100% {{ opacity: 0.35; transform: scale(1); }}
      }}
      @keyframes flow {{
        0%   {{ opacity: 0; }}
        6%   {{ opacity: 0.9; }}
        16%  {{ opacity: 0; }}
        100% {{ opacity: 0; }}
      }}
      @keyframes sweep {{
        0%   {{ transform: translateX(0); }}
        100% {{ transform: translateX({sweep_distance}px); }}
      }}
    </style>
    """)

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def main():
    parser = argparse.ArgumentParser(description="Generate neural-pulse contribution SVG")
    parser.add_argument("--user", required=True, help="GitHub username")
    parser.add_argument("--palette", choices=["dark", "light"], default="dark")
    parser.add_argument("--out", required=True, help="Output SVG path")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    weeks = fetch_contributions(args.user, token)
    svg = build_svg(weeks, args.palette, args.user)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(svg)

    print(f"Wrote {args.out} ({len(weeks)} weeks, palette={args.palette})")


if __name__ == "__main__":
    main()
