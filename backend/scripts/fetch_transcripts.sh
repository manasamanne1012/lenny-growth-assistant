#!/usr/bin/env bash
# Clone (or refresh) the transcript corpus.
#
# A shallow clone of a public repo, kept out of version control. The app never
# needs the git history, so --depth 1 keeps this to seconds rather than minutes.
set -euo pipefail

REPO="https://github.com/ChatPRD/lennys-podcast-transcripts.git"
DEST="${TRANSCRIPTS_DIR:-./data/lennys-podcast-transcripts}"

if [ -d "$DEST/.git" ]; then
  echo "Refreshing $DEST ..."
  git -C "$DEST" pull --ff-only
else
  echo "Cloning transcripts into $DEST ..."
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 "$REPO" "$DEST"
fi

COUNT=$(find "$DEST" -name '*.md' -not -name 'README*' | wc -l | tr -d ' ')
echo "Done. $COUNT transcript files available."
echo "Next: make ingest   (or: make ingest LIMIT=25 for a fast first run)"
