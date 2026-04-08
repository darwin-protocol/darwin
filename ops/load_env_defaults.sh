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

darwin_config_dir() {
  echo "${DARWIN_CONFIG_DIR:-$HOME/.config/darwin}"
}

resolve_darwin_env_file() {
  local preferred="$1"
  local legacy="${2:-}"

  if [[ -f "$preferred" ]]; then
    echo "$preferred"
    return 0
  fi
  if [[ -n "$legacy" && -f "$legacy" ]]; then
    echo "$legacy"
    return 0
  fi
  echo "$preferred"
}

load_base_sepolia_env() {
  local root="$1"
  local config_dir
  local env_file

  config_dir="$(darwin_config_dir)"
  env_file="${DARWIN_ENV_FILE:-$(resolve_darwin_env_file "$config_dir/base-sepolia.env" "$root/.env.base-sepolia")}"
  load_env_defaults "$env_file"
}

load_arbitrum_sepolia_env() {
  local root="$1"
  local config_dir
  local env_file

  config_dir="$(darwin_config_dir)"
  env_file="${DARWIN_ARBITRUM_ENV_FILE:-$(resolve_darwin_env_file "$config_dir/arbitrum-sepolia.env" "$root/.env.arbitrum-sepolia")}"
  load_env_defaults "$env_file"
}

load_site_publish_env() {
  local root="$1"
  local config_dir
  local env_file

  config_dir="$(darwin_config_dir)"
  env_file="${DARWIN_SITE_ENV_FILE:-$(resolve_darwin_env_file "$config_dir/site.env" "$root/.env.site")}"
  load_env_defaults "$env_file"
}

load_darwin_network_env() {
  local root="$1"
  case "${DARWIN_NETWORK:-}" in
    arbitrum-sepolia|arbitrum)
      load_arbitrum_sepolia_env "$root"
      ;;
    *)
      load_base_sepolia_env "$root"
      ;;
  esac
}
