#!/usr/bin/env bash

load_env_defaults() {
  local env_file="$1"
  local line key value

  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"

    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      value="${BASH_REMATCH[2]}"
      if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
        value="${value:1:${#value}-2}"
      fi
      if [[ -z "${!key:-}" ]]; then
        export "$key=$value"
      fi
    fi
  done < "$env_file"
}


load_base_sepolia_env() {
  local root="$1"
  local env_file="${DARWIN_ENV_FILE:-$root/.env.base-sepolia}"
  load_env_defaults "$env_file"
}
