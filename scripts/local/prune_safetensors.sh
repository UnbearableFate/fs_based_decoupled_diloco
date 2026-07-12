#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: prune_safetensors.sh [--delete] ROOT

Recursively find *.safetensors below ROOT. Keep exactly one file: the file
whose basename is global_v<digits>.safetensors with the largest numeric
version. Delete every other *.safetensors file.

The default is a dry run. Pass --delete to perform the deletions.

If multiple files have the same largest version, the lexicographically largest
full path is kept. The script refuses to delete anything if it cannot find a
matching global_v<digits>.safetensors file.
EOF
}

delete=false
root=""

while (($# > 0)); do
    case "$1" in
        --delete)
            delete=true
            ;;
        --dry-run)
            delete=false
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            if (($# != 1)) || [[ -n "$root" ]]; then
                usage >&2
                exit 2
            fi
            root=$1
            shift
            break
            ;;
        -*)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -n "$root" ]]; then
                printf 'Only one ROOT directory may be specified.\n' >&2
                usage >&2
                exit 2
            fi
            root=$1
            ;;
    esac
    shift
done

if [[ -z "$root" || ! -d "$root" ]]; then
    printf 'ROOT must be an existing directory: %s\n' "${root:-<missing>}" >&2
    usage >&2
    exit 2
fi

declare -a safetensors_files=()
while IFS= read -r -d '' path; do
    safetensors_files+=("$path")
done < <(find "$root" -type f -name '*.safetensors' -print0)

if ((${#safetensors_files[@]} == 0)); then
    printf 'No *.safetensors files found below %q.\n' "$root"
    exit 0
fi

keep_path=""
keep_version=""

for path in "${safetensors_files[@]}"; do
    basename=${path##*/}
    if [[ $basename =~ ^global_v([0-9]+)\.safetensors$ ]]; then
        version=${BASH_REMATCH[1]}
        normalized=${version#"${version%%[!0]*}"}
        [[ -n $normalized ]] || normalized=0

        is_larger=false
        if [[ -z $keep_path ]]; then
            is_larger=true
        elif ((${#normalized} > ${#keep_version})); then
            is_larger=true
        elif ((${#normalized} == ${#keep_version})) && [[ $normalized > $keep_version ]]; then
            is_larger=true
        elif [[ $normalized == "$keep_version" && $path > $keep_path ]]; then
            is_larger=true
        fi

        if [[ $is_larger == true ]]; then
            keep_path=$path
            keep_version=$normalized
        fi
    fi
done

if [[ -z $keep_path ]]; then
    printf 'Refusing to delete: no global_v<digits>.safetensors file found below %q.\n' "$root" >&2
    exit 1
fi

printf 'KEEP   %q (version %s)\n' "$keep_path" "$keep_version"

deleted=0
for path in "${safetensors_files[@]}"; do
    [[ $path == "$keep_path" ]] && continue

    if [[ $delete == true ]]; then
        rm -- "$path"
        printf 'DELETE %q\n' "$path"
    else
        printf 'DRY-RUN DELETE %q\n' "$path"
    fi
    ((deleted += 1))
done

if [[ $delete == true ]]; then
    printf 'Deleted %d file(s); kept 1.\n' "$deleted"
else
    printf 'Dry run: would delete %d file(s); pass --delete to proceed.\n' "$deleted"
fi
