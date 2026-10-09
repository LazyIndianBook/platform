#!/usr/bin/env bash
# Builds the production image ghcr.io/lazyindianbook/examleaf-erp:16.50.0-<sha> (UPGRADE.md, README "The image").
#
#   image/build.sh            build locally (the Helm chart runs this tag with installApps from README)
#   PUSH=1 image/build.sh     also push both images (CI on a tag; needs `docker login ghcr.io`)
#
# Two stages:
#   1. frappe_docker v4.0.0's images/layered/Containerfile with apps.json as a BuildKit secret (never a build-arg:
#      build-args stay readable in `docker history`, frappe_docker PR #1861). FRAPPE_BRANCH is both frappe's git ref and
#      the tag of the frappe/base and frappe/build images, so it must exist as both (checked first). CACHE_BUST is the
#      hash of apps.json and of offsite_backups' branch head (the one entry without a tag), because a secret does not
#      take part in Docker's layer cache.
#   2. image/Containerfile copies this repository's examleaf_erp into that base (the layered file only clones from git).
#
# The other form, for when examleaf_erp has its own repository (for example a `git subtree split` mirror): add
#   {"url": "https://<token>@github.com/examleaf/examleaf_erp", "branch": "v1.0.0"}
# to a copy of apps.json made outside the repository, run stage 1 only with it, and add the app's commit to CACHE_BUST.
# APP_GIT_URL and APP_GIT_REF below do exactly that, reading the token from GITHUB_TOKEN; the token never reaches a layer.
set -euo pipefail

FRAPPE_DOCKER_REF=v4.0.0
FRAPPE_BRANCH=v16.50.0
ERP_VERSION=16.50.0
REGISTRY=${REGISTRY:-ghcr.io/lazyindianbook}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)   # examleaf-erp/, the build context of stage 2
WORK="$HERE/.build"            # gitignored

sha() { if command -v sha256sum >/dev/null; then sha256sum | cut -c1-16; else shasum -a 256 | cut -c1-16; fi; }

GIT_SHA=$(git -C "$ROOT" rev-parse --short=12 HEAD)
APP_TREE=$(git -C "$ROOT" rev-parse --short=12 "HEAD:examleaf-erp/apps/examleaf_erp")
if [[ -n "$(git -C "$ROOT" status --porcelain -- apps/examleaf_erp image)" ]]; then
  echo "examleaf-erp/apps or image has uncommitted changes: the tag would not say what is inside. Commit first." >&2
  exit 1
fi

# 1. The base and build images of the framework release must exist (on 9 Oct 2026 v16.50.0 does, v16.51.0 does not).
for repo in base build; do
  if ! curl -fsS "https://hub.docker.com/v2/repositories/frappe/$repo/tags/$FRAPPE_BRANCH" >/dev/null; then
    echo "frappe/$repo:$FRAPPE_BRANCH is not on Docker Hub yet: wait for it, or stay on the previous release." >&2
    exit 1
  fi
done

# 2. frappe_docker at its pinned release
if [[ ! -d "$WORK/frappe_docker" ]]; then
  git clone --quiet --depth 1 --branch "$FRAPPE_DOCKER_REF" https://github.com/frappe/frappe_docker "$WORK/frappe_docker"
fi
[[ "$(git -C "$WORK/frappe_docker" describe --tags)" == "$FRAPPE_DOCKER_REF" ]] || { echo "frappe_docker is not $FRAPPE_DOCKER_REF" >&2; exit 1; }

OFFSITE=$(git ls-remote https://github.com/frappe/offsite_backups refs/heads/version-16 | cut -f1)
APPS_JSON="$HERE/apps.json"
EXTRA=""
if [[ -n "${APP_GIT_URL:-}" ]]; then  # the git form: examleaf_erp from its own repository, one stage
  APPS_JSON=$(mktemp)
  trap 'rm -f "$APPS_JSON"' EXIT
  python3 - "$HERE/apps.json" "$APP_GIT_URL" "${APP_GIT_REF:?set APP_GIT_REF to a tag}" >"$APPS_JSON" <<'PY'
import json, os, sys
apps = json.load(open(sys.argv[1]))
url = sys.argv[2].replace("https://", f"https://{os.environ['GITHUB_TOKEN']}@", 1)
print(json.dumps(apps + [{"url": url, "branch": sys.argv[3]}]))
PY
  EXTRA=$(git ls-remote "$APP_GIT_URL" "refs/tags/$APP_GIT_REF" | cut -f1)
fi
CACHE_BUST=$(printf '%s %s %s' "$(sha <"$HERE/apps.json")" "$OFFSITE" "$EXTRA" | sha)
BASE="$REGISTRY/examleaf-erp-base:$ERP_VERSION-$CACHE_BUST"
TAG="$REGISTRY/examleaf-erp:$ERP_VERSION-$GIT_SHA"

echo "Stage 1: $BASE (offsite_backups version-16 at ${OFFSITE:0:12})"
docker build \
  --build-arg FRAPPE_BRANCH="$FRAPPE_BRANCH" \
  --build-arg CACHE_BUST="$CACHE_BUST" \
  --secret id=apps_json,src="$APPS_JSON" \
  --label org.examleaf.offsite_backups="$OFFSITE" \
  -f "$WORK/frappe_docker/images/layered/Containerfile" \
  -t "$BASE" \
  "$WORK/frappe_docker"

if [[ -n "${APP_GIT_URL:-}" ]]; then
  docker tag "$BASE" "$TAG"
else
  echo "Stage 2: $TAG (examleaf_erp tree ${APP_TREE})"
  docker build \
    --build-arg BASE_IMAGE="$BASE" \
    --build-arg APP_VERSION="$ERP_VERSION-$GIT_SHA" \
    --build-arg GIT_SHA="$GIT_SHA" \
    -f "$HERE/Containerfile" \
    -t "$TAG" \
    "$ROOT"
fi

# the image starts and every app imports
docker run --rm --entrypoint /home/frappe/frappe-bench/env/bin/python "$TAG" -c \
  "import frappe, erpnext, india_compliance, hrms, offsite_backups, examleaf_erp; print('apps import:', examleaf_erp.__version__)"

if [[ "${PUSH:-0}" == "1" ]]; then
  docker push "$BASE"
  docker push "$TAG"
fi
echo "$TAG"
