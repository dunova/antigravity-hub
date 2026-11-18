#!/usr/bin/env bash
# ==============================================================================
# Antigravity Language Server CCPA Region Guard Wrapper Installer (v3.0.9)
#
# Purpose:
#   Atomically wraps /opt/Antigravity/resources/bin/language_server so that when
#   antigravity-hub (127.0.0.1:18088) is alive, --cloud_code_endpoint is routed
#   through http://127.0.0.1:18088/ccpa to strip false-positive free-tier
#   UNSUPPORTED_LOCATION blocks for valid paid subscriptions (Ultra/Pro),
#   matching macOS v2.31.0 seamless hot-switching behavior.
#   When antigravity-hub is offline, 100% falls back to vanilla upstream URL.
# ==============================================================================
set -euo pipefail

LS_PATH="/opt/Antigravity/resources/bin/language_server"
VANILLA_BACKUP="/opt/Antigravity/resources/bin/language_server.orig_vanilla"
HUB_HEALTH_URL="http://127.0.0.1:18088/api/health"
HUB_CCPA_URL="http://127.0.0.1:18088/ccpa"

usage() {
    echo "Usage: $0 [--install | --rollback | --status]"
}

is_elf_binary() {
    local p="$1"
    [[ -f "$p" ]] && head -c 4 "$p" 2>/dev/null | grep -q $'\x7fELF'
}

is_wrapper_script() {
    local p="$1"
    [[ -f "$p" ]] && head -c 2 "$p" 2>/dev/null | grep -q '^#!' && grep -q 'language_server.orig_vanilla' "$p" 2>/dev/null
}

do_status() {
    echo "LS_PATH: $LS_PATH"
    if is_wrapper_script "$LS_PATH"; then
        echo "  state: WRAPPED"
    elif is_elf_binary "$LS_PATH"; then
        echo "  state: VANILLA_ELF"
    else
        echo "  state: MISSING_OR_UNKNOWN"
    fi
    if is_elf_binary "$VANILLA_BACKUP"; then
        echo "VANILLA_BACKUP: PRESENT ($VANILLA_BACKUP)"
    else
        echo "VANILLA_BACKUP: MISSING"
    fi
    if curl -fsS --max-time 0.5 "$HUB_HEALTH_URL" >/dev/null 2>&1; then
        echo "HUB_PROXY: HEALTHY ($HUB_HEALTH_URL)"
    else
        echo "HUB_PROXY: OFFLINE (wrapper will fall back to vanilla upstream)"
    fi
}

do_install() {
    if is_elf_binary "$LS_PATH"; then
        # 原厂二进制或软件更新后新安装的 ELF：原子备份为 orig_vanilla（同文件系统 rename，不影响已运行进程 inode）
        sudo mv -f "$LS_PATH" "$VANILLA_BACKUP"
        echo "✅ Backed up vanilla ELF binary to $VANILLA_BACKUP"
    elif ! is_elf_binary "$VANILLA_BACKUP"; then
        echo "❌ Cannot locate vanilla ELF binary at $LS_PATH or $VANILLA_BACKUP" >&2
        exit 1
    fi

    if [[ ! -x "$VANILLA_BACKUP" ]]; then
        sudo chmod 0755 "$VANILLA_BACKUP"
    fi

    local tmp_wrapper
    tmp_wrapper="$(mktemp /tmp/language_server.wrapper.XXXXXX)"
    cat > "$tmp_wrapper" <<'EOF'
#!/usr/bin/env bash
# Antigravity Hub v3.0.9 CCPA Guard Wrapper
REAL_BIN="/opt/Antigravity/resources/bin/language_server.orig_vanilla"
USE_PROXY=0
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 0.2 http://127.0.0.1:18088/api/health >/dev/null 2>&1; then
    USE_PROXY=1
fi

ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cloud_code_endpoint)
            if [[ "$USE_PROXY" -eq 1 ]]; then
                ARGS+=("--cloud_code_endpoint" "http://127.0.0.1:18088/ccpa")
            else
                ARGS+=("--cloud_code_endpoint" "${2:-https://daily-cloudcode-pa.googleapis.com}")
            fi
            shift 2 || break
            ;;
        --cloud_code_endpoint=*)
            if [[ "$USE_PROXY" -eq 1 ]]; then
                ARGS+=("--cloud_code_endpoint=http://127.0.0.1:18088/ccpa")
            else
                ARGS+=("$1")
            fi
            shift 1
            ;;
        *)
            ARGS+=("$1")
            shift 1
            ;;
    esac
done

exec "$REAL_BIN" "${ARGS[@]}"
EOF

    sudo install -m 0755 "$tmp_wrapper" "$LS_PATH"
    rm -f "$tmp_wrapper"
    echo "✅ Installed wrapper at $LS_PATH -> $VANILLA_BACKUP"
}

do_rollback() {
    if is_elf_binary "$VANILLA_BACKUP"; then
        sudo mv -f "$VANILLA_BACKUP" "$LS_PATH"
        echo "✅ Rolled back $LS_PATH to vanilla ELF binary"
    else
        echo "ℹ️ Vanilla backup $VANILLA_BACKUP not present; checking $LS_PATH"
        do_status
    fi
}

case "${1:---status}" in
    --install)
        do_install
        ;;
    --rollback)
        do_rollback
        ;;
    --status)
        do_status
        ;;
    *)
        usage
        exit 2
        ;;
esac
