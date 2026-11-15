# Source snapshots

Files below this directory are immutable, append-only snapshots of external
inputs. A new acquisition must use a new dated directory and its own manifest;
never replace a prior file in place.

Before using a snapshot, verify its SHA-256 against the adjacent manifest. Raw
files preserve source values and are not production-ready model inputs.
