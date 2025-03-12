#!/bin/bash

if [ -z "$1" ]; then
    echo "Error: Directory path is required."
    echo "Usage: $0 <directory_path>"
    exit 1
fi

DIR="$1"
if [ ! -d "$DIR" ]; then
    echo "Error: Directory '$DIR' does not exist."
    exit 1
fi

for file in "$DIR"/*.csv; do
    if [ -f "$file" ]; then
        python main.py load_terms "$file" --batch-size 1000
    fi
done
