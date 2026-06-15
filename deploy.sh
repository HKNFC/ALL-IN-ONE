#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  DEPLOYMENT SCRIPT  — Katman 1
#  DEV (localhost:5600 / SuperInvestor) → STABLE (localhost:5700)
#
#  Kullanım:
#    ./deploy.sh              → dry-run (ne değişeceğini gösterir)
#    ./deploy.sh --confirm    → gerçek deploy (önce checkpoint alır)
#    ./deploy.sh --rollback   → son checkpoint'e geri döner
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

DEV_SI="/Users/hakanficicilar/SuperInvestor"
STABLE_SI="/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE/SUPER-INVESTOR-CHATGPT"
STABLE_ROOT="/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE"
CHECKPOINT_DIR="/Users/hakanficicilar/Documents/Aİ/.checkpoints"
SMOKE_SCRIPT="$(dirname "$0")/smoke_test.sh"
LOG_FILE="/tmp/deploy_$(date +%Y%m%d_%H%M%S).log"
STABLE_PASSWORD="457101525"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()      { echo -e "$1" | tee -a "$LOG_FILE"; }
log_ok()   { log "${GREEN}  ✓ $1${NC}"; }
log_warn() { log "${YELLOW}  ⚠ $1${NC}"; }
log_err()  { log "${RED}  ✗ $1${NC}"; }
log_info() { log "${CYAN}  → $1${NC}"; }

DRY_RUN=true
ROLLBACK=false
for arg in "$@"; do
  case "$arg" in
    --confirm)  DRY_RUN=false ;;
    --rollback) ROLLBACK=true ;;
    --help|-h)
      echo "Kullanım: $0 [--confirm] [--rollback]"
      echo "  (argümansız)  → dry-run: ne değişeceğini gösterir"
      echo "  --confirm     → gerçek deploy"
      echo "  --rollback    → son checkpoint'e geri döner"
      exit 0 ;;
  esac
done

# ── ROLLBACK modu ────────────────────────────────────────────────────────
if $ROLLBACK; then
  log "\n${BOLD}═══════════════ ROLLBACK MODU ═══════════════${NC}"
  LATEST=$(ls -dt "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null | head -1)
  if [[ -z "$LATEST" ]]; then
    log_err "Hiç checkpoint bulunamadı: $CHECKPOINT_DIR"
    exit 1
  fi
  log_info "Geri yüklenecek checkpoint: $(basename $LATEST)"
  echo -n "Şifreyi girin: "
  read -s INPUT_PASS; echo
  if [[ "$INPUT_PASS" != "$STABLE_PASSWORD" ]]; then
    log_err "Hatalı şifre — rollback iptal edildi."
    exit 1
  fi
  chmod -R u+w "$STABLE_SI" 2>/dev/null || true
  cp -Rf "$LATEST/SUPER-INVESTOR-CHATGPT/." "$STABLE_SI/"
  chmod -R a-w "$STABLE_SI" 2>/dev/null || true
  log_ok "Rollback tamamlandı → $(basename $LATEST)"
  bash "$STABLE_ROOT/start_stable.sh" &
  exit 0
fi

log "\n${BOLD}╔══════════════════════════════════════════════════╗${NC}"
log "${BOLD}║   ALL-IN-ONE DEPLOYMENT SCRIPT  (Katman 1)      ║${NC}"
log "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
log "Tarih   : $(date '+%Y-%m-%d %H:%M:%S')"
log "Mod     : $( $DRY_RUN && echo 'DRY-RUN (önizleme)' || echo 'CANLI DEPLOY' )\n"

# ── [1] Syntax kontrolü ──────────────────────────────────────────────────
log "${BOLD}[1/5] Syntax Kontrolü${NC}"
FAIL=0
VENV_PY="/Users/hakanficicilar/.superinvestor-venv/bin/python3"
for f in "$DEV_SI"/*.py; do
  if ! $VENV_PY -c "import ast; ast.parse(open('$f').read())" 2>/tmp/syntax_err.txt; then
    log_err "$(basename $f): $(cat /tmp/syntax_err.txt)"
    FAIL=1
  fi
done
[[ $FAIL -eq 1 ]] && { log_err "Syntax hatası — deploy iptal!"; exit 1; }
log_ok "Tüm .py dosyaları syntax kontrolünden geçti"

# ── [2] Import kontrolü ──────────────────────────────────────────────────
log "\n${BOLD}[2/5] Import Kontrolü${NC}"
IMPORT_RESULT=$($VENV_PY - << 'PYEOF'
import sys, os
sys.path.insert(0, '/Users/hakanficicilar/SuperInvestor')
errors = []
modules = ['backtest_engine','scoring_engine','data_fetcher','filters',
           'indicators','momentum_metrics','bist_adaptations','scan_history',
           'historical_fundamentals','fmp_data_provider','price_provider','disk_cache']
for m in modules:
    try:
        __import__(m)
    except Exception as e:
        errors.append(f'{m}: {e}')
if errors:
    for e in errors: print('ERR:'+e)
else:
    print('OK')
PYEOF
)
if echo "$IMPORT_RESULT" | grep -q "^ERR:"; then
  echo "$IMPORT_RESULT" | grep "^ERR:" | sed 's/^ERR://' | while read line; do log_err "$line"; done
  log_err "Import hatası — deploy iptal!"
  exit 1
fi
log_ok "Kritik modüller import edilebilir"

# ── [3] Değişiklik tespiti ───────────────────────────────────────────────
log "\n${BOLD}[3/5] Değişiklik Tespiti${NC}"
CHANGED=0 NEW_C=0 DEL_C=0
for f in "$DEV_SI"/*.py; do
  fname=$(basename "$f")
  target="$STABLE_SI/$fname"
  if [[ ! -f "$target" ]]; then
    log_info "YENİ: $fname"; ((NEW_C++)) || true
  elif ! diff -q "$f" "$target" > /dev/null 2>&1; then
    log_warn "DEĞİŞTİ: $fname"; ((CHANGED++)) || true
    diff "$target" "$f" | grep "^[<>]" | head -3 | sed 's/^/         /'
  fi
done
for f in "$STABLE_SI"/*.py; do
  fname=$(basename "$f")
  [[ ! -f "$DEV_SI/$fname" ]] && { log_warn "SİLİNECEK: $fname"; ((DEL_C++)) || true; }
done
TOTAL=$((CHANGED + NEW_C + DEL_C))
[[ $TOTAL -eq 0 ]] && { log_ok "Hiçbir değişiklik yok."; exit 0; }
log "\n  ${BOLD}Özet: $CHANGED değişti, $NEW_C yeni, $DEL_C silinecek${NC}"

$DRY_RUN && { log "\n${YELLOW}Gerçek deploy için: ./deploy.sh --confirm${NC}"; exit 0; }

# ── [4] Şifre doğrulama ──────────────────────────────────────────────────
log "\n${BOLD}[4/5] Şifre Doğrulama${NC}"
echo -n "STABLE ortamını güncellemek için şifreyi girin: "
read -s INPUT_PASS; echo
[[ "$INPUT_PASS" != "$STABLE_PASSWORD" ]] && { log_err "Hatalı şifre — deploy iptal!"; exit 1; }
log_ok "Şifre doğrulandı"

# ── [5] Checkpoint + Deploy ──────────────────────────────────────────────
log "\n${BOLD}[5/5] Checkpoint + Deploy${NC}"
mkdir -p "$CHECKPOINT_DIR"
CHECKPOINT_NAME="checkpoint_$(date +%Y%m%d_%H%M%S)"
CHECKPOINT_PATH="$CHECKPOINT_DIR/$CHECKPOINT_NAME"
mkdir -p "$CHECKPOINT_PATH"
cp -Rf "$STABLE_SI" "$CHECKPOINT_PATH/"
log_ok "Checkpoint alındı: $CHECKPOINT_NAME"

# 5+ checkpoint varsa en eskiyi sil
CP_COUNT=$(ls -d "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null | wc -l)
if [[ $CP_COUNT -gt 5 ]]; then
  OLDEST=$(ls -dt "$CHECKPOINT_DIR"/checkpoint_* | tail -1)
  rm -rf "$OLDEST"
  log_info "Eski checkpoint silindi: $(basename $OLDEST)"
fi

chmod -R u+w "$STABLE_SI" 2>/dev/null || true
rsync -av --exclude='*.pyc' --exclude='__pycache__' \
  "$DEV_SI/" "$STABLE_SI/" >> "$LOG_FILE" 2>&1
log_ok "Dosyalar kopyalandı"
chmod -R a-w "$STABLE_SI" 2>/dev/null || true
log_ok "STABLE klasörü kilitlendi"

# ── Smoke test ───────────────────────────────────────────────────────────
if [[ -f "$SMOKE_SCRIPT" ]]; then
  log "\n${BOLD}Smoke Test çalıştırılıyor...${NC}"
  if ! bash "$SMOKE_SCRIPT" --target stable 2>&1 | tee -a "$LOG_FILE"; then
    log_err "Smoke test başarısız! Rollback yapılıyor..."
    chmod -R u+w "$STABLE_SI" 2>/dev/null || true
    cp -Rf "$CHECKPOINT_PATH/SUPER-INVESTOR-CHATGPT/." "$STABLE_SI/"
    chmod -R a-w "$STABLE_SI" 2>/dev/null || true
    log_warn "Rollback tamamlandı"
    exit 1
  fi
else
  log_warn "smoke_test.sh bulunamadı — test atlandı"
fi

log "\n${GREEN}${BOLD}══════════════════════════════════════════${NC}"
log "${GREEN}${BOLD}  DEPLOY BAŞARILI ✓  |  Log: $LOG_FILE${NC}"
log "${GREEN}${BOLD}══════════════════════════════════════════${NC}"
