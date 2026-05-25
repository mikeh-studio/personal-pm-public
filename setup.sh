#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_DIR=${PERSONAL_PM_DATA_DIR:-"$ROOT_DIR/private"}

case "$TARGET_DIR" in
  /*) ;;
  *) TARGET_DIR="$ROOT_DIR/$TARGET_DIR" ;;
esac

mkdir -p "$TARGET_DIR"
cp -R -n "$ROOT_DIR/templates/." "$TARGET_DIR/"

TODAY_FILE="$TARGET_DIR/tasks/today.md"
if [ -f "$TODAY_FILE" ] && grep -q '{{YYYY-MM-DD}}' "$TODAY_FILE"; then
  TODAY=$(date +%Y-%m-%d)
  TMP_FILE=$(mktemp "${TODAY_FILE}.XXXXXX")
  sed "s/{{YYYY-MM-DD}}/$TODAY/g" "$TODAY_FILE" > "$TMP_FILE"
  mv "$TMP_FILE" "$TODAY_FILE"
fi

printf 'Personal PM workspace initialized at %s\n' "$TARGET_DIR"
printf 'Existing files were left unchanged.\n'
