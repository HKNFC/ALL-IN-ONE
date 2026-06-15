#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  CHECKPOINT KORUMASI — Katman 3
#  Manuel veya otomatik snapshot yönetimi
#
#  Kullanım:
#    ./checkpoint.sh save              → anlık snapshot al
#    ./checkpoint.sh save "açıklama"  → açıklamalı snapshot
#    ./checkpoint.sh list              → mevcut checkpoint'leri listele
#    ./checkpoint.sh restore           → listeden seç ve geri yükle
#    ./checkpoint.sh restore <isim>   → belirli checkpoint'i geri yükle
#    ./checkpoint.sh diff <isim>      → checkpoint ile mevcut farkı göster
#    ./checkpoint.sh auto-protect     → cron ile saatlik otomatik koruma kur
# ═══════════════════════════════════════════════════════════════════════

set -uo pipefail

STABLE_SI="/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE/SUPER-INVESTOR-CHATGPT"
DEV_SI="/Users/hakanficicilar/SuperInvestor"
CHECKPOINT_DIR="/Users/hakanficicilar/Documents/Aİ/.checkpoints"
STABLE_PASSWORD="457101525"
MAX_CHECKPOINTS=10

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
log_err()  { echo -e "${RED}  ✗ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
log_info() { echo -e "${CYAN}  → $1${NC}"; }

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in

# ── save ──────────────────────────────────────────────────────────────
save)
  LABEL="${1:-manual}"
  SAFE_LABEL=$(echo "$LABEL" | tr ' ' '_' | tr -cd '[:alnum:]_-')
  TS=$(date +%Y%m%d_%H%M%S)
  CHKPT_NAME="checkpoint_${TS}_${SAFE_LABEL}"
  CHKPT_PATH="$CHECKPOINT_DIR/$CHKPT_NAME"

  mkdir -p "$CHKPT_PATH"

  # DEV snapshot
  rsync -a --exclude='*.pyc' --exclude='__pycache__' \
    --exclude='data/' --exclude='artifacts/' \
    "$DEV_SI/" "$CHKPT_PATH/DEV/"

  # STABLE snapshot
  rsync -a --exclude='*.pyc' --exclude='__pycache__' \
    --exclude='data/' --exclude='artifacts/' \
    "$STABLE_SI/" "$CHKPT_PATH/STABLE/"

  # Metadata
  cat > "$CHKPT_PATH/info.json" << JSON
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "label": "$LABEL",
  "dev_files": $(ls "$DEV_SI"/*.py 2>/dev/null | wc -l),
  "stable_files": $(ls "$STABLE_SI"/*.py 2>/dev/null | wc -l),
  "git_hash": "$(cd $DEV_SI && git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
}
JSON

  log_ok "Checkpoint kaydedildi: $CHKPT_NAME"
  log_info "Konum: $CHKPT_PATH"

  # Eski checkpoint temizleme
  CP_LIST=($(ls -dt "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null))
  if [[ ${#CP_LIST[@]} -gt $MAX_CHECKPOINTS ]]; then
    for OLD in "${CP_LIST[@]:$MAX_CHECKPOINTS}"; do
      rm -rf "$OLD"
      log_warn "Eski checkpoint silindi: $(basename $OLD)"
    done
  fi
  ;;

# ── list ──────────────────────────────────────────────────────────────
list)
  echo -e "\n${BOLD}Mevcut Checkpoint'ler${NC}"
  echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
  CP_LIST=($(ls -dt "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null))
  if [[ ${#CP_LIST[@]} -eq 0 ]]; then
    log_warn "Hiç checkpoint bulunamadı."
    exit 0
  fi
  IDX=1
  for CP in "${CP_LIST[@]}"; do
    NAME=$(basename "$CP")
    INFO="$CP/info.json"
    if [[ -f "$INFO" ]]; then
      TS=$(python3 -c "import json; d=json.load(open('$INFO')); print(d.get('timestamp','?'))" 2>/dev/null || echo "?")
      LABEL=$(python3 -c "import json; d=json.load(open('$INFO')); print(d.get('label','?'))" 2>/dev/null || echo "?")
      DEV_F=$(python3 -c "import json; d=json.load(open('$INFO')); print(d.get('dev_files','?'))" 2>/dev/null || echo "?")
      GIT=$(python3 -c "import json; d=json.load(open('$INFO')); print(d.get('git_hash','n/a'))" 2>/dev/null || echo "n/a")
      echo -e "  ${CYAN}[$IDX]${NC} ${BOLD}$NAME${NC}"
      echo -e "       Tarih: $TS | Etiket: $LABEL | DEV dosyaları: $DEV_F | git: $GIT"
    else
      echo -e "  ${CYAN}[$IDX]${NC} $NAME"
    fi
    ((IDX++)) || true
  done
  echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
  ;;

# ── restore ───────────────────────────────────────────────────────────
restore)
  # Şifre kontrolü
  echo -n "STABLE ortamına geri yüklemek için şifreyi girin: "
  read -s INPUT_PASS; echo
  if [[ "$INPUT_PASS" != "$STABLE_PASSWORD" ]]; then
    log_err "Hatalı şifre — restore iptal edildi."
    exit 1
  fi

  TARGET_NAME="${1:-}"
  if [[ -z "$TARGET_NAME" ]]; then
    # İnteraktif seçim
    CP_LIST=($(ls -dt "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null))
    if [[ ${#CP_LIST[@]} -eq 0 ]]; then
      log_err "Checkpoint bulunamadı."
      exit 1
    fi
    bash "$0" list
    echo -n "Geri yüklenecek numarayı girin: "
    read SEL
    IDX=$((SEL - 1))
    TARGET_NAME=$(basename "${CP_LIST[$IDX]}")
  fi

  CHKPT_PATH="$CHECKPOINT_DIR/$TARGET_NAME"
  if [[ ! -d "$CHKPT_PATH" ]]; then
    log_err "Checkpoint bulunamadı: $TARGET_NAME"
    exit 1
  fi

  # Mevcut durumu otomatik kaydet
  PRE_RESTORE="checkpoint_$(date +%Y%m%d_%H%M%S)_pre_restore"
  mkdir -p "$CHECKPOINT_DIR/$PRE_RESTORE/STABLE"
  cp -Rf "$STABLE_SI/." "$CHECKPOINT_DIR/$PRE_RESTORE/STABLE/"
  log_warn "Mevcut durum kaydedildi: $PRE_RESTORE"

  # Geri yükle
  chmod -R u+w "$STABLE_SI" 2>/dev/null || true
  if [[ -d "$CHKPT_PATH/STABLE" ]]; then
    cp -Rf "$CHKPT_PATH/STABLE/." "$STABLE_SI/"
    log_ok "STABLE geri yüklendi: $TARGET_NAME"
  else
    cp -Rf "$CHKPT_PATH/." "$STABLE_SI/"
    log_ok "STABLE geri yüklendi (eski format): $TARGET_NAME"
  fi
  chmod -R a-w "$STABLE_SI" 2>/dev/null || true
  log_ok "STABLE kilidi yeniden uygulandı"

  echo -e "\n${YELLOW}STABLE'ı yeniden başlatmak ister misiniz? [y/N]${NC}"
  read -r RESTART
  if [[ "${RESTART,,}" == "y" ]]; then
    bash "/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE/start_stable.sh" &
    log_ok "STABLE yeniden başlatıldı"
  fi
  ;;

# ── diff ──────────────────────────────────────────────────────────────
diff)
  TARGET_NAME="${1:-}"
  if [[ -z "$TARGET_NAME" ]]; then
    bash "$0" list
    echo -n "Karşılaştırılacak numarayı girin: "
    read SEL
    CP_LIST=($(ls -dt "$CHECKPOINT_DIR"/checkpoint_* 2>/dev/null))
    IDX=$((SEL - 1))
    TARGET_NAME=$(basename "${CP_LIST[$IDX]}")
  fi
  CHKPT_PATH="$CHECKPOINT_DIR/$TARGET_NAME"
  SRC_DIR="$CHKPT_PATH/STABLE"
  [[ ! -d "$SRC_DIR" ]] && SRC_DIR="$CHKPT_PATH/SUPER-INVESTOR-CHATGPT"
  [[ ! -d "$SRC_DIR" ]] && SRC_DIR="$CHKPT_PATH"
  echo -e "\n${BOLD}Fark Raporu: $TARGET_NAME vs MEVCUT STABLE${NC}"
  echo -e "${BOLD}══════════════════════════════════════════${NC}"
  FOUND_DIFF=0
  for f in "$SI_DIR_SRC"/*.py "$SRC_DIR"/*.py; do
    fname=$(basename "$f" 2>/dev/null) || continue
    current="$STABLE_SI/$fname"
    old_f="$SRC_DIR/$fname"
    [[ ! -f "$current" ]] && { log_info "YENİ (checkpoint'te yok): $fname"; FOUND_DIFF=1; continue; }
    [[ ! -f "$old_f" ]] && { log_info "SİLİNMİŞ (checkpoint'te vardı): $fname"; FOUND_DIFF=1; continue; }
    if ! diff -q "$old_f" "$current" > /dev/null 2>&1; then
      echo -e "${YELLOW}  ~ $fname${NC}"
      diff "$old_f" "$current" | grep "^[<>]" | head -5
      FOUND_DIFF=1
    fi
  done
  [[ $FOUND_DIFF -eq 0 ]] && log_ok "Hiçbir fark yok."
  ;;

# ── auto-protect ──────────────────────────────────────────────────────
auto-protect)
  CRON_CMD="0 * * * * bash /Users/hakanficicilar/Documents/Aİ/checkpoint.sh save auto-hourly >> /tmp/checkpoint_cron.log 2>&1"
  CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")
  if echo "$CURRENT_CRON" | grep -q "checkpoint.sh"; then
    log_warn "Otomatik koruma zaten aktif"
  else
    (echo "$CURRENT_CRON"; echo "$CRON_CMD") | crontab -
    log_ok "Otomatik checkpoint kuruldu (her saat başı)"
    log_info "Cron: $CRON_CMD"
  fi
  ;;

# ── help ──────────────────────────────────────────────────────────────
*)
  echo -e "\n${BOLD}CHECKPOINT KORUMASI — Katman 3${NC}"
  echo -e "${BOLD}══════════════════════════════════════════${NC}"
  echo "  ./checkpoint.sh save [etiket]   → Snapshot al"
  echo "  ./checkpoint.sh list            → Checkpoint'leri listele"
  echo "  ./checkpoint.sh restore [isim] → Geri yükle"
  echo "  ./checkpoint.sh diff [isim]    → Fark göster"
  echo "  ./checkpoint.sh auto-protect   → Saatlik otomatik cron kur"
  echo -e "${BOLD}══════════════════════════════════════════${NC}"
  ;;
esac
