#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  SMOKE TEST — Katman 2
#  Deployment sonrası veya manuel olarak çalıştırılır.
#
#  Kullanım:
#    ./smoke_test.sh              → DEV'i test eder (5600/5001)
#    ./smoke_test.sh --target stable  → STABLE'ı test eder (5700/8603)
# ═══════════════════════════════════════════════════════════════════════

set -uo pipefail

TARGET="dev"
for arg in "$@"; do
  [[ "$arg" == "--target" ]] && { TARGET="${2:-dev}"; break; }
done

VENV_PY="/Users/hakanficicilar/.superinvestor-venv/bin/python3"
if [[ "$TARGET" == "stable" ]]; then
  SI_DIR="/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE/SUPER-INVESTOR-CHATGPT"
  SI_PORT=8603
  PORTAL_PORT=5700
else
  SI_DIR="/Users/hakanficicilar/SuperInvestor"
  SI_PORT=5001
  PORTAL_PORT=5600
fi

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0; FAIL=0; WARN=0
log_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; ((PASS++)) || true; }
log_err()  { echo -e "${RED}  ✗ $1${NC}"; ((FAIL++)) || true; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; ((WARN++)) || true; }
log_info() { echo -e "${CYAN}  → $1${NC}"; }

echo -e "\n${BOLD}╔═════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   SMOKE TEST — Katman 2  [$( echo $TARGET | tr a-z A-Z )]        ║${NC}"
echo -e "${BOLD}╚═════════════════════════════════════════════╝${NC}"
echo "Hedef  : $SI_DIR"
echo "Tarih  : $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ── TEST 1: Python syntax ─────────────────────────────────────────────
echo -e "${BOLD}[T1] Syntax Kontrolü${NC}"
SFAIL=0
for f in "$SI_DIR"/*.py; do
  if ! $VENV_PY -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
    log_err "Syntax hatası: $(basename $f)"
    SFAIL=1
  fi
done
[[ $SFAIL -eq 0 ]] && log_ok "Tüm .py dosyaları geçerli"

# ── TEST 2: Kritik modül importları ──────────────────────────────────
echo -e "\n${BOLD}[T2] Modül Import Kontrolü${NC}"
$VENV_PY - << PYEOF
import sys, os
sys.path.insert(0, '$SI_DIR')
tests = [
    ('backtest_engine',       'run_backtest'),
    ('scoring_engine',        'score_stock'),
    ('data_fetcher',          'fetch_backtest_data'),
    ('filters',               'apply_filters'),
    ('indicators',            'compute_indicators'),
    ('bist_adaptations',      'apply_bist_adaptations'),
    ('scan_history',          'save_scan_result'),
    ('historical_fundamentals','inject_fundamentals_at_date'),
]
ok = err = 0
for mod, fn in tests:
    try:
        m = __import__(mod)
        if hasattr(m, fn):
            print(f'\033[0;32m  ✓ {mod}.{fn}\033[0m')
        else:
            print(f'\033[1;33m  ⚠ {mod} yüklendi ama {fn} bulunamadı\033[0m')
        ok += 1
    except Exception as e:
        print(f'\033[0;31m  ✗ {mod}: {e}\033[0m')
        err += 1
print(f'\n  Sonuç: {ok} geçti, {err} başarısız')
sys.exit(0 if err == 0 else 1)
PYEOF
IMPORT_EXIT=$?
[[ $IMPORT_EXIT -ne 0 ]] && ((FAIL++)) || ((PASS++))

# ── TEST 3: Backtest motoru fonksiyonel test ──────────────────────────
echo -e "\n${BOLD}[T3] Backtest Motor Testi (mini)${NC}"
BT_RESULT=$($VENV_PY - 2>&1 << PYEOF
import sys, os
sys.path.insert(0, '$SI_DIR')
try:
    from backtest_engine import run_backtest
    import datetime
    end = datetime.date.today()
    start = end - datetime.timedelta(days=90)
    result = run_backtest(
        start_date=start,
        end_date=end,
        market='USA',
        top_n=3,
        rebalance_freq='monthly',
        universe="SP500",
        scan_mode='standard',
        quality_preset="basic",
        sort_by='combined_score',
        inst_profile="standard"
    )
    if hasattr(result, 'total_return'):
        tr = result.total_return
        print(f'OK — total_return: {tr:.2f}')
    elif hasattr(result, 'get'):
        tr = result.get('total_return', None)
        print(f'OK — total_return: {tr}')
    else:
        print('WARN — total_return anahtarı yok')
except Exception as e:
    print(f'ERR — {e}')
PYEOF
)
if echo "$BT_RESULT" | grep -q "^OK"; then
  log_ok "Backtest motoru çalışıyor: $BT_RESULT"
elif echo "$BT_RESULT" | grep -q "^WARN"; then
  log_warn "Backtest çalıştı ama uyarı: $BT_RESULT"
else
  log_err "Backtest başarısız: $BT_RESULT"
fi

# ── TEST 4: Port/HTTP kontrolü ────────────────────────────────────────
echo -e "\n${BOLD}[T4] Port Kontrolü${NC}"
check_port() {
  local port=$1; local name=$2
  if lsof -i :$port -sTCP:LISTEN -t > /dev/null 2>&1; then
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://localhost:$port/" 2>/dev/null || echo "000")
    if [[ "$HTTP" =~ ^(200|302|303)$ ]]; then
      log_ok "$name (port $port) → HTTP $HTTP"
    else
      log_warn "$name (port $port) çalışıyor ama HTTP $HTTP döndü"
    fi
  else
    log_warn "$name (port $port) kapalı veya başlamıyor"
  fi
}
check_port $SI_PORT    "Super Investor"
check_port $PORTAL_PORT "ALL-IN-ONE Portal"

# ── TEST 5: Kritik dosya varlığı ─────────────────────────────────────
echo -e "\n${BOLD}[T5] Kritik Dosya Kontrolü${NC}"
CRITICAL_FILES=(
  "app.py" "backtest_engine.py" "scoring_engine.py"
  "data_fetcher.py" "filters.py" "indicators.py"
  "bist_adaptations.py" "historical_fundamentals.py"
  "fmp_data_provider.py" "scan_history.py"
)
for f in "${CRITICAL_FILES[@]}"; do
  if [[ -f "$SI_DIR/$f" ]]; then
    log_ok "$f mevcut"
  else
    log_err "$f eksik!"
  fi
done

# ── TEST 6: .env / API key kontrolü ──────────────────────────────────
echo -e "\n${BOLD}[T6] Ortam Değişkeni Kontrolü${NC}"
if [[ -f "$SI_DIR/.env" ]]; then
  if grep -q "FMP_API_KEY" "$SI_DIR/.env" 2>/dev/null; then
    FMP_VAL=$(grep "FMP_API_KEY" "$SI_DIR/.env" | cut -d= -f2 | tr -d ' "')
    if [[ ${#FMP_VAL} -gt 10 ]]; then
      log_ok ".env — FMP_API_KEY tanımlı (${#FMP_VAL} karakter)"
    else
      log_warn ".env — FMP_API_KEY çok kısa veya boş"
    fi
  else
    log_warn ".env — FMP_API_KEY bulunamadı"
  fi
else
  log_warn ".env dosyası yok (LaunchAgent'tan alınıyor olabilir)"
fi

# ── Özet ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════${NC}"
TOTAL_TESTS=$((PASS + FAIL + WARN))
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}  SMOKE TEST GEÇTI ✓  ($PASS/$TOTAL_TESTS)${NC}"
  echo -e "${BOLD}════════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}  SMOKE TEST BAŞARISIZ ✗  ($FAIL hata, $WARN uyarı)${NC}"
  echo -e "${BOLD}════════════════════════════════════════════${NC}"
  exit 1
fi
