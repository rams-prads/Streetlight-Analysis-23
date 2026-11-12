#!/usr/bin/env bash
# ==============================================================================
# Urban Integrated Municipal ERP — Automatic Version & VersionCode Incrementer
# Updates frontend/urban-console/src/app/core/constants/version.ts and package.json
# Usage: ./scripts/bump_version.sh [patch|minor|major]
# ==============================================================================
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_TS="$REPO_ROOT/frontend/urban-console/src/app/core/constants/version.ts"
PACKAGE_JSON="$REPO_ROOT/frontend/urban-console/package.json"

BUMP_TYPE="${1:-patch}"

if [ ! -f "$VERSION_TS" ]; then
  echo "Error: $VERSION_TS not found"
  exit 1
fi

# Extract current version and versionCode
CURRENT_VER=$(grep -E "version:\s*'" "$VERSION_TS" | sed -E "s/.*version:\s*'([^']+)'.*/\1/")
CURRENT_CODE=$(grep -E "versionCode:\s*[0-9]+" "$VERSION_TS" | sed -E "s/.*versionCode:\s*([0-9]+).*/\1/")

if [ -z "$CURRENT_VER" ] || [ -z "$CURRENT_CODE" ]; then
  echo "Error: Could not parse version or versionCode from $VERSION_TS"
  exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VER"
NEW_CODE=$((CURRENT_CODE + 1))

case "$BUMP_TYPE" in
  major)
    NEW_MAJOR=$((MAJOR + 1))
    NEW_VER="${NEW_MAJOR}.0.0"
    ;;
  minor)
    NEW_MINOR=$((MINOR + 1))
    NEW_VER="${MAJOR}.${NEW_MINOR}.0"
    ;;
  patch|*)
    NEW_PATCH=$((PATCH + 1))
    NEW_VER="${MAJOR}.${MINOR}.${NEW_PATCH}"
    ;;
esac

MONTH_YEAR=$(date +"%B %Y")

# Update version.ts (perl -pi, not sed -i: sed's in-place flag takes a mandatory suffix on
# GNU sed but a separate arg on BSD/macOS sed, so one script can't satisfy both; perl's -pi
# behaves the same everywhere).
perl -pi -e "s/version:\s*'[^']+'/version: '$NEW_VER'/" "$VERSION_TS"
perl -pi -e "s/versionCode:\s*[0-9]+/versionCode: $NEW_CODE/" "$VERSION_TS"
perl -pi -e "s/releaseDate:\s*'[^']+'/releaseDate: '$MONTH_YEAR'/" "$VERSION_TS"

# Update package.json
perl -pi -e "s/\"version\":\s*\"[^\"]+\"/\"version\": \"$NEW_VER\"/" "$PACKAGE_JSON"
perl -pi -e "s/\"versionCode\":\s*[0-9]+/\"versionCode\": $NEW_CODE/" "$PACKAGE_JSON"

echo "✓ Bumped version: $CURRENT_VER -> $NEW_VER"
echo "✓ Bumped versionCode: $CURRENT_CODE -> $NEW_CODE"
echo "✓ Release Date: $MONTH_YEAR"

