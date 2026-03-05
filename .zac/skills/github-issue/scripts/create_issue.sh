#!/bin/bash
# Create a GitHub issue using the gh CLI

usage() {
    echo "Usage: $0 <title> <description> [--repo <owner/repo>] [--label <label>]"
    echo ""
    echo "Arguments:"
    echo "  title         Issue title"
    echo "  description   Issue body/description"
    echo "  --repo        Repository (default: robtandy/zac)"
    echo "  --label       Label to add (can be specified multiple times)"
    exit 1
}

if [ $# -lt 2 ]; then
    usage
fi

TITLE="$1"
DESCRIPTION="$2"
shift 2

REPO="robtandy/zac"
LABELS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --repo)
            REPO="$2"
            shift 2
            ;;
        --label)
            if [ -n "$LABELS" ]; then
                LABELS="$LABELS,$2"
            else
                LABELS="$2"
            fi
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Build the gh command
CMD="gh issue create --title \"$TITLE\" --body \"$DESCRIPTION\" --repo $REPO"

if [ -n "$LABELS" ]; then
    CMD="$CMD --label $LABELS"
fi

# Execute the command
eval $CMD